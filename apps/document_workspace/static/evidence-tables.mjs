// Saved evidence workflow; all source content is rendered as text.
const locationLabel=doc=>/\.pdf$/i.test(doc.name||doc.document_name||'')?'page':'section';
export function evidenceTables({api, esc, uid, openCitation, isActive}) {
  let projectId = null, tables = [], active = null, editing = false, loading = false, error = '', busy = false;
  let draft = {title:'', questions:'', documents:[]};
  const reviewNames = {unreviewed:'Not reviewed', supported:'Supported · your review', unclear:'Needs follow-up'};
  let root, documents;
  const current = id => projectId === id && isActive(id);
  const endpoint = () => `/api/projects/${uid(projectId)}/tables`;
  async function load() {
    const id = projectId; loading = true; render();
    try {const result = await api(endpoint()); if(projectId===id) tables = result.tables;}
    catch(e) {if(projectId===id) error=e.message;}
    finally {if(projectId===id){loading=false; render();}}
  }
  async function open(id) {
    const owner = projectId; loading=true; error=''; render();
    try {const result=await api(`${endpoint()}/${uid(id)}`); if(projectId===owner){active=result.table; editing=false;}}
    catch(e){if(projectId===owner)error=e.message;}
    finally {if(projectId===owner){loading=false;render();}}
  }
  function newTable() {editing=true;active=null;error='';draft={title:'',questions:'',documents:documents.slice(0,10).map(d=>d.id)};render();}
  function capture() {
    draft={title:root.querySelector('#table-title').value, questions:root.querySelector('#table-questions').value,
      documents:[...root.querySelectorAll('[name="table-document"]:checked')].map(el=>el.value)};
  }
  async function create(event) {
    event.preventDefault();capture();const owner=projectId;busy=true;error='';render();
    try {
      const result=await api(endpoint(),{method:'POST',body:{title:draft.title,document_ids:draft.documents,
        questions:draft.questions.split('\n').map(s=>s.trim()).filter(Boolean)}});
      if(projectId===owner){active=result.table;editing=false;tables=[active,...tables];}
    } catch(e){if(projectId===owner)error=e.message;}
    finally {if(projectId===owner){busy=false;render();}}
  }
  function editCell(cell) {
    const dialog=document.createElement('dialog');dialog.className='evidence-dialog';
    dialog.innerHTML=`<form><h2>Review this evidence</h2><p>${esc(active.columns[cell.column])}</p>
      <label>Your finding<textarea name="finding" rows="5" maxlength="3000" placeholder="Write a conclusion or a question to investigate">${esc(cell.finding)}</textarea></label>
      <label>Review label<select name="review">${Object.entries(reviewNames).map(([value,label])=>`<option value="${value}" ${cell.review===value?'selected':''} ${value==='supported'&&!cell.sources.length?'disabled':''}>${label}</option>`).join('')}</select></label>
      <p>Review labels are your assessment. Retrieved passages are not verified answers.</p><p role="alert" class="evidence-error"></p>
      <div class="evidence-actions"><button type="button" class="secondary-button" data-cancel>Cancel</button><button class="primary-button" type="submit">Save finding</button></div></form>`;
    document.body.append(dialog);dialog.showModal();dialog.addEventListener('close',()=>dialog.remove());
    dialog.querySelector('[data-cancel]').addEventListener('click',()=>dialog.close());
    dialog.querySelector('textarea').focus();
    dialog.querySelector('form').addEventListener('submit',async event=>{
      event.preventDefault();const owner=projectId, tableId=active.id, revision=active.revision;
      const save=dialog.querySelector('[type="submit"]');save.disabled=true;
      try {
        const data=await api(`${endpoint()}/${uid(tableId)}/cell`,{method:'POST',body:{
          document_id:cell.document_id,column:cell.column,revision,
          finding:dialog.querySelector('textarea').value,review:dialog.querySelector('select').value}});
        if(projectId===owner&&active?.id===tableId){active=data.table;render();}dialog.close();
      }catch(e){dialog.querySelector('[role="alert"]').textContent=e.message;save.disabled=false;}
    });
  }
  function render() {
    if(!current(projectId))return;
    root.innerHTML=`<div class="page-title"><div><p class="eyebrow">RESEARCH WORKSPACE</p><h1>${active&&!editing?esc(active.title):'Evidence tables'}</h1><p>Bring questions, documents, source passages, and your findings together.</p></div><button class="primary-button" id="table-new" ${busy||loading?'disabled':''}>New evidence table</button></div>`;
    root.querySelector('#table-new').addEventListener('click',newTable);
    if(error)root.insertAdjacentHTML('beforeend',`<p class="evidence-error" role="alert">${esc(error)}</p>`);
    if(loading){root.insertAdjacentHTML('beforeend','<p role="status">Opening your evidence tables…</p>');return;}
    if(editing){renderForm();return;}
    if(active){renderTable();return;}
    root.insertAdjacentHTML('beforeend',`<div class="evidence-intro"><h2>A research question for every column.</h2><p>Compare up to 10 documents across 6 questions. Collect relevant passages, follow their page citations, and record your own review. Tables remain available after you close the app.</p><div class="evidence-steps"><span>1 · Choose documents</span><span>2 · Gather passages</span><span>3 · Review and export</span></div></div><div class="evidence-saved">${tables.map(t=>`<button class="evidence-saved-card" data-table="${esc(t.id)}"><strong>${esc(t.title)}</strong><small>Saved ${esc(new Date(t.updated_at).toLocaleDateString())}</small><span>Open table →</span></button>`).join('')||'<p>No saved tables yet. Start with a question you want to investigate across your documents.</p>'}</div>`);
    root.querySelectorAll('[data-table]').forEach(button=>button.addEventListener('click',()=>open(button.dataset.table)));
  }
  function renderForm() {
    if(!documents.length){root.insertAdjacentHTML('beforeend','<p>Add documents to this project before creating an evidence table.</p>');return;}
    root.insertAdjacentHTML('beforeend',`<form id="table-create" class="evidence-builder"><div><h2>Set up your research</h2><label>Table name<input id="table-title" maxlength="100" required value="${esc(draft.title)}" placeholder="For example: Vendor policy review" ${busy?'disabled':''}></label><label>Research questions <small>One per line · up to 6</small><textarea id="table-questions" rows="6" maxlength="1805" required placeholder="What is the refund policy?&#10;How is customer data retained?" ${busy?'disabled':''}>${esc(draft.questions)}</textarea></label><div class="evidence-presets"><span>Start with:</span><button type="button" data-preset="papers" ${busy?'disabled':''}>Research papers</button><button type="button" data-preset="policies" ${busy?'disabled':''}>Policies</button></div></div><fieldset><legend>Documents <small>Choose 1–10</small></legend>${documents.map(d=>`<label class="evidence-document"><input type="checkbox" name="table-document" value="${esc(d.id)}" ${draft.documents.includes(d.id)?'checked':''} ${busy?'disabled':''}><span>${esc(d.name)}<small>${d.pages} ${locationLabel(d)}${d.pages===1?'':'s'}</small></span></label>`).join('')}</fieldset><div class="evidence-builder-footer"><p>Uses keyword search to collect up to two passages per cell. Matches may be incomplete or irrelevant; review the cited pages. No model or cloud request is needed.</p><div class="evidence-actions"><button class="secondary-button" type="button" id="table-cancel" ${busy?'disabled':''}>Back to tables</button><button class="primary-button" ${busy?'disabled':''}>${busy?'Gathering evidence…':'Build evidence table'}</button></div></div></form>`);
    root.querySelector('#table-create').addEventListener('submit',create);
    root.querySelector('#table-cancel').addEventListener('click',()=>{editing=false;render();});
    root.querySelectorAll('[data-preset]').forEach(button=>button.addEventListener('click',()=>{
      capture();const papers=button.dataset.preset==='papers';
      draft.title=draft.title||(papers?'Literature review':'Policy comparison');
      draft.questions=papers?'What research question is studied?\nWhat methods are used?\nWhat results are reported?\nWhat limitations are described?':'What is the refund policy?\nHow is data retained?\nWhat support is provided?';render();
    }));
  }
  function renderTable() {
    const reviewed=active.cells.filter(c=>c.review!=='unreviewed').length, matched=active.cells.filter(c=>c.sources.length).length;
    const created=new Date(active.created_at).toLocaleString();
    root.insertAdjacentHTML('beforeend',`<div class="evidence-toolbar"><button class="secondary-button" id="table-back">All tables</button><span>${active.documents.length} documents · ${active.columns.length} questions · ${reviewed}/${active.cells.length} reviewed</span><a class="primary-button" href="${endpoint()}/${uid(active.id)}/export" download="evidence-table.csv">Export CSV</a></div><p class="evidence-caption">Saved source snapshot · ${esc(created)} · ${matched}/${active.cells.length} cells have keyword matches. No match does not establish that information is absent.</p><div class="evidence-scroll" role="region" aria-label="Evidence table" tabindex="0"><table class="evidence-grid"><thead><tr><th scope="col">Document</th>${active.columns.map(q=>`<th scope="col">${esc(q)}</th>`).join('')}</tr></thead><tbody>${active.documents.map(doc=>`<tr><th scope="row">${esc(doc.name)}<small>${doc.pages} ${locationLabel(doc)}${doc.pages===1?'':'s'}</small></th>${active.columns.map((_,column)=>{
      const index=active.cells.findIndex(c=>c.document_id===doc.id&&c.column===column),cell=active.cells[index];
      return `<td><span class="evidence-review review-${cell.review}">${reviewNames[cell.review]}</span>${cell.finding?`<p class="evidence-finding">${esc(cell.finding)}</p>`:''}${cell.sources.map((source,i)=>`<div class="evidence-passage"><p>${esc(source.text)}</p><button class="text-button" data-source="${index}:${i}">Inspect ${locationLabel(source)} ${source.page} →</button></div>`).join('')||'<p class="evidence-missing">No matching passage found. Inspect the document or try a different question in a new table.</p>'}<button class="secondary-button" data-cell="${index}">${cell.finding?'Edit finding':'Add finding / review'}</button></td>`;
    }).join('')}</tr>`).join('')}</tbody></table></div><p class="evidence-caption">Review labels are your assessment. This is a snapshot of retrieved passages, not an automated claim verification.</p>`);
    root.querySelector('#table-back').addEventListener('click',()=>{active=null;load();});
    root.querySelectorAll('[data-source]').forEach(button=>button.addEventListener('click',()=>{const [cell,source]=button.dataset.source.split(':').map(Number);openCitation(active.cells[cell].sources[source]);}));
    root.querySelectorAll('[data-cell]').forEach(button=>button.addEventListener('click',()=>editCell(active.cells[Number(button.dataset.cell)])));
  }
  return {mount(element,id,docs){
    root=element;documents=docs;
    if(projectId!==id){projectId=id;tables=[];active=null;editing=false;error='';busy=false;loading=false;load();}
    else render();
  }};
}
