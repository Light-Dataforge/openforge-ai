import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {observePixels,verifyAnswer} from './verifier.mjs';

test('browser geometry agrees with Python on all six original fixture scenes',()=>{
 const code=`
import json,tempfile
from pathlib import Path
from core.multimodal.fixtures import generate_fixtures
from core.verification.raster import observe,decode_rgb_png
from core.verification.claims import verify_claim
from apps.verification_demo.runner import claim_for
kinds=['color-square','color-circle','count-green-squares','count-blue-circles','relation-left','tallest']
with tempfile.TemporaryDirectory() as tmp:
 manifest=generate_fixtures(Path(tmp)/'fixtures')
 rows=[json.loads(x) for x in manifest.read_text().splitlines()]
 result=[]
 for row,kind in zip(rows,kinds,strict=True):
  raw=(manifest.parent/row['image']).read_bytes()
  width,height,rgb=decode_rgb_png(raw)
  rgba=[]
  for i in range(0,len(rgb),3):rgba.extend([*rgb[i:i+3],255])
  correct=row['answer']
  wrong=('0' if kind.startswith('count-') else 'right' if kind=='relation-left' else 'red' if correct=='blue' else 'blue')
  checks=[{'candidate':candidate,'result':verify_claim(raw,claim_for(row['question'],candidate))} for candidate in [correct,wrong]]
  result.append({'kind':kind,'width':width,'height':height,'rgba':rgba,'observed':observe(raw),'checks':checks})
 print(json.dumps(result))
`;
 const root=fileURLToPath(new URL('../',import.meta.url));
 const process=spawnSync('python3',['-c',code],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024});
 assert.equal(process.status,0,process.stderr);
 const cases=JSON.parse(process.stdout);assert.equal(cases.length,6);
 for(const row of cases) {
  const observed=observePixels(new Uint8ClampedArray(row.rgba),row.width,row.height);
  assert.deepEqual(observed,row.observed,row.kind);
  for(const check of row.checks) {
   const actual=verifyAnswer(observed,row.kind,check.candidate);
   for(const key of ['status','expected','claimed','reason'])assert.equal(actual[key],check.result[key],`${row.kind}: ${key}`);
  }
 }
});
