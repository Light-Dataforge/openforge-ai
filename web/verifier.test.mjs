import test from 'node:test';
import assert from 'node:assert/strict';
import {observePixels,verifyAnswer} from './verifier.mjs';
const color={red:[220,30,30],green:[20,150,50],blue:[30,70,220]};
function raster(width=24,height=20) {
 const data=new Uint8ClampedArray(width*height*4);data.fill(255);
 const dot=(x,y,c)=>data.set([...color[c],255],(y*width+x)*4);
 const rect=(left,top,w,h,c)=>{for(let y=top;y<top+h;y++)for(let x=left;x<left+w;x++)dot(x,y,c);};
 const circle=(cx,cy,r,c)=>{for(let y=cy-r;y<=cy+r;y++)for(let x=cx-r;x<=cx+r;x++)if((x-cx)**2+(y-cy)**2<=r*r)dot(x,y,c);};
 return {data,width,height,dot,rect,circle,observe:()=>observePixels(data,width,height)};
}
test('actual pixels identify a square, independent of claimed color',()=>{
 const r=raster();r.rect(2,3,5,5,'red');const observed=r.observe();
 assert.deepEqual(observed.red,[{left:2,top:3,right:7,bottom:8,pixels:25,shape:'square'}]);
 assert.equal(verifyAnswer(observed,'color-square',' RED ').status,'verified');
 assert.equal(verifyAnswer(observed,'color-square','blue').status,'contradicted');
});
test('lattice circles and separated components yield counts',()=>{
 const r=raster();r.circle(4,4,2,'blue');r.circle(14,4,3,'blue');r.rect(2,12,2,2,'green');r.rect(8,12,2,2,'green');
 const observed=r.observe();assert.deepEqual(observed.blue.map(x=>x.shape),['circle','circle']);
 assert.equal(verifyAnswer(observed,'count-blue-circles','2').status,'verified');
 assert.equal(verifyAnswer(observed,'count-green-squares','3').status,'contradicted');
 assert.equal(verifyAnswer(observed,'count-green-squares','3').expected,'2');
});
test('unknown geometry abstains conservatively',()=>{
 const r=raster();r.dot(2,2,'red');r.dot(3,2,'red');r.dot(2,3,'red');
 assert.equal(r.observe().red[0].shape,'unknown');
 assert.equal(verifyAnswer(r.observe(),'color-square','red').status,'abstained');
});
test('unsupported palette, transparency and size reject before observations',()=>{
 const r=raster();r.data.set([1,2,3,255],0);assert.throws(()=>r.observe(),/palette/);
 r.data.set([255,255,255,0],0);assert.throws(()=>r.observe(),/Transparent/);
 assert.throws(()=>observePixels(r.data,257,20),/dimensions/);
 assert.throws(()=>observePixels(new Uint8Array(4),2,2),/complete/);
});
test('horizontal relation uses disjoint component bounds',()=>{
 const r=raster();r.rect(2,4,3,3,'red');r.circle(16,5,2,'blue');
 assert.equal(verifyAnswer(r.observe(),'relation-left','left').status,'verified');
 assert.equal(verifyAnswer(r.observe(),'relation-left','right').status,'contradicted');
});
test('tallest bars require aligned bottoms and a unique winner',()=>{
 const r=raster();r.rect(2,10,3,8,'red');r.rect(10,5,3,13,'blue');
 assert.equal(verifyAnswer(r.observe(),'tallest','blue').status,'verified');
 const tied=raster();tied.rect(2,5,3,13,'red');tied.rect(10,5,3,13,'blue');
 assert.equal(verifyAnswer(tied.observe(),'tallest','blue').reason,'tied_bars');
 const uneven=raster();uneven.rect(2,5,3,5,'red');uneven.rect(10,5,3,7,'blue');
 assert.equal(verifyAnswer(uneven.observe(),'tallest','blue').reason,'nonaligned_bars');
});
test('ambiguous shapes, narrative answers and invalid observations abstain',()=>{
 const r=raster();r.rect(2,2,3,3,'red');r.rect(10,2,3,3,'blue');
 assert.equal(verifyAnswer(r.observe(),'color-square','red').reason,'ambiguous_color');
 assert.equal(verifyAnswer(r.observe(),'color-square','The square is red.').reason,'unsupported_answer_or_question');
 assert.equal(verifyAnswer(r.observe(),'count-green-squares','01').status,'abstained');
 assert.equal(verifyAnswer(r.observe(),'count-green-squares','1025').status,'abstained');
 assert.equal(verifyAnswer({},'color-square','red').reason,'invalid_observation');
});
