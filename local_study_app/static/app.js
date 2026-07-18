const app = document.querySelector('#app');
const modal = document.querySelector('#modal');
const modalContent = document.querySelector('#modal-content');
const toastEl = document.querySelector('#toast');
const state = { decks: [], folders: [], activeDeck: null, cards: [], flash: null, session: null, timer: null, match: null };

const icons = { flashcards:'▣', learn:'◎', write:'✎', spell:'♫', test:'✓', match:'⌁' };

async function api(url, options={}) {
  const init = {...options, headers:{...(options.body && !(options.body instanceof FormData) ? {'Content-Type':'application/json'} : {}), ...(options.headers||{})}};
  const response = await fetch(url, init);
  const result = await response.json();
  if (result && result.success === false) throw Object.assign(new Error(result.error?.message || 'Something went wrong'), {result});
  return result?.data !== undefined ? result.data : result;
}

function esc(value='') { return String(value).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function toast(message, error=false) { toastEl.textContent=message; toastEl.className=`toast show${error?' error':''}`; clearTimeout(toastEl.timer); toastEl.timer=setTimeout(()=>toastEl.className='toast',2800); }
function loading(){ app.innerHTML='<div class="loading"><span></span><p>Growing your study space…</p></div>'; }
function formatDate(value){ if(!value) return '—'; return new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date(value)); }
function formatTime(ms){ if(ms==null) return '—'; const seconds=ms/1000; return seconds<60?`${seconds.toFixed(1)}s`:`${Math.floor(seconds/60)}m ${(seconds%60).toFixed(0)}s`; }
function formatDuration(ms){const minutes=Math.max(0,Math.round((ms||0)/60000));return minutes<60?`${minutes}m`:`${Math.floor(minutes/60)}h ${minutes%60}m`}
function route(path){ location.hash=path; }
function openModal(html){ modalContent.innerHTML=html; modal.showModal(); }
function closeModal(){ modal.close(); modalContent.innerHTML=''; }
function formData(form){ return Object.fromEntries(new FormData(form).entries()); }
function parseList(value){ return String(value||'').split(/[|\n]/).map(x=>x.trim()).filter(Boolean); }

document.querySelectorAll('[data-route]').forEach(button=>button.addEventListener('click',()=>route(button.dataset.route)));
document.querySelector('#quick-create').addEventListener('click',showCreateDeck);
document.querySelector('.modal-close').addEventListener('click',closeModal);
modal.addEventListener('click',event=>{ if(event.target===modal) closeModal(); });
let flashTouchX=null;
app.addEventListener('touchstart',event=>{if(event.target.closest('#flashcard'))flashTouchX=event.changedTouches[0].clientX},{passive:true});
app.addEventListener('touchend',event=>{if(flashTouchX===null||!event.target.closest('#flashcard'))return;const delta=event.changedTouches[0].clientX-flashTouchX;flashTouchX=null;if(Math.abs(delta)>45)flashMove(delta<0?1:-1)},{passive:true});
window.addEventListener('hashchange',renderRoute);
window.addEventListener('keydown',event=>{
  if(!state.flash || ['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName)) return;
  if(event.key==='ArrowRight') flashMove(1);
  if(event.key==='ArrowLeft') flashMove(-1);
  if(event.key===' '){ event.preventDefault(); flipCard(); }
  if(['1','2','3','4'].includes(event.key)) rateFlash(['again','hard','good','easy'][Number(event.key)-1]);
});

async function renderRoute(){
  clearInterval(state.timer); state.timer=null;
  document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',location.hash.includes(x.dataset.route)));
  const [name,id] = (location.hash.slice(1)||'dashboard').split('/');
  loading();
  try {
    if(name==='dashboard') await renderDashboard();
    else if(name==='library') await renderLibrary();
    else if(name==='folders') await renderFolders();
    else if(name==='progress') await renderProgress();
    else if(name==='deck') await renderDeck(Number(id));
    else if(name==='flashcards') await renderFlashcards(Number(id));
    else if(['learn','write','spell'].includes(name)) await configureStudy(Number(id),name);
    else if(name==='test') await configureTest(Number(id));
    else if(name==='match') await renderMatch(Number(id));
    else route('dashboard');
  } catch(error){ renderError(error); }
}

function renderError(error){
  app.innerHTML=`<section class="panel empty"><div class="emoji">🌧️</div><h2>That didn’t grow as planned</h2><p class="muted">${esc(error.message)}</p><button class="primary" id="back-home">Return home</button></section>`;
  document.querySelector('#back-home').onclick=()=>route('dashboard');
}

async function renderDashboard(){
  const [decks,progress,activity] = await Promise.all([api('/api/decks'),api('/api/progress'),api('/api/activity?limit=6')]);
  state.decks=decks;
  app.innerHTML=`
    <section class="hero"><div><p class="eyebrow" style="color:#fff">Your private study garden</p><h1>Small sessions.<br>Big growth.</h1><p>Build focused decks, learn adaptively, test yourself, and turn recall into a game—all on this computer.</p><div class="actions"><button class="primary" id="hero-create">Create a deck</button><button class="ghost" style="color:white;border-color:#ffffff66" id="review-due">Review ${progress.due} due</button></div></div><div class="hero-art" aria-hidden="true">🌱</div></section>
    <section class="stats" aria-label="Study statistics">${stat(progress.total_cards,'Cards')}${stat(progress.due,'Due now')}${stat(progress.mastered,'Mastered')}${stat(`${progress.accuracy}%`,'Accuracy')}${stat(progress.streak,'Day streak')}</section>
    <div class="section-head"><div><p class="eyebrow">Your library</p><h2>Pick up where you left off</h2></div><button class="secondary" id="all-decks">See all decks</button></div>
    <section class="deck-grid">${decks.slice(0,6).map(deckCard).join('') || emptyInline('No decks yet','Create your first deck to begin.')}</section>
    <div class="section-head"><div><p class="eyebrow">Recent activity</p><h2>Momentum matters</h2></div></div>
    <section class="panel activity-list">${activity.map(activityRow).join('') || '<p class="muted">Your completed sessions will appear here.</p>'}</section>`;
  bindDeckCards();
  document.querySelector('#hero-create').onclick=showCreateDeck;
  document.querySelector('#all-decks').onclick=()=>route('library');
  document.querySelector('#review-due').onclick=async()=>{ const due=await api('/api/due?limit=1'); if(due.length) route(`flashcards/${due[0].deck_id}`); else toast('You are all caught up!'); };
}

function stat(value,label){ return `<article class="stat"><b>${esc(value)}</b><span>${esc(label)}</span></article>`; }
function activityRow(item){ return `<div class="activity"><div><strong>${esc(item.kind.replaceAll('_',' '))}</strong><div class="muted">${esc(item.deck_title||item.detail)}</div></div><time class="muted">${formatDate(item.happened_at)}</time></div>`; }
function emptyInline(title,copy){ return `<article class="panel empty" style="grid-column:1/-1"><div class="emoji">🌿</div><h3>${title}</h3><p class="muted">${copy}</p></article>`; }

function deckCard(deck){
  const pct=deck.card_count?Math.round(deck.mastered_count/deck.card_count*100):0;
  return `<article class="deck-card" data-deck="${deck.id}"><button class="deck-open" aria-label="Open ${esc(deck.title)}"></button><span class="pill">${deck.card_count} cards</span><h3>${esc(deck.title)}</h3><p class="muted">${esc(deck.description||'Ready for a fresh study session.')}</p><div class="progress-track" aria-label="${pct}% mastered"><span style="width:${pct}%"></span></div><div class="deck-meta"><span>${deck.mastered_count} mastered</span><span>★ ${deck.starred_count}</span></div></article>`;
}
function bindDeckCards(){ document.querySelectorAll('.deck-card .deck-open').forEach(button=>button.onclick=()=>route(`deck/${button.parentElement.dataset.deck}`)); }

async function renderLibrary(){
  const [decks,folders]=await Promise.all([api('/api/decks'),api('/api/folders')]); state.decks=decks; state.folders=folders;
  app.innerHTML=`<div class="section-head"><div><p class="eyebrow">Library</p><h1>Everything you’re learning</h1></div><div class="actions"><button class="secondary" id="combine">Combine decks</button><button class="primary" id="create-deck">＋ New deck</button></div></div>
    <div class="toolbar"><input class="search" id="deck-search" type="search" placeholder="Search decks, cards, or tags…"><select id="folder-filter" class="search" style="max-width:230px"><option value="">All folders</option>${folders.map(x=>`<option value="${x.id}">${esc(x.title)}</option>`).join('')}</select></div>
    <section id="deck-results" class="deck-grid">${decks.map(deckCard).join('')||emptyInline('A blank garden','Create or import a deck to start studying.')}</section>`;
  bindDeckCards(); document.querySelector('#create-deck').onclick=showCreateDeck; document.querySelector('#combine').onclick=showCombine;
  let searchTimer; document.querySelector('#deck-search').oninput=event=>{clearTimeout(searchTimer); searchTimer=setTimeout(()=>filterLibrary(event.target.value),180)};
  document.querySelector('#folder-filter').onchange=event=>filterLibrary(document.querySelector('#deck-search').value,event.target.value);
}

async function filterLibrary(query='',folderId=''){
  const decks=await api(`/api/decks?q=${encodeURIComponent(query)}${folderId?`&folder_id=${folderId}`:''}`); document.querySelector('#deck-results').innerHTML=decks.map(deckCard).join('')||emptyInline('Nothing found','Try a different search or folder.'); bindDeckCards();
}

function showCreateDeck(){
  openModal(`<p class="eyebrow">New study set</p><h2>Create a deck</h2><form id="deck-form"><div class="field"><label>Title</label><input name="title" required maxlength="160" autofocus placeholder="e.g. Anatomy midterm"></div><div class="field"><label>Description</label><textarea name="description" placeholder="What will this deck help you learn?"></textarea></div><div class="two-col"><div class="field"><label>Term language</label>${languageSelect('term_language')}</div><div class="field"><label>Definition language</label>${languageSelect('definition_language')}</div></div><button class="primary" type="submit">Create deck</button></form>`);
  document.querySelector('#deck-form').onsubmit=async event=>{ event.preventDefault(); try{const data=formData(event.target);const created=await api('/api/decks',{method:'POST',body:JSON.stringify(data)});closeModal();toast('Deck created');route(`deck/${created.id}`)}catch(error){toast(error.message,true)}};
}
function languageSelect(name,value='auto'){ return `<select name="${name}">${[['auto','Auto detect'],['en','English'],['es','Spanish'],['fr','French'],['de','German'],['it','Italian'],['pt','Portuguese'],['other','Other']].map(([v,l])=>`<option value="${v}" ${v===value?'selected':''}>${l}</option>`).join('')}</select>`; }

function showCombine(){
  if(state.decks.length<2){toast('Create at least two decks first',true);return}
  openModal(`<p class="eyebrow">Mix topics</p><h2>Combine decks</h2><form id="combine-form"><div class="field"><label>Choose at least two decks</label>${state.decks.map(x=>`<label><input type="checkbox" name="deck" value="${x.id}"> ${esc(x.title)}</label>`).join('')}</div><div class="field"><label>New deck title</label><input name="title" placeholder="Combined review"></div><button class="primary">Create combined deck</button></form>`);
  document.querySelector('#combine-form').onsubmit=async event=>{event.preventDefault();const ids=[...event.target.querySelectorAll('[name=deck]:checked')].map(x=>Number(x.value));try{const result=await api('/api/decks/combine',{method:'POST',body:JSON.stringify({deck_ids:ids,title:event.target.title.value||null,persist:true})});closeModal();toast('Combined deck created');route(`deck/${result.id}`)}catch(error){toast(error.message,true)}};
}

async function renderDeck(deckId){
  const [deck,cards,folders]=await Promise.all([api(`/api/decks/${deckId}`),api(`/api/decks/${deckId}/cards`),api('/api/folders')]); state.activeDeck=deck;state.cards=cards;state.folders=folders;
  const pct=deck.card_count?Math.round(deck.mastered_count/deck.card_count*100):0;
  app.innerHTML=`<section class="deck-header"><div><button class="ghost compact" id="back-library">← Library</button><p class="eyebrow" id="deck-card-count" style="margin-top:22px">${deck.card_count} cards · ${pct}% mastered</p><h1>${esc(deck.title)}</h1><p class="muted">${esc(deck.description||'Add a description to remember what this deck is for.')}</p></div><div class="actions"><button class="secondary" id="edit-deck">Edit details</button><button class="secondary" id="duplicate-deck">Duplicate</button><button class="ghost" id="print-deck">Print</button><button class="danger" id="delete-deck">Delete</button></div></section>
    <section class="mode-grid" aria-label="Study modes">${['flashcards','learn','write','spell','test','match'].map(mode=>`<button class="mode" data-mode="${mode}"><span>${icons[mode]}</span>${mode[0].toUpperCase()+mode.slice(1)}</button>`).join('')}</section>
    <section class="panel card-editor-panel"><div class="section-head" style="margin-top:0"><div><p class="eyebrow">Cards</p><h2>Front and back</h2><p class="muted">Type directly into each row. Changes save automatically.</p></div></div><div class="toolbar"><input id="card-search" class="search" type="search" placeholder="Search this deck…"><button class="secondary" id="import-cards">Import</button><select id="export-format" class="search" style="max-width:130px"><option value="json">JSON</option><option value="csv">CSV</option><option value="text">Text</option></select><button class="secondary" id="export-cards">Export</button></div><div id="card-list" class="card-list">${renderCardRows(cards)}</div><div class="add-card-row"><button class="secondary" id="add-card">＋ Add card</button></div></section>`;
  document.querySelector('#back-library').onclick=()=>route('library'); document.querySelectorAll('[data-mode]').forEach(x=>x.onclick=()=>route(`${x.dataset.mode}/${deckId}`));
  document.querySelector('#add-card').onclick=addDraftCard; document.querySelector('#edit-deck').onclick=showEditDeck; document.querySelector('#duplicate-deck').onclick=duplicateActiveDeck; document.querySelector('#delete-deck').onclick=deleteActiveDeck; document.querySelector('#print-deck').onclick=()=>window.print();
  document.querySelector('#import-cards').onclick=()=>showImport(deckId); document.querySelector('#export-cards').onclick=exportActiveDeck;
  let timer; document.querySelector('#card-search').oninput=event=>{clearTimeout(timer);timer=setTimeout(async()=>{const cards=await api(`/api/decks/${deckId}/cards?q=${encodeURIComponent(event.target.value)}`);document.querySelector('#card-list').innerHTML=renderCardRows(cards);bindCardRows()},160)};
  bindCardRows();
}

function renderCardRows(cards){
  if(!cards.length)return '<div class="card-editor-empty">No cards yet. Add your first front and back below.</div>';
  return cards.map(card=>renderCardEditorRow(card,state.cards.findIndex(item=>item.id===card.id))).join('');
}

function renderCardEditorRow(card,index,isDraft=false){
  const number=index+1;
  return `<article class="card-editor-row${isDraft?' is-draft':''}" data-card="${card?.id||''}"><header class="card-row-head"><strong class="card-number">${number}</strong><span class="save-state" aria-live="polite">${isDraft?'Add both sides to save':'Saved'}</span><div class="row-actions"><button class="drag-handle" type="button" draggable="${isDraft?'false':'true'}" aria-label="Reorder card ${number}" title="Drag to reorder">☰</button><button class="row-delete" type="button" aria-label="Delete card ${number}" title="Delete card">⌫</button></div></header><div class="inline-card-field"><textarea rows="2" aria-label="Front" placeholder="Enter the front">${esc(card?.front||'')}</textarea><label>Front</label></div><div class="inline-card-field"><textarea rows="2" aria-label="Back" placeholder="Enter the back">${esc(card?.back||'')}</textarea><label>Back</label></div></article>`;
}

function setCardRowStatus(row,message,error=false){const status=row.querySelector('.save-state');status.textContent=message;status.classList.toggle('error',error)}
function resizeCardField(field){field.style.height='auto';field.style.height=`${Math.max(58,field.scrollHeight)}px`}
function refreshCardCount(){
  state.activeDeck.card_count=state.cards.length;
  const label=document.querySelector('#deck-card-count');
  if(label){const pct=state.cards.length?Math.round((state.activeDeck.mastered_count||0)/state.cards.length*100):0;label.textContent=`${state.cards.length} cards · ${pct}% mastered`}
}

function addDraftCard(){
  const search=document.querySelector('#card-search');
  if(search.value){search.value='';document.querySelector('#card-list').innerHTML=renderCardRows(state.cards);bindCardRows()}
  let row=document.querySelector('.card-editor-row.is-draft');
  if(!row){const list=document.querySelector('#card-list');list.querySelector('.card-editor-empty')?.remove();list.insertAdjacentHTML('beforeend',renderCardEditorRow(null,state.cards.length,true));row=list.lastElementChild;bindCardRows()}
  ([...row.querySelectorAll('textarea')].find(field=>!field.value.trim())||row.querySelector('textarea')).focus();
  row.scrollIntoView({behavior:'smooth',block:'center'});
}

async function saveCardRow(row){
  clearTimeout(row.saveTimer);
  const fields=row.querySelectorAll('textarea');
  const front=fields[0].value.trim(),back=fields[1].value.trim();
  if(!front||!back){setCardRowStatus(row,`${front?'Back':'Front'} required`);return}
  if(row.dataset.saving==='true'){row.dataset.pending='true';return}
  row.dataset.saving='true';row.dataset.pending='';setCardRowStatus(row,'Saving…');
  try{
    const id=Number(row.dataset.card);
    const saved=id?await api(`/api/cards/${id}`,{method:'PATCH',body:JSON.stringify({front,back})}):await api('/api/cards',{method:'POST',body:JSON.stringify({deck_id:state.activeDeck.id,front,back})});
    if(id){const card=state.cards.find(item=>item.id===id);if(card)Object.assign(card,saved)}else if(row.dataset.discarded==='true'){await api(`/api/cards/${saved.id}`,{method:'DELETE'});return}else{state.cards.push(saved);row.dataset.card=saved.id;row.classList.remove('is-draft');const handle=row.querySelector('.drag-handle');handle.draggable=true;refreshCardCount()}
    setCardRowStatus(row,'Saved');
    if(fields[0].value.trim()!==front||fields[1].value.trim()!==back)row.dataset.pending='true';
  }catch(error){setCardRowStatus(row,'Could not save',true);toast(error.message,true)}finally{
    row.dataset.saving='false';
    if(row.dataset.pending==='true'){row.dataset.pending='';row.saveTimer=setTimeout(()=>saveCardRow(row),100)}
  }
}

function bindCardRows(){
  document.querySelectorAll('.card-editor-row').forEach(row=>{
    if(row.dataset.bound==='true')return;row.dataset.bound='true';
    row.querySelectorAll('textarea').forEach(field=>{
      resizeCardField(field);
      field.addEventListener('input',()=>{resizeCardField(field);setCardRowStatus(row,'Unsaved');clearTimeout(row.saveTimer);row.saveTimer=setTimeout(()=>saveCardRow(row),650)});
      field.addEventListener('blur',()=>{if(row.saveTimer)saveCardRow(row)});
      field.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();saveCardRow(row).then(addDraftCard)}});
    });
    row.querySelector('.row-delete').onclick=async()=>{
      const id=Number(row.dataset.card);
      if(!id){row.dataset.discarded='true';clearTimeout(row.saveTimer);row.remove();if(!state.cards.length)document.querySelector('#card-list').innerHTML=renderCardRows([]);return}
      if(!confirm('Delete this card?'))return;
      try{await api(`/api/cards/${id}`,{method:'DELETE'});state.cards=state.cards.filter(card=>card.id!==id);document.querySelector('#card-list').innerHTML=renderCardRows(state.cards);bindCardRows();refreshCardCount();toast('Card deleted')}catch(error){toast(error.message,true)}
    };
    const handle=row.querySelector('.drag-handle');
    handle.ondragstart=event=>{const id=Number(row.dataset.card);if(!id){event.preventDefault();return}event.dataTransfer.setData('text/plain',String(id));event.dataTransfer.effectAllowed='move';row.classList.add('dragging')};
    handle.ondragend=()=>{row.classList.remove('dragging');document.querySelectorAll('.drag-over').forEach(item=>item.classList.remove('drag-over'))};
    handle.onkeydown=event=>{if(!event.altKey||!['ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();moveCard(Number(row.dataset.card),event.key==='ArrowUp'?-1:1)};
    row.ondragover=event=>{if(event.dataTransfer.types.includes('text/plain')){event.preventDefault();row.classList.add('drag-over')}};
    row.ondragleave=()=>row.classList.remove('drag-over');
    row.ondrop=event=>{event.preventDefault();row.classList.remove('drag-over');reorderCard(Number(event.dataTransfer.getData('text/plain')),Number(row.dataset.card))};
  });
}

async function persistCardOrder(){await api(`/api/decks/${state.activeDeck.id}/reorder`,{method:'POST',body:JSON.stringify({card_ids:state.cards.map(card=>card.id)})});document.querySelector('#card-list').innerHTML=renderCardRows(state.cards);bindCardRows()}
async function moveCard(id,delta){const index=state.cards.findIndex(card=>card.id===id),target=index+delta;if(index<0||target<0||target>=state.cards.length)return;[state.cards[index],state.cards[target]]=[state.cards[target],state.cards[index]];try{await persistCardOrder()}catch(error){toast(error.message,true);renderDeck(state.activeDeck.id)}}
async function reorderCard(id,targetId){if(!id||!targetId||id===targetId)return;const from=state.cards.findIndex(card=>card.id===id);let to=state.cards.findIndex(card=>card.id===targetId);if(from<0||to<0)return;const [card]=state.cards.splice(from,1);if(from<to)to-=1;state.cards.splice(to,0,card);try{await persistCardOrder()}catch(error){toast(error.message,true);renderDeck(state.activeDeck.id)}}

function showEditDeck(){const d=state.activeDeck;openModal(`<p class="eyebrow">Deck details</p><h2>Edit your deck</h2><form id="edit-deck-form"><div class="field"><label>Title</label><input name="title" required value="${esc(d.title)}"></div><div class="field"><label>Description</label><textarea name="description">${esc(d.description)}</textarea></div><div class="two-col"><div class="field"><label>Term language</label>${languageSelect('term_language',d.term_language)}</div><div class="field"><label>Definition language</label>${languageSelect('definition_language',d.definition_language)}</div></div><div class="field"><label>Folders</label>${state.folders.map(f=>`<label><input type="checkbox" name="folder" value="${f.id}" ${d.folder_ids.includes(f.id)?'checked':''}> ${esc(f.title)}</label>`).join('')||'<span class="muted">Create a folder from the Folders page.</span>'}</div><button class="primary">Save deck</button></form>`);document.querySelector('#edit-deck-form').onsubmit=async event=>{event.preventDefault();try{const data=formData(event.target);await api(`/api/decks/${d.id}`,{method:'PATCH',body:JSON.stringify({title:data.title,description:data.description,term_language:data.term_language,definition_language:data.definition_language})});const chosen=[...event.target.querySelectorAll('[name=folder]:checked')].map(x=>Number(x.value));for(const folder of state.folders)await api(`/api/folders/${folder.id}/decks`,{method:'POST',body:JSON.stringify({deck_id:d.id,included:chosen.includes(folder.id)})});closeModal();toast('Deck saved');renderDeck(d.id)}catch(error){toast(error.message,true)}}}

async function deleteActiveDeck(){if(!confirm(`Delete “${state.activeDeck.title}” and all of its cards? This cannot be undone.`))return;await api(`/api/decks/${state.activeDeck.id}`,{method:'DELETE'});toast('Deck deleted');route('library');}
async function duplicateActiveDeck(){try{const copy=await api(`/api/decks/${state.activeDeck.id}/duplicate`,{method:'POST',body:JSON.stringify({title:`${state.activeDeck.title} copy`})});toast('Deck duplicated');route(`deck/${copy.id}`)}catch(error){toast(error.message,true)}}

function showImport(deckId){openModal(`<p class="eyebrow">Bring your notes</p><h2>Import cards</h2><form id="import-form"><div class="field"><label>Format</label><select name="format"><option value="text">Separated text</option><option value="csv">CSV</option><option value="json">Study Sprout JSON</option></select></div><div class="field"><label>Paste terms and definitions</label><textarea name="payload" required style="min-height:220px" placeholder="Term&#9;Definition&#10;Another term&#9;Another definition"></textarea></div><div id="import-preview" class="muted"></div><div class="actions"><button type="button" class="secondary" id="preview-import">Preview</button><button class="primary">Import as a new deck</button></div></form>`);const form=document.querySelector('#import-form');document.querySelector('#preview-import').onclick=async()=>{try{const d=formData(form);const preview=await api('/api/import/preview',{method:'POST',body:JSON.stringify(d)});document.querySelector('#import-preview').innerHTML=`<div class="feedback good"><b>${preview.card_count} valid cards</b><br>${preview.cards.slice(0,3).map(x=>`${esc(x.front)} → ${esc(x.back)}`).join('<br>')}</div>`}catch(error){toast(error.message,true)}};form.onsubmit=async event=>{event.preventDefault();try{const d=formData(form);const result=await api('/api/import',{method:'POST',body:JSON.stringify({...d,title:`${state.activeDeck.title} Import`})});closeModal();toast(`${result.card_count} cards imported`);route(`deck/${result.deck_id}`)}catch(error){toast(error.message,true)}}}

async function exportActiveDeck(){try{const format=document.querySelector('#export-format').value;const data=await api(`/api/decks/${state.activeDeck.id}/export?format=${format}`);const link=document.createElement('a');link.href=data.download_url;link.download=data.filename;link.click();toast(`${format.toUpperCase()} export ready`)}catch(error){toast(error.message,true)}}

async function renderFlashcards(deckId,options={}){
  const [deck,cards]=await Promise.all([api(`/api/decks/${deckId}`),api(`/api/decks/${deckId}/cards${options.starred?'?starred=true':''}`)]);if(!cards.length){renderEmptyMode(deckId,'No cards to review');return}
  let saved=null;try{saved=JSON.parse(localStorage.getItem(`flash-session-${deckId}`)||'null')}catch(_error){saved=null}
  let ordered=options.shuffle?[...cards].sort(()=>Math.random()-.5):cards;
  if(saved?.card_ids?.length){const ranks=new Map(saved.card_ids.map((id,index)=>[id,index]));ordered=[...cards].sort((a,b)=>(ranks.get(a.id)??9999)-(ranks.get(b.id)??9999))}
  state.activeDeck=deck;state.cards=ordered;state.flash={index:Math.min(saved?.index||0,ordered.length-1),flipped:Boolean(saved?.flipped),orientation:saved?.orientation||options.orientation||'term',auto:false};renderFlashScreen();
}
function saveFlashState(){if(!state.flash||!state.activeDeck)return;localStorage.setItem(`flash-session-${state.activeDeck.id}`,JSON.stringify({card_ids:state.cards.map(x=>x.id),index:state.flash.index,flipped:state.flash.flipped,orientation:state.flash.orientation}))}
function renderFlashScreen(){const f=state.flash,c=state.cards[f.index],front=f.orientation==='term'?c.front:c.back,back=f.orientation==='term'?c.back:c.front;saveFlashState();app.innerHTML=`<section class="study-shell"><div class="study-top"><button class="ghost compact" id="exit-study">← ${esc(state.activeDeck.title)}</button><div class="progress-track"><span style="width:${((f.index+1)/state.cards.length)*100}%"></span></div><strong>${f.index+1} / ${state.cards.length}</strong></div><div class="toolbar"><button class="secondary" id="shuffle-flash">⇄ Shuffle</button><button class="secondary" id="orient-flash">↕ ${f.orientation==='term'?'Term first':'Definition first'}</button><button class="secondary" id="auto-flash">▶ Autoplay</button><button class="secondary" id="speak-flash">🔊 Speak</button><button class="star ${c.starred?'on':''}" id="star-flash" aria-label="Star card">★</button></div><div class="flashcard-wrap"><button class="flashcard ${f.flipped?'flipped':''}" id="flashcard"><span class="face front"><span class="card-label">${f.orientation==='term'?'Term':'Definition'}</span><span><span class="card-text">${esc(front)}</span>${!f.flipped&&c.image_url&&f.orientation!=='term'?`<img src="${c.image_url}" alt="">`:''}<small class="muted" style="display:block;margin-top:20px">Click or press Space to flip</small></span></span><span class="face back"><span class="card-label">Answer</span><span><span class="card-text">${esc(back)}</span>${c.image_url?`<img src="${c.image_url}" alt="Card illustration">`:''}${c.hint?`<small class="muted" style="display:block;margin-top:20px">Hint: ${esc(c.hint)}</small>`:''}</span></span></button></div><div class="study-controls"><button class="secondary" id="prev-flash">← Previous</button><button class="secondary" id="next-flash">Next →</button></div><div class="rating-row"><button data-rate="again">Again<br><small>1</small></button><button data-rate="hard">Hard<br><small>2</small></button><button data-rate="good">Good<br><small>3</small></button><button data-rate="easy">Easy<br><small>4</small></button></div></section>`;document.querySelector('#exit-study').onclick=()=>route(`deck/${state.activeDeck.id}`);document.querySelector('#flashcard').onclick=flipCard;document.querySelector('#prev-flash').onclick=()=>flashMove(-1);document.querySelector('#next-flash').onclick=()=>flashMove(1);document.querySelector('#shuffle-flash').onclick=()=>{state.cards.sort(()=>Math.random()-.5);state.flash.index=0;state.flash.flipped=false;renderFlashScreen()};document.querySelector('#orient-flash').onclick=()=>{state.flash.orientation=state.flash.orientation==='term'?'definition':'term';state.flash.flipped=false;renderFlashScreen()};document.querySelector('#auto-flash').onclick=toggleAutoplay;document.querySelector('#speak-flash').onclick=()=>speak(state.flash.flipped?back:front);document.querySelector('#star-flash').onclick=async()=>{c.starred=!c.starred;await api(`/api/cards/${c.id}/star`,{method:'POST',body:JSON.stringify({starred:c.starred})});renderFlashScreen()};document.querySelectorAll('[data-rate]').forEach(x=>x.onclick=()=>rateFlash(x.dataset.rate));}
function flipCard(){if(!state.flash)return;state.flash.flipped=!state.flash.flipped;document.querySelector('#flashcard')?.classList.toggle('flipped',state.flash.flipped);saveFlashState()}
function flashMove(delta){if(!state.flash)return;state.flash.index=(state.flash.index+delta+state.cards.length)%state.cards.length;state.flash.flipped=false;renderFlashScreen()}
async function rateFlash(rating){const card=state.cards[state.flash.index];await api('/api/reviews',{method:'POST',body:JSON.stringify({card_id:card.id,rating})});toast(`${rating[0].toUpperCase()+rating.slice(1)} · review saved`);flashMove(1)}
function toggleAutoplay(){state.flash.auto=!state.flash.auto;clearInterval(state.timer);if(state.flash.auto){state.timer=setInterval(()=>{if(!state.flash.flipped)flipCard();else flashMove(1)},2500);toast('Autoplay started')}else toast('Autoplay stopped');renderFlashScreen()}
function speak(text,rate=1){speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(text);utterance.rate=rate;speechSynthesis.speak(utterance)}

async function configureStudy(deckId,mode){
  const [deck,cards]=await Promise.all([api(`/api/decks/${deckId}`),api(`/api/decks/${deckId}/cards`)]);state.activeDeck=deck;state.cards=cards;
  const sessionKey=`study-session-${mode}-${deckId}`,savedId=localStorage.getItem(sessionKey);
  if(savedId){try{const saved=await api(`/api/sessions/${savedId}`);if(saved.status==='active'&&saved.mode===mode&&saved.deck_id===deckId){state.session=saved;await renderStudyQuestion();return}localStorage.removeItem(sessionKey)}catch(_error){localStorage.removeItem(sessionKey)}}
  openModal(`<p class="eyebrow">${esc(mode)}</p><h2>Choose your study settings</h2><form id="study-config"><div class="two-col"><div class="field"><label>Answer with</label><select name="answer_with"><option value="definition">Definitions</option><option value="term">Terms</option></select></div><div class="field"><label>Grading</label><select name="grading"><option value="strict">Strict</option><option value="moderate" selected>Moderate</option><option value="relaxed">Relaxed</option></select></div></div>${mode==='learn'?'<div class="field"><label>Study goal</label><select name="target_repetitions"><option value="1">Quick pass · once correct</option><option value="2" selected>Mastery · twice correct</option><option value="3">Deep practice · three times</option></select></div>':''}<label><input type="checkbox" name="starred_only"> Study starred cards only</label><label style="display:block;margin:12px 0"><input type="checkbox" name="adaptive" checked> Prioritize missed and unmastered cards</label><label style="display:block;margin:12px 0"><input type="checkbox" name="shuffle"> Shuffle instead</label>${mode==='spell'?'<label style="display:block;margin:12px 0"><input type="checkbox" name="slow_audio"> Start with slow audio</label>':''}<button class="primary">Start ${esc(mode)}</button></form>`);
  document.querySelector('#study-config').onsubmit=async event=>{event.preventDefault();const raw=formData(event.target);try{state.session=await api('/api/sessions',{method:'POST',body:JSON.stringify({deck_id:deckId,mode,options:{answer_with:raw.answer_with,grading:raw.grading,starred_only:raw.starred_only==='on',adaptive:raw.adaptive==='on',shuffle:raw.shuffle==='on',slow_audio:raw.slow_audio==='on',target_repetitions:Number(raw.target_repetitions||2)}})});localStorage.setItem(sessionKey,String(state.session.id));closeModal();await renderStudyQuestion()}catch(error){toast(error.message,true)}};
}

async function renderStudyQuestion(feedback=null){
  const s=state.session,c=s.current_card;if(!c||s.status==='complete'){renderSessionComplete(s);return}const reverse=s.options.answer_with==='term';const rawPrompt=reverse?c.back:c.front;const prompt=s.mode==='spell'?'Listen, then type what you hear':rawPrompt;const expected=reverse?c.front:c.back;const isChoice=s.mode==='learn'&&s.state.answered%2===0;let choices=[];if(isChoice){const pool=state.cards.length?state.cards:await api(`/api/decks/${s.deck_id}/cards`);choices=[expected,...pool.map(x=>reverse?x.front:x.back).filter(x=>x!==expected)].filter((x,i,a)=>a.indexOf(x)===i).slice(0,4).sort(()=>Math.random()-.5)}app.innerHTML=`<section class="study-shell"><div class="study-top"><button class="ghost compact" id="exit-session">← Exit</button><div class="progress-track"><span style="width:${s.progress_percent}%"></span></div><strong>${s.correct} correct</strong></div><article class="question-card"><p class="eyebrow">${esc(s.mode)} · ${isChoice?'Choose':'Type'} the ${reverse?'term':'definition'}</p><div class="question">${esc(prompt)}</div>${c.hint?`<p class="muted">Hint: ${esc(c.hint)}</p>`:''}${s.mode==='spell'?'<div class="actions"><button class="secondary" id="hear-word">🔊 Hear it again</button><button class="secondary" id="slow-word">🐢 Play slowly</button></div>':''}${isChoice?`<div class="choices">${choices.map(x=>`<button class="choice" data-answer="${esc(x)}">${esc(x)}</button>`).join('')}</div>`:`<form id="answer-form"><div class="field"><label for="response">Your answer</label><input id="response" name="response" autocomplete="off" autofocus></div><div class="actions"><button class="primary">Check answer</button><button type="button" class="secondary" id="dont-know">Don’t know</button></div></form>`}${feedback?renderFeedback(feedback):''}</article></section>`;document.querySelector('#exit-session').onclick=()=>route(`deck/${s.deck_id}`);if(s.mode==='spell'){speak(expected,s.options.slow_audio?0.75:1);document.querySelector('#hear-word').onclick=()=>speak(expected);document.querySelector('#slow-word').onclick=()=>speak(expected,0.65)}if(isChoice)document.querySelectorAll('[data-answer]').forEach(x=>x.onclick=()=>submitStudyAnswer(x.dataset.answer));else{document.querySelector('#answer-form').onsubmit=e=>{e.preventDefault();submitStudyAnswer(e.target.response.value)};document.querySelector('#dont-know').onclick=()=>submitStudyAnswer('')};}
function renderFeedback(feedback){return `<div class="feedback ${feedback.correct?'good':'bad'}"><strong>${feedback.correct?'Correct!':'Not quite yet.'}</strong>${feedback.correct?'':`<div>The answer is <b>${esc(feedback.expected)}</b></div>`}${feedback.explanation?`<p>${esc(feedback.explanation)}</p>`:''}</div>`}
function spellingDiff(response,expected){const typed=String(response||'');return [...String(expected||'')].map((char,index)=>`<span class="${typed[index]?.toLocaleLowerCase()===char.toLocaleLowerCase()?'char-good':'char-bad'}">${esc(char)}</span>`).join('')}
function renderStudyCorrection(feedback){const spelling=state.session.mode==='spell'?`<div class="spelling-map" aria-label="Character-level spelling feedback">${spellingDiff(feedback.response,feedback.expected)}</div>`:'';app.innerHTML=`<section class="study-shell"><div class="study-top"><button class="ghost compact" id="exit-session">← Exit</button><div class="progress-track"><span style="width:${state.session.progress_percent}%"></span></div><strong>${state.session.correct} correct</strong></div><article class="question-card"><p class="eyebrow">Review your answer</p><div class="question">${esc(feedback.prompt)}</div><p class="muted">You wrote: ${esc(feedback.response||'Nothing')}</p>${spelling}${renderFeedback(feedback)}<div class="actions"><button class="primary" id="continue-answer">Continue</button><button class="ghost" id="override-answer">I was correct</button></div></article></section>`;document.querySelector('#exit-session').onclick=()=>route(`deck/${state.session.deck_id}`);document.querySelector('#continue-answer').onclick=()=>renderStudyQuestion();document.querySelector('#override-answer').onclick=overrideLast}
async function submitStudyAnswer(response,override=false){const result=await api(`/api/sessions/${state.session.id}/answer`,{method:'POST',body:JSON.stringify({response,card_id:state.session.current_card.id,override})});state.session=result.session;if(!result.correct&&!override)renderStudyCorrection(result);else{toast('Correct');await renderStudyQuestion()}}
async function overrideLast(){const updated=await api(`/api/sessions/${state.session.id}/override-last`,{method:'POST'});state.session=updated.session;toast('Marked correct');await renderStudyQuestion();}
function renderSessionComplete(session){localStorage.removeItem(`study-session-${session.mode}-${session.deck_id}`);app.innerHTML=`<section class="study-shell panel empty"><div class="emoji">🌟</div><p class="eyebrow">Session complete</p><h1>You kept growing.</h1><p class="muted">${session.correct} correct · ${session.incorrect} to keep practicing</p><div class="actions" style="justify-content:center"><button class="primary" id="again-session">Study again</button><button class="secondary" id="back-deck">Back to deck</button></div></section>`;document.querySelector('#again-session').onclick=()=>route(`${session.mode}/${session.deck_id}`);document.querySelector('#back-deck').onclick=()=>route(`deck/${session.deck_id}`)}

async function configureTest(deckId){const deck=await api(`/api/decks/${deckId}`);state.activeDeck=deck;openModal(`<p class="eyebrow">Practice test</p><h2>Build your test</h2><form id="test-config"><div class="field"><label>Number of questions</label><input name="limit" type="number" min="1" max="100" value="10"></div><div class="field"><label>Question types</label><label><input type="checkbox" name="type" value="multiple_choice" checked> Multiple choice</label><label><input type="checkbox" name="type" value="true_false" checked> True or false</label><label><input type="checkbox" name="type" value="written" checked> Written</label></div><label><input type="checkbox" name="starred_only"> Test starred cards only</label><button class="primary" style="display:block;margin-top:18px">Start test</button></form>`);document.querySelector('#test-config').onsubmit=async event=>{event.preventDefault();const types=[...event.target.querySelectorAll('[name=type]:checked')].map(x=>x.value);try{const test=await api('/api/tests',{method:'POST',body:JSON.stringify({deck_id:deckId,limit:Number(event.target.limit.value),types,starred_only:event.target.starred_only.checked})});closeModal();renderTest(test,deckId)}catch(error){toast(error.message,true)}}}
function renderTest(test,deckId){app.innerHTML=`<section class="study-shell"><div class="study-top"><button class="ghost compact" id="exit-test">← Exit</button><h2>Practice test</h2><span>${test.questions.length} questions</span></div>${test.warning?`<div class="feedback bad">${esc(test.warning)}</div>`:''}<form id="test-form" class="question-card">${test.questions.map((q,i)=>`<section class="test-question"><p class="eyebrow">Question ${i+1} · ${q.type.replace('_',' ')}</p><h3>${esc(q.question)}</h3>${q.type==='multiple_choice'||q.type==='true_false'?q.options.map(x=>`<label style="display:block;padding:8px"><input type="radio" name="q-${q.card_id}" value="${esc(x)}"> ${esc(x)}</label>`).join(''):`<input class="search" name="q-${q.card_id}" placeholder="Type your answer">`}</section>`).join('')}<button class="primary">Submit test</button></form></section>`;document.querySelector('#exit-test').onclick=()=>route(`deck/${deckId}`);document.querySelector('#test-form').onsubmit=async event=>{event.preventDefault();const data=new FormData(event.target),answers={};test.questions.forEach(q=>answers[q.card_id]=data.get(`q-${q.card_id}`)||'');const result=await api(`/api/tests/${test.session_id}/submit`,{method:'POST',body:JSON.stringify({answers,grading:'moderate'})});renderTestResults(result,deckId)}}
function renderTestResults(result,deckId){app.innerHTML=`<section class="study-shell"><article class="panel empty"><div class="emoji">${result.score>=80?'🎉':'🌱'}</div><p class="eyebrow">Test complete</p><h1>${result.score}%</h1><p class="muted">${result.correct} correct · ${result.incorrect} incorrect</p><div class="actions" style="justify-content:center"><button class="primary" id="restart-test">Restart</button><button class="secondary" id="print-test">Print review</button><button class="ghost" id="return-test">Return to deck</button></div></article><section class="panel" style="margin-top:18px"><h2>Answer review</h2>${result.review.map((x,i)=>`<div class="test-question"><p class="eyebrow">${x.correct?'Correct':'Review this one'}</p><h3>${i+1}. ${esc(x.question)}</h3><p>Your answer: <b>${esc(x.response||'No answer')}</b></p>${x.correct?'':`<p>Correct answer: <b>${esc(x.expected)}</b></p>`}${x.explanation?`<p class="muted">${esc(x.explanation)}</p>`:''}</div>`).join('')}</section></section>`;document.querySelector('#restart-test').onclick=()=>route(`test/${deckId}`);document.querySelector('#return-test').onclick=()=>route(`deck/${deckId}`);document.querySelector('#print-test').onclick=()=>window.print()}

async function renderMatch(deckId){const [deck,cards,scores]=await Promise.all([api(`/api/decks/${deckId}`),api(`/api/decks/${deckId}/cards`),api(`/api/decks/${deckId}/match-scores`)]);if(cards.length<6){renderEmptyMode(deckId,'Match needs at least six cards');return}state.activeDeck=deck;const chosen=[...cards].sort(()=>Math.random()-.5).slice(0,6);const tiles=chosen.flatMap(c=>[{key:c.id,side:'front',text:c.front},{key:c.id,side:'back',text:c.back}]).sort(()=>Math.random()-.5);state.match={tiles,selected:null,matched:new Set(),mistakes:0,start:performance.now(),best:scores.best_ms};renderMatchScreen();state.timer=setInterval(updateMatchTimer,75)}
function renderMatchScreen(){const m=state.match;app.innerHTML=`<section class="study-shell"><div class="study-top"><button class="ghost compact" id="exit-match">← ${esc(state.activeDeck.title)}</button><div><span class="muted">Time </span><span class="timer" id="match-time">0.0s</span></div><span class="muted">Best ${formatTime(m.best)}</span></div><article class="question-card"><p class="eyebrow">Match</p><h2>Pair each term with its definition</h2><p class="muted">A wrong pair adds one second.</p><div class="match-grid">${m.tiles.map((x,i)=>`<button class="match-tile ${m.matched.has(x.key)?'matched':''}" data-index="${i}">${esc(x.text)}</button>`).join('')}</div></article></section>`;document.querySelector('#exit-match').onclick=()=>route(`deck/${state.activeDeck.id}`);document.querySelectorAll('.match-tile:not(.matched)').forEach(x=>x.onclick=()=>selectMatch(Number(x.dataset.index)));}
function updateMatchTimer(){const el=document.querySelector('#match-time');if(el&&state.match)el.textContent=formatTime(performance.now()-state.match.start+state.match.mistakes*1000)}
async function selectMatch(index){const m=state.match,tile=m.tiles[index],button=document.querySelector(`[data-index="${index}"]`);if(m.selected===null){m.selected=index;button.classList.add('selected');return}if(m.selected===index){m.selected=null;button.classList.remove('selected');return}const first=m.tiles[m.selected],firstButton=document.querySelector(`[data-index="${m.selected}"]`);if(first.key===tile.key&&first.side!==tile.side){m.matched.add(tile.key);m.selected=null;firstButton.classList.add('matched');button.classList.add('matched');if(m.matched.size===6){clearInterval(state.timer);const elapsed=Math.round(performance.now()-m.start+m.mistakes*1000);const result=await api('/api/match/scores',{method:'POST',body:JSON.stringify({deck_id:state.activeDeck.id,elapsed_ms:elapsed,mistakes:m.mistakes})});renderMatchComplete(result)}}else{m.mistakes++;firstButton.classList.add('wrong');button.classList.add('wrong');setTimeout(()=>{firstButton.classList.remove('wrong','selected');button.classList.remove('wrong');},300);m.selected=null}}
function renderMatchComplete(result){app.innerHTML=`<section class="study-shell panel empty"><div class="emoji">🏁</div><p class="eyebrow">Board cleared</p><h1>${formatTime(result.elapsed_ms)}</h1><p class="muted">${result.mistakes} mistakes${result.new_best?' · New personal best!':''}</p><div class="actions" style="justify-content:center"><button class="primary" id="play-again">Play again</button><button class="secondary" id="match-deck">Back to deck</button></div></section>`;document.querySelector('#play-again').onclick=()=>renderMatch(state.activeDeck.id);document.querySelector('#match-deck').onclick=()=>route(`deck/${state.activeDeck.id}`)}
function renderEmptyMode(deckId,title){app.innerHTML=`<section class="study-shell panel empty"><div class="emoji">🌱</div><h1>${esc(title)}</h1><p class="muted">Add more cards or change your filters, then try again.</p><button class="primary" id="empty-back">Back to deck</button></section>`;document.querySelector('#empty-back').onclick=()=>route(`deck/${deckId}`)}

async function renderFolders(){const [folders,decks]=await Promise.all([api('/api/folders'),api('/api/decks')]);state.folders=folders;state.decks=decks;app.innerHTML=`<div class="section-head"><div><p class="eyebrow">Folders</p><h1>Keep topics together</h1></div><button class="primary" id="new-folder">＋ New folder</button></div><section class="folder-grid">${folders.map(f=>`<article class="folder" data-folder="${f.id}"><div class="inner"><span class="pill">${f.deck_count} decks</span><h3>${esc(f.title)}</h3><p class="muted">${esc(f.description||'A tidy place for related sets.')}</p><div class="actions"><button class="secondary open-folder">View decks</button><button class="danger delete-folder">Delete</button></div></div></article>`).join('')||emptyInline('No folders yet','Create one to group related decks.')}</section>`;document.querySelector('#new-folder').onclick=showCreateFolder;document.querySelectorAll('.folder').forEach(row=>{const id=Number(row.dataset.folder);row.querySelector('.open-folder').onclick=()=>{route('library');setTimeout(()=>{const select=document.querySelector('#folder-filter');if(select){select.value=id;select.dispatchEvent(new Event('change'))}},80)};row.querySelector('.delete-folder').onclick=async()=>{if(!confirm('Delete this folder? Decks will be kept.'))return;await api(`/api/folders/${id}`,{method:'DELETE'});toast('Folder deleted');renderFolders()}})}
function showCreateFolder(){openModal(`<p class="eyebrow">Organize</p><h2>Create a folder</h2><form id="folder-form"><div class="field"><label>Title</label><input name="title" required autofocus></div><div class="field"><label>Description</label><textarea name="description"></textarea></div><button class="primary">Create folder</button></form>`);document.querySelector('#folder-form').onsubmit=async event=>{event.preventDefault();try{await api('/api/folders',{method:'POST',body:JSON.stringify(formData(event.target))});closeModal();toast('Folder created');renderFolders()}catch(error){toast(error.message,true)}}}

async function renderProgress(){const [progress,activity]=await Promise.all([api('/api/progress'),api('/api/activity?limit=20')]);const max=Math.max(progress.not_studied,progress.still_learning,progress.mastered,1);app.innerHTML=`<div class="section-head"><div><p class="eyebrow">Progress</p><h1>See your knowledge grow</h1></div></div><section class="stats">${stat(progress.total_cards,'Total cards')}${stat(progress.mastered,'Mastered')}${stat(progress.due,'Due')}${stat(`${progress.accuracy}%`,'Accuracy')}${stat(progress.streak,'Day streak')}${stat(formatDuration(progress.study_time_ms),'Study time')}</section><div class="two-col"><section class="panel"><h2>Mastery</h2><div class="chart" aria-label="Mastery chart">${[['Not studied',progress.not_studied],['Still learning',progress.still_learning],['Mastered',progress.mastered]].map(([label,value])=>`<div class="chart-col"><span style="height:${value/max*100}%" title="${value}"></span><small>${label}<br><b>${value}</b></small></div>`).join('')}</div><div class="deck-meta">${Object.entries(progress.mode_completion).map(([mode,count])=>`<span class="pill">${esc(mode)} · ${count}</span>`).join('')||'<span class="muted">Completed modes will appear here.</span>'}</div></section><section class="panel"><h2>Most missed</h2>${progress.most_missed.slice(0,8).map(card=>`<div class="activity"><div><strong>${esc(card.front)}</strong><div class="muted">${esc(card.back)}</div></div><span class="pill">${card.incorrect_count} missed</span></div>`).join('')||'<p class="muted">No missed cards yet.</p>'}</section></div><div class="two-col" style="margin-top:18px"><section class="panel"><h2>Recent study sessions</h2>${progress.sessions.slice(0,8).map(s=>`<div class="activity"><div><strong>${esc(s.mode)}</strong><div class="muted">${s.correct} correct · ${s.incorrect} missed</div></div><time class="muted">${formatDate(s.started_at)}</time></div>`).join('')||'<p class="muted">Complete a study session to see it here.</p>'}</section><section class="panel"><h2>Test history</h2>${progress.quiz_scores.map(test=>`<div class="activity"><strong>${test.score}%</strong><time class="muted">${formatDate(test.completed_at)}</time></div>`).join('')||'<p class="muted">Completed test scores will appear here.</p>'}</section></div><section class="panel" style="margin-top:18px"><h2>All activity</h2><div class="activity-list">${activity.map(activityRow).join('')||'<p class="muted">No activity yet.</p>'}</div></section>`}

if(!location.hash)location.hash='dashboard';else renderRoute();
