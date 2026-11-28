import {test} from 'node:test';
import assert from 'node:assert/strict';
import {citedSources, answerNote} from '../../apps/document_workspace/static/citations.mjs';
const sources = [1,2,3].map(page => ({document_id:'doc-'+page, document_name:'Document '+page, page}));
test('sparse references keep their original source index and deduplicate cards', () => {
  assert.deepEqual(citedSources('Evidence [3], repeated [3], and [1].',sources).map(x=>[x.index,x.number]),[[0,1],[2,3]]);
});
test('invalid or absent reference markers never create source cards', () => {
  assert.deepEqual(citedSources('Unknown [0] [99].',sources),[]);
  assert.deepEqual(citedSources('No references.',sources),[]);
});
test('single cited source sets the correct note page instead of the first retrieved page', () => {
  const note=answerNote('Finding [3].',sources);
  assert.equal(note.source.document_id,'doc-3');
  assert.match(note.text,/\[3\] Document 3 — page 3/);
});
test('multi-source notes retain all references without a misleading single-page association', () => {
  const note=answerNote('Findings [1] [3].',sources);
  assert.equal(note.source.document_id,null);
  assert.match(note.text,/Document 1 — page 1/);
  assert.match(note.text,/Document 3 — page 3/);
  assert.doesNotMatch(note.text,/Document 2/);
});

test('Word and text note references use sections instead of original pages', () => {
  for (const name of ['Policy.docx','Research.md','Notes.txt']) {
    const note = answerNote('Finding [1]', [{document_id:'doc',document_name:name,page:2}]);
    assert.match(note.text, /section 2/);
    assert.doesNotMatch(note.text, /page 2/);
  }
});
