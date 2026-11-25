/** Exact-palette geometric observations. No model, labels or answer keys are used. */
const COLORS = ['red', 'green', 'blue'];
const PALETTE = new Map([
  ['255,255,255', 0], ['0,0,0', 0], ['220,30,30', 1],
  ['20,150,50', 2], ['30,70,220', 3],
]);
const SHAPES = new Set(['square', 'rectangle', 'circle', 'unknown']);

function classify(points, left, top, right, bottom) {
  const width = right - left, height = bottom - top;
  if (points.length === width * height) return width === height ? 'square' : 'rectangle';
  if (width === height && width % 2 === 1) {
    const radius = (width - 1) / 2, cx = left + radius, cy = top + radius;
    let expected = 0;
    for (let dy = -radius; dy <= radius; dy++) {
      expected += 2 * Math.floor(Math.sqrt(radius * radius - dy * dy)) + 1;
    }
    if (points.length === expected && points.every(([x,y]) => (x-cx)**2 + (y-cy)**2 <= radius**2)) {
      return 'circle';
    }
  }
  return 'unknown';
}

export function observePixels(data, width, height) {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 256 || height > 256) {
    throw new Error('Image dimensions must be between 1 and 256 pixels.');
  }
  if (!(data instanceof Uint8ClampedArray || data instanceof Uint8Array) || data.length !== width * height * 4) {
    throw new Error('Expected a complete RGBA byte raster.');
  }
  const labels = new Uint8Array(width * height);
  for (let i=0; i<labels.length; i++) {
    const offset=i*4;
    if (data[offset+3] !== 255) throw new Error('Transparent pixels are outside the supported profile.');
    const color=PALETTE.get(`${data[offset]},${data[offset+1]},${data[offset+2]}`);
    if (color === undefined) throw new Error('Image contains an unsupported palette color.');
    labels[i]=color;
  }
  const visited=new Uint8Array(labels.length), observed={red:[],green:[],blue:[]};
  let components=0;
  for (let start=0; start<labels.length; start++) {
    const color=labels[start];
    if (!color || visited[start]) continue;
    if (++components>1024) throw new Error('Image exceeds the component limit.');
    const queue=[start], points=[];
    let cursor=0, left=width, top=height, right=0, bottom=0;
    visited[start]=1;
    while (cursor<queue.length) {
      const position=queue[cursor++], x=position%width, y=Math.floor(position/width);
      points.push([x,y]); left=Math.min(left,x); top=Math.min(top,y);
      right=Math.max(right,x+1); bottom=Math.max(bottom,y+1);
      const neighbors=[];
      if(x>0) neighbors.push(position-1);
      if(x+1<width) neighbors.push(position+1);
      if(y>0) neighbors.push(position-width);
      if(y+1<height) neighbors.push(position+width);
      for(const n of neighbors) if(!visited[n] && labels[n]===color) {visited[n]=1;queue.push(n);}
    }
    observed[COLORS[color-1]].push({left,top,right,bottom,pixels:points.length,shape:classify(points,left,top,right,bottom)});
  }
  return observed;
}

function validObservations(observed) {
  if (!observed || typeof observed !== 'object' || Array.isArray(observed) || Object.keys(observed).sort().join(',') !== 'blue,green,red') return false;
  let count=0;
  for(const color of COLORS) {
    if(!Array.isArray(observed[color])) return false;
    count+=observed[color].length;
    if(count>1024) return false;
    for(const row of observed[color]) {
      if(!row || typeof row !== 'object' || Object.keys(row).sort().join(',')!=='bottom,left,pixels,right,shape,top') return false;
      if(!['left','top','right','bottom'].every(k=>Number.isInteger(row[k]) && row[k]>=0 && row[k]<=256)) return false;
      const width=row.right-row.left,height=row.bottom-row.top;
      if(width<=0 || height<=0 || !Number.isInteger(row.pixels) || row.pixels<1 || row.pixels>width*height || !SHAPES.has(row.shape)) return false;
      if(['square','rectangle'].includes(row.shape) && row.pixels!==width*height) return false;
      if(row.shape==='square' && width!==height) return false;
    }
  }
  return true;
}

export function verifyAnswer(observed, taskType, answer) {
  const claimed=typeof answer==='string' ? answer.trim().toLowerCase() : null;
  const result=(expected,reason)=>({status:expected===null?'abstained':claimed===expected?'verified':'contradicted',expected,claimed,reason,evidence:{components:observed}});
  if(!validObservations(observed)) return {status:'abstained',expected:null,claimed,reason:'invalid_observation',evidence:{}};
  const countTask=['count-green-squares','count-blue-circles'].includes(taskType);
  const colorTask=['color-square','color-circle','tallest'].includes(taskType);
  if (countTask ? !(/^(0|[1-9][0-9]{0,3})$/.test(claimed ?? '') && Number(claimed)<=1024) :
      colorTask ? !COLORS.includes(claimed) : taskType==='relation-left' ? !['left','right'].includes(claimed) : true) {
    return result(null,'unsupported_answer_or_question');
  }
  const all=COLORS.flatMap(color=>observed[color].map(row=>({color,...row})));
  if(taskType==='color-square' || taskType==='color-circle') {
    if(all.some(row=>row.shape==='unknown')) return result(null,'unknown_color_candidate');
    const candidates=all.filter(row=>row.shape===(taskType==='color-square'?'square':'circle'));
    return candidates.length===1 ? result(candidates[0].color,'unique_shape_color') : result(null,'ambiguous_color');
  }
  if(countTask) {
    const color=taskType==='count-green-squares'?'green':'blue', shape=color==='green'?'square':'circle';
    if(observed[color].some(row=>row.shape==='unknown')) return result(null,'unknown_count_shape');
    return result(String(observed[color].filter(row=>row.shape===shape).length),'exact_component_count');
  }
  if(taskType==='relation-left') {
    if([...observed.red,...observed.blue].some(row=>row.shape==='unknown')) return result(null,'unknown_relation_shape');
    const subjects=observed.red.filter(row=>row.shape==='square'), objects=observed.blue.filter(row=>row.shape==='circle');
    if(subjects.length!==1 || objects.length!==1) return result(null,'ambiguous_relation');
    const subject=subjects[0],object=objects[0];
    if(subject.right<=object.left) return result('left','disjoint_horizontal_bounds');
    if(subject.left>=object.right) return result('right','disjoint_horizontal_bounds');
    return result(null,'overlapping_horizontal_bounds');
  }
  if(all.some(row=>row.shape==='unknown')) return result(null,'unknown_bar_candidate');
  const bars=all.filter(row=>['square','rectangle'].includes(row.shape));
  if(bars.length<2) return result(null,'insufficient_bars');
  if(new Set(bars.map(row=>row.bottom)).size!==1) return result(null,'nonaligned_bars');
  const ordered=[...bars].sort((a,b)=>a.left-b.left);
  if(ordered.some((row,i)=>i>0 && ordered[i-1].right>row.left)) return result(null,'overlapping_bars');
  const tallest=Math.max(...bars.map(row=>row.bottom-row.top));
  const winners=bars.filter(row=>row.bottom-row.top===tallest);
  return winners.length===1 ? result(winners[0].color,'unique_tallest_bar') : result(null,'tied_bars');
}
