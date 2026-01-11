// Full Feature UI Script v11
const API = location.origin.includes('8000') ? location.origin : 'http://localhost:8000';

// Elements
const fileInput = document.getElementById('logFiles');
const btnUpload = document.getElementById('btnUpload');
const btnExport = document.getElementById('btnExport');
const exportSelect = document.getElementById('exportFormat');
const btnGroupMode = null; // group mode removed
const issuesList = document.getElementById('issuesList');
const statusEl = document.getElementById('status');
const emptyState = document.getElementById('emptyState');
const detailArea = document.getElementById('detailArea');
const metaLine = document.getElementById('metaLine');
const snippetBox = document.getElementById('snippetBox');
const resolutionBox = document.getElementById('resolutionBox');
const btnResolve = document.getElementById('btnResolve');
const btnCopy = document.getElementById('btnCopy');
const btnCopySnippet = document.getElementById('btnCopySnippet');
const filterButtons = document.querySelectorAll('.filters .filt');
const searchBox = document.getElementById('searchBox');
const countAll = document.getElementById('countAll');
const countErr = document.getElementById('countErr');
const sumResolved = document.getElementById('sumResolved');
const sumProgress = document.getElementById('sumProgress');
const flagQa = document.getElementById('flagQa');
const flagIndex = document.getElementById('flagIndex');
const toastHost = document.getElementById('toastHost');
const overlay = document.getElementById('overlay');
const overlayMsg = document.getElementById('overlayMsg');
const gpWrap = document.getElementById('progressWrap');
const gpFill = document.getElementById('gpFill');
const gpLabel = document.getElementById('gpLabel');
const gpPct = document.getElementById('gpPct');
const miniFill = document.getElementById('miniFill');
const resolveProg = document.getElementById('resolveProgress');
const issuesSkeleton = document.getElementById('issuesSkeleton');
const batchBar = document.getElementById('batchBar');
const batchCount = document.getElementById('batchCount');
const btnBatchResolve = document.getElementById('btnBatchResolve');
const btnBatchMark = document.getElementById('btnBatchMark');
const btnBatchExport = document.getElementById('btnBatchExport');
const btnBatchClear = document.getElementById('btnBatchClear');
const btnToggleResolution = document.getElementById('btnToggleResolution');
const sourcesBlock = null;
const sourcesList = null;
const btnToggleSources = null;
const summaryBox = document.getElementById('summaryBox');
const summaryStatus = document.getElementById('summaryStatus');
const tabButtons = document.querySelectorAll('#detailTabs .tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');
const btnToggleSummary = document.getElementById('btnToggleSummary');
const indexLockHint = document.getElementById('indexLockHint'); // NEW
const btnRetrySummary = document.getElementById('btnRetrySummary');
const selectedFilesBar = document.getElementById('selectedFilesBar');
const fileInputLabelSpan = document.querySelector('.file-input span');
const btnAnalytics = document.getElementById('btnAnalytics');
const analyticsModal = document.getElementById('analyticsModal');
const analyticsClose = document.getElementById('analyticsClose');
const chartSeverity = document.getElementById('chartSeverity');
const chartTop = document.getElementById('chartTop');
const chartProgress = document.getElementById('chartProgress');
const legendSeverity = document.getElementById('legendSeverity');
const kpiTotal=document.querySelector('#kpiTotal .kpi-value');
const kpiErrors=document.querySelector('#kpiErrors .kpi-value');
const kpiResolved=document.querySelector('#kpiResolved .kpi-value');
const kpiTop=document.querySelector('#kpiTop .kpi-value');
const topErrorList=document.getElementById('topErrorList'); // NEW
const btnEmailReport=document.getElementById('btnEmailReport');
const emailModal=document.getElementById('emailModal');
const emailClose=document.getElementById('emailClose');
const emailFrom=document.getElementById('emailFrom'); // NEW
const emailTo=document.getElementById('emailTo');
const emailSubject=document.getElementById('emailSubject');
const emailBody=document.getElementById('emailBody');
const btnGenerateMailto=document.getElementById('btnGenerateMailto');
const btnCopyEmailBody=document.getElementById('btnCopyEmailBody');
const btnSendOutlook=document.getElementById('btnSendOutlook');
let PENDING_FILE_NAMES = [];

// === Added: helper to fully reset UI state prior to (re)upload ===
function resetUIForNewUpload(opts={}){
  const {preserveFilesBar=false} = opts;
  CURRENT_ID=null; ERRORS=[]; GROUPS=[]; SELECTED.clear(); SUMMARY_CACHE={}; RESOLVED_COUNT=0; FILTER='ALL';
  if(issuesList) issuesList.innerHTML='';
  if(statusEl) statusEl.textContent='';
  if(detailArea){ detailArea.style.display='none'; }
  if(emptyState){ emptyState.style.display='block'; emptyState.textContent='Uploading...'; }
  if(snippetBox) snippetBox.textContent='';
  if(resolutionBox) resolutionBox.textContent='';
  if(summaryBox) summaryBox.textContent='';
  if(btnToggleResolution) btnToggleResolution.style.display='none';
  if(btnToggleSummary) btnToggleSummary.style.display='none';
  if(!preserveFilesBar && selectedFilesBar){ selectedFilesBar.innerHTML=''; selectedFilesBar.classList.add('hidden'); selectedFilesBar.dataset.mode='pre'; }
  if(!preserveFilesBar) PENDING_FILE_NAMES = [];
  updateCounts();
}

// State
let ERRORS=[]; let CURRENT_ID=null; let FILTER='ALL'; let RESOLVED_COUNT=0; let QA_READY=false; let pollTimer=null; let pollInterval=2000; let pollAttempts=0; // NEW backoff state
let gpAnimTimer=null; let gpLevel=0; let RESOLVING=false; let GROUP_MODE=false; let GROUPS=[]; let SELECTED=new Set();
let RESOLUTION_FULL_TEXT=null, RESOLUTION_SUMMARY_TEXT=null, RESOLUTION_EXPANDED=false;
let SUMMARY_CACHE = {}; // id -> {summary, full}
let REQUIRE_UPLOAD = true; // NEW: force initial disabled state until first upload cycle completes
let UPLOAD_CYCLE_ACTIVE = false; // NEW
let progressHistory=[];

// Toast
function toast({title,msg,type='info',ttl=3500}){ if(!toastHost) return; const div=document.createElement('div'); div.className='toast '+type; div.innerHTML=`<strong>${title}</strong><div>${msg}</div>`; toastHost.appendChild(div); setTimeout(()=>{ div.style.opacity='0'; setTimeout(()=>div.remove(),300); }, ttl); }

// Steps
function setStep(step){
  const order=['select','upload','index','ready'];
  const steps=[...document.querySelectorAll('#pipelineSteps .step')];
  steps.forEach(s=>{ s.classList.remove('active'); s.classList.remove('done'); });
  if(step==='complete'){
    // Mark all steps as done; no active highlight
    steps.forEach(s=> s.classList.add('done'));
    return;
  }
  steps.forEach(s=>{
    const name=s.dataset.step;
    if(name===step){
      s.classList.add('active');
    } else if(order.indexOf(name) !== -1 && order.indexOf(name) < order.indexOf(step)){
      s.classList.add('done');
    }
  });
}


// NEW: lock helpers (were missing causing script error)
function setGlobalLock(lock){
  const effectiveLock = lock || REQUIRE_UPLOAD; // still lock if first upload not done
  if(btnUpload) btnUpload.disabled = false;
  const actionBtns=[btnResolve, btnExport, btnGroupMode, btnBatchResolve, btnBatchMark, btnBatchExport];
  actionBtns.forEach(b=>{ if(!b) return; b.disabled = effectiveLock || !QA_READY; b.setAttribute('aria-disabled', String(effectiveLock || !QA_READY)); });
  if(filterButtons){ filterButtons.forEach(b=>{ b.disabled = effectiveLock; b.setAttribute('aria-disabled', String(effectiveLock)); b.classList.toggle('lock-disabled', effectiveLock); }); }
  if(searchBox){ searchBox.disabled = effectiveLock; if(effectiveLock){ if(!searchBox.dataset.phOrig) searchBox.dataset.phOrig=searchBox.placeholder; searchBox.placeholder = REQUIRE_UPLOAD? 'Disabled: upload logs first' : 'Disabled: building index'; } else if(searchBox.dataset.phOrig){ searchBox.placeholder = searchBox.dataset.phOrig; }}
  if(issuesList) issuesList.classList.toggle('disabled', !!effectiveLock);
  if(indexLockHint){
    if(effectiveLock){
      indexLockHint.textContent = REQUIRE_UPLOAD? 'Upload logs and wait for indexing — controls are temporarily disabled.' : 'Building index — controls disabled until ready.';
      indexLockHint.classList.remove('hidden');
    } else {
      indexLockHint.classList.add('hidden');
    }
  }
}
function setDetailLock(lock){
  if(detailArea) detailArea.classList.toggle('locked', !!lock);
}

// Progress helpers
function setGlobalProgress(label,pct,{active=false,hideOnDone=true}={}){ if(!gpWrap) return; pct=Math.max(0,Math.min(100,pct)); gpLabel.textContent=label; gpPct.textContent=Math.round(pct)+'%'; gpFill.style.width=pct+'%'; gpWrap.classList.remove('hidden'); if(active) gpFill.parentElement.classList.add('active'); else gpFill.parentElement.classList.remove('active'); if(pct>=100 && hideOnDone) setTimeout(()=>gpWrap.classList.add('hidden'),1200);} 
function startIndeterminate(label){ if(gpAnimTimer) clearInterval(gpAnimTimer); gpLevel=40; setGlobalProgress(label,gpLevel,{active:true,hideOnDone:false}); gpAnimTimer=setInterval(()=>{ gpLevel += Math.random()*5; if(gpLevel>85) gpLevel=60; gpFill.style.width=gpLevel+'%'; },1100);} 
function stopIndeterminate(){ if(gpAnimTimer){ clearInterval(gpAnimTimer); gpAnimTimer=null;} gpFill.parentElement.classList.remove('active'); }

// Counts
function updateCounts(){ const errCount=ERRORS.filter(e=>e.severity==='ERROR').length; if(RESOLVED_COUNT>ERRORS.length) RESOLVED_COUNT=ERRORS.length; countAll.textContent=ERRORS.length; countErr.textContent=errCount; const pct=ERRORS.length? Math.round((RESOLVED_COUNT/ERRORS.length)*100):0; sumResolved.textContent=RESOLVED_COUNT; sumProgress.textContent=pct+'%'; if(miniFill) miniFill.style.width=pct+'%'; progressHistory.push(pct); if(progressHistory.length>100) progressHistory.shift(); if(analyticsModal && !analyticsModal.classList.contains('hidden')) renderAnalytics(); }

// Batch UI
function updateBatchUI(){ const n=SELECTED.size; batchCount.textContent=n+' selected'; if(n>0){ batchBar.classList.remove('hidden'); batchBar.setAttribute('aria-hidden','false'); } else { batchBar.classList.add('hidden'); batchBar.setAttribute('aria-hidden','true'); } [btnBatchResolve,btnBatchMark,btnBatchExport].forEach(b=> b.disabled = n===0); }
function toggleSelect(id){ if(SELECTED.has(id)) SELECTED.delete(id); else SELECTED.add(id); updateBatchUI(); }
btnBatchClear.addEventListener('click',()=>{ SELECTED.clear(); updateBatchUI(); renderIssues(); });

// Render issues
function renderIssues(){ if(GROUP_MODE){ return renderGroups(); } issuesList.innerHTML=''; const term=(searchBox.value||'').toLowerCase(); const filtered=ERRORS.filter(e=>{ const resolved=e.resolved||e.manual_resolved||e._answer; if(FILTER==='RESOLVED' && !resolved) return false; if(FILTER!=='ALL' && FILTER!=='RESOLVED' && e.severity!==FILTER) return false; if(term && !(e.message||'').toLowerCase().includes(term)) return false; return true; }); if(!filtered.length){ statusEl.textContent=ERRORS.length?'No match':''; return;} filtered.forEach(e=>{ const li=document.createElement('li'); li.dataset.id=e.id; const msgRaw=(e.message||'').slice(0,5000); const msgEsc=msgRaw.replace(/</g,'&lt;').replace(/>/g,'&gt;'); const resolved=e.resolved||e.manual_resolved||e._answer; if(resolved) li.classList.add('resolved'); const occ=e.occurrences||e.count||1; li.innerHTML=`<div class="issue-row"><div class="issue-head"><span class="badge ${e.severity}">${e.severity}</span><div class="msg-scroll"><div class="msg-text">${msgEsc}</div></div><span class="count-badge" title="Occurrences">${occ}</span></div></div>`; li.addEventListener('click',()=> selectIssue(e.id)); if(e.id===CURRENT_ID) li.classList.add('active'); issuesList.appendChild(li); }); statusEl.textContent=filtered.length+' shown'; }

// Render groups view
async function fetchGroups(){ try{ const r=await fetch(`${API}/errors?distinct=1`); const d=await r.json(); GROUPS=d.groups||[]; if(GROUP_MODE) renderGroups(); }catch(e){} }
function renderGroups(){ issuesList.innerHTML=''; const term=(searchBox.value||'').toLowerCase(); const filtered=GROUPS.filter(g=> !term || (g.message||'').toLowerCase().includes(term)); if(!filtered.length){ statusEl.textContent = GROUPS.length?'No match':'No groups'; return;} filtered.forEach(g=>{ const li=document.createElement('li'); const pct=g.count? Math.round((g.resolved_count/g.count)*100):0; const occ=g.occurrences||g.count; li.innerHTML=`<div class="issue-row ${g.resolved_count===g.count?'resolved-group':''}"><div class="issue-head"><span class="badge ${g.severity}">${g.severity}</span><span class="msg-text">${(g.message||'').slice(0,170)}</span><span class="count-badge" title="Occurrences">${occ}</span><button class="btn xs ghost act-expand" aria-expanded="false">Expand</button></div><div class="meta-line">Progress ${pct}%</div><ul class="child-issues hidden"></ul></div>`; li.querySelector('.act-expand').addEventListener('click',()=> toggleGroupExpand(li,g.group_key)); issuesList.appendChild(li); }); statusEl.textContent = filtered.length+' groups'; }
async function toggleGroupExpand(li,gk){ const btn=li.querySelector('.act-expand'); const expanded=btn.getAttribute('aria-expanded')==='true'; const child=li.querySelector('.child-issues'); if(expanded){ btn.setAttribute('aria-expanded','false'); btn.textContent='Expand'; child.classList.add('hidden'); return;} btn.setAttribute('aria-expanded','true'); btn.textContent='Hide'; child.classList.remove('hidden'); child.innerHTML='<li class="loading">Loading...</li>'; try{ const r=await fetch(`${API}/errors?group_key=${encodeURIComponent(gk)}`); const d=await r.json(); child.innerHTML=''; (d.errors||[]).forEach(e=>{ const msg=(e.message||'').slice(0,160); const li2=document.createElement('li'); const resolved=e.resolved||e.manual_resolved||e._answer; li2.className='child'+(resolved?' resolved':''); li2.innerHTML=`<span class="badge ${e.severity}">${e.severity}</span> <span class="c-msg">${msg}</span> <button class="btn xs ghost" data-id="${e.id}">Open</button>`; li2.querySelector('button').addEventListener('click',()=>{ GROUP_MODE=false; btnGroupMode.setAttribute('aria-pressed','false'); CURRENT_ID=e.id; ERRORS=d.errors; renderIssues(); selectIssue(e.id); }); child.appendChild(li2); }); }catch(e){ child.innerHTML='<li class="err">Failed</li>'; } }

// Selection
function selectIssue(id){
  CURRENT_ID=id; renderIssues(); const e=ERRORS.find(x=>x.id===id); if(!e) return;
  emptyState.style.display='none'; detailArea.style.display='block';
  const linePart = (e.line_no!==undefined && e.line_no!==null)? `Line:${e.line_no}` : 'Line:?';
  metaLine.textContent=`${e.severity} • ${linePart} • Occurrences:${e.occurrences||1}`;
  snippetBox.textContent=e.snippet||'No snippet';
  // Resolution persistence logic
  RESOLUTION_FULL_TEXT=null; RESOLUTION_SUMMARY_TEXT=null; RESOLUTION_EXPANDED=false;
  if(e._answer_full){
    RESOLUTION_FULL_TEXT = e._answer_full;
    RESOLUTION_SUMMARY_TEXT = e._answer_summary || e._answer_full.slice(0,600);
    if(RESOLUTION_SUMMARY_TEXT.length < RESOLUTION_FULL_TEXT.length){
      resolutionBox.textContent = RESOLUTION_SUMMARY_TEXT + '\n...';
      btnToggleResolution.style.display='inline-flex'; btnToggleResolution.textContent='Show Full';
    } else {
      resolutionBox.textContent = RESOLUTION_FULL_TEXT;
      btnToggleResolution.style.display='none';
    }
  } else {
    resolutionBox.textContent=''; btnToggleResolution.style.display='none';
  }
  summaryStatus.textContent=''; SUMMARY_EXPANDED=false; btnToggleSummary.style.display='none';
  if(SUMMARY_CACHE[id]){ applySummaryDisplay(id); } else { summaryBox.textContent='Generating summary...'; autoSummary(id); }
}

// Overlay
function showOverlay(msg){ overlayMsg.textContent=msg||'Working...'; overlay.classList.remove('hidden'); }
function hideOverlay(){ overlay.classList.add('hidden'); }

// Skeleton
function showSkeleton(n=6){ if(!issuesSkeleton) return; issuesSkeleton.innerHTML=''; for(let i=0;i<n;i++){ const li=document.createElement('li'); li.className='skeleton-item'; issuesSkeleton.appendChild(li);} issuesSkeleton.classList.remove('hidden'); issuesList.classList.add('hidden'); }
function hideSkeleton(){ if(!issuesSkeleton) return; issuesSkeleton.classList.add('hidden'); issuesList.classList.remove('hidden'); }

// Upload
async function upload(){
  if(!fileInput.files.length){ toast({title:'No Files',msg:'Select log files',type:'warn'}); return; }
  // Capture current selection BEFORE reset so we can show during upload
  const selFiles=[...fileInput.files];
  PENDING_FILE_NAMES = selFiles.map(f=>f.name);
  const maxShow=5;
  const first=selFiles[0].name; const extra=selFiles.length-1;
  const labelText = extra>0? `${first} (+${extra})` : first;
  resetUIForNewUpload({preserveFilesBar:true});
  // Re-render files bar immediately (uploading state)
  if(selectedFilesBar){
    selectedFilesBar.classList.remove('hidden');
    selectedFilesBar.dataset.mode='uploading';
    const label = 'File:'; // always singular per user request
    selectedFilesBar.innerHTML = `<span class="label">${label}</span>` + selFiles.slice(0,maxShow).map(f=>`<span class=\"file-pill\" title=\"${f.name}\">${f.name}</span>`).join('');
    if(selFiles.length>maxShow){ selectedFilesBar.innerHTML += `<button type=\"button\" class=\"more-count\" aria-label=\"Show ${selFiles.length-maxShow} more files\">+${selFiles.length-maxShow} more</button>`; }
  }
  if(fileInputLabelSpan) fileInputLabelSpan.textContent = labelText;
  REQUIRE_UPLOAD = true; UPLOAD_CYCLE_ACTIVE=true; setGlobalLock(true);
  setStep('upload'); showOverlay('Uploading...'); showSkeleton(); setGlobalProgress('Uploading',10,{active:true,hideOnDone:false});
  const form=new FormData(); for(const f of selFiles) form.append('files',f,f.name);
  let success=false;
  try { const res=await fetch(`${API}/upload`,{method:'POST',body:form}); const raw=await res.text(); let data={}; try{ data=JSON.parse(raw);}catch{ throw new Error(raw||'Upload parse error'); } if(!res.ok) throw new Error(data.detail||'Upload failed');
    setStep('index'); setGlobalProgress('Processing',40,{active:true,hideOnDone:false});
    ERRORS=data.errors||[]; CURRENT_ID=null; RESOLVED_COUNT=0; 
    ERRORS.forEach(e=>{ delete e.resolved; delete e.manual_resolved; delete e._answer; delete e._answer_full; delete e._answer_summary; });
    hideSkeleton(); updateCounts(); renderIssues();
    if(ERRORS.length){ selectIssue(ERRORS[0].id); toast({title:'Upload Complete',msg:`${ERRORS.length} issues`}); } else { emptyState.style.display='block'; detailArea.style.display='none'; toast({title:'No Issues',msg:'No ERROR lines',type:'warn'}); }
    if(selectedFilesBar){ selectedFilesBar.dataset.mode='post'; }
    pollStats(true); success=true;
  } catch(e){ hideSkeleton(); toast({title:'Upload Error',msg:e.message||'Failed',type:'error'}); setGlobalProgress('Failed',100,{active:false}); UPLOAD_CYCLE_ACTIVE=false; }
  finally { hideOverlay(); fileInput.value=''; if(!success && fileInputLabelSpan) fileInputLabelSpan.textContent='Select Files'; }
}

// Resolve
async function resolve(){
  if(!CURRENT_ID || RESOLVING) return; if(!QA_READY){ toast({title:'Not Ready',msg:'QA building',type:'warn'}); return;}
  RESOLVING=true; resolutionBox.textContent='Generating...';
  if(resolveProg){ resolveProg.classList.remove('hidden'); resolveProg.querySelector('span').style.width='0%'; requestAnimationFrame(()=> resolveProg.querySelector('span').style.width='100%'); }
  try { const res=await fetch(`${API}/resolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:CURRENT_ID})}); const data=await res.json(); if(!res.ok) throw new Error(data.detail||'Resolve failed'); if(data.answer){
      const full=data.answer.text||data.answer; RESOLUTION_FULL_TEXT=full; RESOLUTION_SUMMARY_TEXT=full.split('\n').slice(0,6).join('\n').slice(0,600);
      if(RESOLUTION_SUMMARY_TEXT.length<full.length){ resolutionBox.textContent=RESOLUTION_SUMMARY_TEXT+'\n...'; btnToggleResolution.style.display='inline-flex'; btnToggleResolution.textContent='Show Full'; } else { resolutionBox.textContent=full; }
      const errObj=ERRORS.find(e=>e.id===CURRENT_ID); if(errObj){ errObj._answer_full=full; errObj._answer_summary=RESOLUTION_SUMMARY_TEXT; errObj._answer=true; if(!errObj._resolvedFlag){ errObj._resolvedFlag=true; RESOLVED_COUNT++; } }
      updateCounts(); toast({title:'Resolved',msg:'Answer ready'});
    } else { resolutionBox.textContent='No answer'; }
  } catch(e){ resolutionBox.textContent='Error'; toast({title:'Resolve Error',msg:e.message||'Failed',type:'error'}); }
  finally { RESOLVING=false; if(resolveProg) setTimeout(()=> resolveProg.classList.add('hidden'),400); }
}
btnToggleResolution.addEventListener('click',()=>{ if(!RESOLUTION_FULL_TEXT) return; RESOLUTION_EXPANDED=!RESOLUTION_EXPANDED; if(RESOLUTION_EXPANDED){ resolutionBox.textContent=RESOLUTION_FULL_TEXT; btnToggleResolution.textContent='Show Summary'; } else { resolutionBox.textContent=RESOLUTION_SUMMARY_TEXT+(RESOLUTION_SUMMARY_TEXT.length<RESOLUTION_FULL_TEXT.length?'\n...':''); btnToggleResolution.textContent='Show Full'; } });

// Batch
async function batchResolve(){ if(!QA_READY || SELECTED.size===0) return; btnBatchResolve.disabled=true; try{ const ids=[...SELECTED]; const r=await fetch(`${API}/resolve_batch`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})}); const d=await r.json(); if(!r.ok) throw new Error(d.detail||'Batch failed'); let added=0; (d.results||[]).forEach(res=>{ if(!res.ok) return; const errObj=ERRORS.find(e=>e.id===res.id); if(errObj){ const full=res.answer?.text||res.answer; if(full){ errObj._answer_full=full; errObj._answer_summary=(full.split('\n').slice(0,6).join('\n')).slice(0,600); errObj._answer=true; }
  if(!errObj._resolvedFlag){ errObj._resolvedFlag=true; added++; } } }); if(added){ RESOLVED_COUNT+=added; }
  updateCounts(); toast({title:'Batch',msg:`${added} resolved`}); }catch(e){ toast({title:'Batch Error',msg:e.message||'Failed',type:'error'});} finally { btnBatchResolve.disabled=false; renderIssues(); }}
async function batchMarkResolved(){ if(SELECTED.size===0) return; btnBatchMark.disabled=true; try{ const ids=[...SELECTED]; const r=await fetch(`${API}/mark_resolved`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids,resolved:true})}); if(!r.ok) throw new Error('Mark failed'); let added=0; ids.forEach(id=>{ const errObj=ERRORS.find(e=>e.id===id); if(errObj && !errObj._resolvedFlag){ errObj._resolvedFlag=true; errObj.manual_resolved=true; added++; } }); if(added){ RESOLVED_COUNT+=added; } updateCounts(); toast({title:'Marked',msg:`${added} marked`}); }catch(e){ toast({title:'Error',msg:e.message||'Failed',type:'error'});} finally { btnBatchMark.disabled=false; renderIssues(); }}
async function batchExport(){ if(SELECTED.size===0) return; btnBatchExport.disabled=true; try{ const ids=[...SELECTED].join(','); const fmt=exportSelect.value; const r=await fetch(`${API}/export?format=${fmt}&ids=${encodeURIComponent(ids)}`); if(!r.ok) throw new Error('Export failed'); if(fmt==='json'){ const d=await r.json(); const blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download= 'issues_selected.json'; a.click(); URL.revokeObjectURL(a.href);} else if(fmt==='md'){ const d=await r.json(); const blob=new Blob([d.markdown],{type:'text/markdown'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='issues_selected.md'; a.click(); URL.revokeObjectURL(a.href);} else { const blob=await r.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`issues_selected.${fmt==='xlsx'?'xlsx':fmt}`; a.click(); URL.revokeObjectURL(a.href);} toast({title:'Export',msg:'Selected exported'}); }catch(e){ toast({title:'Export Error',msg:e.message||'Failed',type:'error'});} finally { btnBatchExport.disabled=false; }}
btnBatchResolve.addEventListener('click',batchResolve); btnBatchMark.addEventListener('click',batchMarkResolved); btnBatchExport.addEventListener('click',batchExport);

// Export all
async function exportAll(){ const fmt=exportSelect.value; try{ const r=await fetch(`${API}/export?format=${fmt}`); if(!r.ok) throw new Error('Export failed'); if(fmt==='json'){ const d=await r.json(); const blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download= 'issues.json'; a.click(); URL.revokeObjectURL(a.href);} else if(fmt==='md'){ const d=await r.json(); const blob=new Blob([d.markdown],{type:'text/markdown'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='issues.md'; a.click(); URL.revokeObjectURL(a.href);} else { const blob=await r.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=`issues.${fmt==='xlsx'?'xlsx':fmt}`; a.click(); URL.revokeObjectURL(a.href);} toast({title:'Export',msg:'All exported'}); }catch(e){ toast({title:'Export Error',msg:e.message||'Failed',type:'error'});} }
btnExport.addEventListener('click',exportAll);

// Poll stats
async function pollStats(fromUpload=false){
  try{
    if(REQUIRE_UPLOAD && !UPLOAD_CYCLE_ACTIVE){
      setStep('select');
      setGlobalProgress('Idle',0,{active:false});
    }
    const r=await fetch(`${API}/stats`);
    if(!r.ok) return; const d=await r.json();
    if(REQUIRE_UPLOAD && !UPLOAD_CYCLE_ACTIVE){
      flagQa.textContent=String(d.qa_ready);
      flagIndex.textContent=String(d.index_building);
      QA_READY=false;
      updateCounts();
      return;
    }
    const partialReady = !d.index_building && d.small_corpus_fast_path;
    const fullReady = !d.index_building && d.qa_ready;
    if(fullReady){
      stopIndeterminate();
      setGlobalProgress('Ready',100,{active:false});
      // Show ready state briefly then mark complete (remove blue highlight)
      if(!pollStats._markedComplete){
        setStep('ready');
        setTimeout(()=>{ setStep('complete'); pollStats._markedComplete=true; }, 1200);
      }
      if(UPLOAD_CYCLE_ACTIVE){ REQUIRE_UPLOAD=false; UPLOAD_CYCLE_ACTIVE=false; }
      setGlobalLock(false); setDetailLock(false); if(gpWrap) gpWrap.classList.add('hidden');
      if(pollTimer){ clearInterval(pollTimer); pollTimer=null; }
    } else if(partialReady){
      setStep('ready');
      setGlobalProgress('Ready (Lazy)',90,{active:false,hideOnDone:false});
      if(UPLOAD_CYCLE_ACTIVE){ REQUIRE_UPLOAD=false; UPLOAD_CYCLE_ACTIVE=false; }
      setGlobalLock(false); setDetailLock(false);
      pollAttempts++; if(pollAttempts===2) pollInterval=4000; else if(pollAttempts===4) pollInterval=6000; else if(pollAttempts===8) pollInterval=10000;
    }
    flagQa.textContent=String(d.qa_ready); flagIndex.textContent=String(d.index_building); QA_READY=!!d.qa_ready; const building=d.index_building; const ready = fullReady; btnResolve.disabled=!QA_READY; setGlobalLock(!ready && !partialReady); setDetailLock(!partialReady && !ready);
    if(building){ if(fromUpload) startIndeterminate('Indexing');
      pollAttempts++; if(pollAttempts===3) pollInterval=4000; else if(pollAttempts===6) pollInterval=6000; else if(pollAttempts===9) pollInterval=10000;
      if(!pollTimer){ pollTimer=setInterval(()=>{ if(pollTimer){ clearInterval(pollTimer); pollTimer=null; } pollStats(); }, pollInterval); }
      if(!partialReady) setStep('index');
    } else if(!fullReady){
      if(!pollTimer){ pollTimer=setInterval(()=>{ if(pollTimer){ clearInterval(pollTimer); pollTimer=null; } pollStats(); }, pollInterval); }
    }
    updateCounts();
  }catch(e){ console.error('pollStats error', e); }}

// Events
filterButtons.forEach(b=> b.addEventListener('click',()=>{ filterButtons.forEach(x=>{ x.classList.remove('active'); x.setAttribute('aria-pressed','false'); }); b.classList.add('active'); b.setAttribute('aria-pressed','true'); FILTER=b.dataset.filter; renderIssues(); }));
searchBox.addEventListener('input',renderIssues);
btnUpload.addEventListener('click',upload);
btnResolve.addEventListener('click',resolve);
btnCopy.addEventListener('click',()=>{ if(resolutionBox.textContent) navigator.clipboard.writeText(resolutionBox.textContent); });
btnCopySnippet.addEventListener('click',()=>{ if(snippetBox.textContent) navigator.clipboard.writeText(snippetBox.textContent); });
if(btnToggleSources){ btnToggleSources.addEventListener('click',()=>{ const expanded=btnToggleSources.getAttribute('aria-expanded')==='true'; btnToggleSources.setAttribute('aria-expanded', String(!expanded)); btnToggleSources.textContent = expanded? 'Show':'Hide'; document.getElementById('sourcesInner').classList.toggle('hidden', expanded); }); }
if(btnToggleSummary){ btnToggleSummary.addEventListener('click',()=>{ SUMMARY_EXPANDED=!SUMMARY_EXPANDED; if(CURRENT_ID) applySummaryDisplay(CURRENT_ID, true); }); }
fileInput.addEventListener('click',()=>{ fileInput.value=''; });
fileInput.addEventListener('change',()=>{
  if(!fileInput.files.length){ if(selectedFilesBar){ selectedFilesBar.classList.add('hidden'); selectedFilesBar.innerHTML=''; } if(fileInputLabelSpan) fileInputLabelSpan.textContent='Select Files'; PENDING_FILE_NAMES=[]; return; }
  const files=[...fileInput.files];
  PENDING_FILE_NAMES = files.map(f=>f.name);
  const first=files[0].name; const extra=files.length-1;
  if(fileInputLabelSpan){ fileInputLabelSpan.textContent = extra>0 ? `${first} (+${extra})` : first; }
  const maxShow=5;
  if(selectedFilesBar){
    selectedFilesBar.classList.remove('hidden');
    selectedFilesBar.dataset.mode='pre';
    const label = 'File:'; // always singular per user request
    selectedFilesBar.innerHTML = `<span class="label">${label}</span>` + files.slice(0,maxShow).map(f=>`<span class="file-pill" title="${f.name}">${f.name}</span>`).join('');
    if(files.length>maxShow){
      selectedFilesBar.innerHTML += `<button type="button" class="more-count" aria-label="Show ${files.length-maxShow} more files" title="Show all files">+${files.length-maxShow} more</button>`;
    }
  }
  // Full pipeline reset on new selection BEFORE upload
  if(gpWrap){
    gpFill.style.width='0%';
    gpPct.textContent='0%';
    gpLabel.textContent='Idle';
    gpWrap.classList.add('hidden');
  }
  // Reset state flags so steps 2-4 are cleared and controls locked until upload
  REQUIRE_UPLOAD = true;
  QA_READY = false;
  UPLOAD_CYCLE_ACTIVE = false;
  pollAttempts = 0; pollInterval = 2000; if(pollTimer){ clearInterval(pollTimer); pollTimer=null; }
  if(gpAnimTimer){ stopIndeterminate(); }
  delete pollStats._markedComplete;
  setStep('select');
  setGlobalLock(true);
  setDetailLock(true);
  // Optionally hide detail area until an issue list is available
  if(detailArea) detailArea.style.display='none';
  if(emptyState){ emptyState.style.display='block'; emptyState.textContent='Ready to upload'; }
  toast({title:'Files Selected', msg:`${files.length} file${files.length>1?'s':''} ready. Click Upload to start.`, type:'info'});
});
if(selectedFilesBar){
  selectedFilesBar.addEventListener('click',e=>{
    if(e.target.classList.contains('more-count')){
      // Expand list to show all pending names
      const btn=e.target; const rest=PENDING_FILE_NAMES.slice(5);
      rest.forEach(name=>{
        const span=document.createElement('span');
        span.className='file-pill'; span.title=name; span.textContent=name; btn.before(span);
      });
      btn.remove();
    }
  });
}

// Init
(function init(){ console.log('[UI] Full feature script v13 with enforced pre-upload lock'); setStep('select'); btnResolve.disabled=true; setGlobalLock(true); setDetailLock(true); updateCounts(); pollStats(); 
  // Help modal wiring (simple)
  const helpFab=document.getElementById('helpFab');
  const helpModal=document.getElementById('helpModal');
  const helpClose=document.getElementById('helpClose');
  const focusSelectors='button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])';
  let lastFocused=null;
  function trapFocus(e){ if(!helpModal || helpModal.classList.contains('hidden')) return; const focusables=[...helpModal.querySelectorAll(focusSelectors)].filter(el=>!el.disabled && el.offsetParent!==null); if(!focusables.length) return; const first=focusables[0]; const last=focusables[focusables.length-1]; if(e.key==='Tab'){ if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); } else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); } } }
  function openHelp(){ if(!helpModal) return; lastFocused=document.activeElement; helpModal.classList.remove('hidden'); helpModal.classList.add('anim-enter'); requestAnimationFrame(()=> helpModal.classList.remove('anim-enter')); helpFab && helpFab.setAttribute('aria-expanded','true'); (helpClose||helpFab).focus(); }
  function closeHelp(){ if(!helpModal) return; helpModal.classList.add('hidden'); helpFab && helpFab.setAttribute('aria-expanded','false'); if(lastFocused && typeof lastFocused.focus==='function') lastFocused.focus(); }
  if(helpFab&&helpModal&&helpClose){
    helpFab.addEventListener('click',openHelp);
    helpClose.addEventListener('click',closeHelp);
    helpModal.addEventListener('click',e=>{ if(e.target===helpModal) closeHelp(); });
    document.addEventListener('keydown',e=>{ if(e.key==='Escape' && !helpModal.classList.contains('hidden')) closeHelp(); else if(e.key==='/' && e.shiftKey && helpModal.classList.contains('hidden') && document.activeElement.tagName!=='INPUT' && document.activeElement.tagName!=='TEXTAREA'){ openHelp(); } else if(e.key==='Tab'){ trapFocus(e); } });
  }
})();

// Sources
async function fetchSources(id){ return; }
const __origSelectIssue = selectIssue; selectIssue = function(id){ __origSelectIssue(id); /* sources removed */ };
function applySummaryDisplay(id, allowFetchFull=false){
  const data = SUMMARY_CACHE[id];
  if(!data) return;
  const rawFull = data.full || data.summary || '';
  let lines = rawFull.split(/\n+/).filter(l=>l.trim().length>0);
  const PREVIEW_LINES = 8;      // collapsed summary lines
  const FULL_MIN_LINES = 8;     // desired minimum in full view
  const FULL_MAX_LINES = 10;    // cap for full view

  // If expanding and we have fewer than FULL_MIN_LINES and can try to fetch extended once
  if(SUMMARY_EXPANDED && allowFetchFull && !data.extendedLoaded && lines.length < FULL_MIN_LINES){
    fetchExtendedSummary(id); // will recall applySummaryDisplay after load
    return;
  }

  if(!SUMMARY_EXPANDED){
    const prev = lines.slice(0, PREVIEW_LINES);
    const truncated = lines.length > PREVIEW_LINES;
    summaryBox.textContent = prev.join('\n') + (truncated ? '\n...' : '');
    if(truncated){
      btnToggleSummary.style.display='inline-flex';
      btnToggleSummary.textContent='Show Full';
    } else {
      btnToggleSummary.style.display='none';
    }
  } else {
    // Recompute lines after possible extended fetch
    lines = (data.full || data.summary || '').split(/\n+/).filter(l=>l.trim().length>0);
    const useCount = Math.min(FULL_MAX_LINES, lines.length);
    const truncated = lines.length > useCount;
    const needPad = lines.length < FULL_MIN_LINES; // even after extended fetch
    summaryBox.textContent = lines.slice(0,useCount).join('\n') + (truncated ? '\n...' : (needPad ? '\n(Full detail limited to available content)' : ''));
    btnToggleSummary.style.display='inline-flex';
    btnToggleSummary.textContent='Show Summary';
  }
}
async function fetchExtendedSummary(id){ try{ summaryStatus.textContent='Loading full...'; const r=await fetch(`${API}/summary?full=1`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})}); const d=await r.json(); if(!r.ok) throw new Error(d.detail||'Full failed'); SUMMARY_CACHE[id].full = d.full || d.summary; SUMMARY_CACHE[id].extendedLoaded = true; summaryStatus.textContent='Full'; applySummaryDisplay(id); }catch(e){ summaryStatus.textContent='Full error'; SUMMARY_EXPANDED=false; applySummaryDisplay(id); }}
async function autoSummary(id) {
  if (!id) return;
  btnRetrySummary && (btnRetrySummary.style.display='none');
  try {
    summaryStatus.textContent='';
    const r = await fetch(`${API}/summary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });
    const d = await r.json();
    if (!r.ok || !d.summary) throw new Error(d.detail || 'Failed');
    SUMMARY_CACHE[id] = { summary: d.summary, full: d.full || d.summary, extendedLoaded:false };
    summaryStatus.textContent = 'Auto';
    applySummaryDisplay(id);
  } catch (e) {
    summaryBox.textContent = 'Summary not available';
    summaryStatus.textContent = 'Error';
    if(btnRetrySummary){ btnRetrySummary.style.display='inline-flex'; btnRetrySummary.onclick=()=>{ summaryBox.textContent='Retrying...'; autoSummary(id); }; }
  }
}

// Analytics
function renderAnalytics(){ renderSeverityChart(); renderTopErrorsChart(); renderProgressChart(); updateKpis(); }
function sizeCanvas(c,h=160){ if(!c) return; const dpr=window.devicePixelRatio||1; const prevW=c.clientWidth||300; c.width=prevW*dpr; c.height=h*dpr; const ctx=c.getContext('2d'); ctx.setTransform(1,0,0,1,0,0); if(dpr!==1) ctx.scale(dpr,dpr); }
function renderSeverityChart(){ if(!chartSeverity) return; sizeCanvas(chartSeverity,160); const ctx=chartSeverity.getContext('2d'); const counts={ERROR:0,WARN:0,INFO:0}; ERRORS.forEach(e=>{ if(counts[e.severity]!==undefined) counts[e.severity]++; }); const data=Object.entries(counts).filter(([,v])=>v>0); ctx.clearRect(0,0,chartSeverity.clientWidth,chartSeverity.clientHeight); if(!data.length){ ctx.fillStyle='#74808a'; ctx.font='12px sans-serif'; ctx.fillText('No data',20,80); legendSeverity.innerHTML=''; return;} const total=data.reduce((a,[,v])=>a+v,0); const cx=chartSeverity.clientWidth/2; const cy=chartSeverity.clientHeight/2; const r=Math.min(cx,cy)-10; let start=-Math.PI/2; legendSeverity.innerHTML=''; data.forEach(([k,v])=>{ const frac=v/total; const end=start+frac*2*Math.PI; ctx.beginPath(); ctx.moveTo(cx,cy); ctx.arc(cx,cy,r,start,end); ctx.closePath(); const color=k==='ERROR'? '#ff5964': k==='WARN'? '#ffb454':'#2d8fff'; ctx.fillStyle=color; ctx.globalAlpha=.9; ctx.fill(); start=end; const span=document.createElement('span'); span.innerHTML=`<i style="background:${color}"></i>${k} ${v} (${Math.round(frac*100)}%)`; legendSeverity.appendChild(span); }); ctx.globalAlpha=1; ctx.fillStyle='#0d1319'; ctx.beginPath(); ctx.arc(cx,cy,r*0.55,0,Math.PI*2); ctx.fill(); ctx.fillStyle='#b9c6d2'; ctx.font='600 14px sans-serif'; ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText(total,cx,cy); }
function renderTopErrorsChart(){ if(!chartTop) return; sizeCanvas(chartTop,160); const ctx=chartTop.getContext('2d'); ctx.clearRect(0,0,chartTop.clientWidth,chartTop.clientHeight); const map=new Map(); ERRORS.forEach(e=>{ if(e.severity==='ERROR'){ const key=(e.message||'').slice(0,60); map.set(key,(map.get(key)||0)+(e.occurrences||1)); }}); const rows=[...map.entries()].sort((a,b)=>b[1]-a[1]).slice(0,5); if(topErrorList){ topErrorList.innerHTML=''; rows.forEach(([msg,val])=>{ const li=document.createElement('li'); li.textContent=`(${val}) ${msg}`; topErrorList.appendChild(li); }); if(!rows.length){ topErrorList.innerHTML='<li style="opacity:.6;">No errors</li>'; } }
  if(!rows.length){ ctx.fillStyle='#74808a'; ctx.font='12px sans-serif'; ctx.fillText('No data',10,80); return;} const max=Math.max(...rows.map(r=>r[1])); const barH=26; rows.forEach((r,i)=>{ const [msg,val]=r; const y=14+i*barH; const w=(val/max)*(chartTop.clientWidth-140); ctx.fillStyle='rgba(255,89,100,.18)'; ctx.fillRect(120,y-14,chartTop.clientWidth-150,barH-10); ctx.fillStyle='#ff5964'; ctx.fillRect(120,y-14,w,barH-10); ctx.fillStyle='#b9c6d2'; ctx.font='10px sans-serif'; ctx.textAlign='right'; ctx.fillText(val,115,y-2); ctx.textAlign='left'; ctx.fillStyle='#ffe5e7'; ctx.fillText(msg,122,y-2); }); }
function renderProgressChart(){ if(!chartProgress) return; sizeCanvas(chartProgress,160); const ctx=chartProgress.getContext('2d'); ctx.clearRect(0,0,chartProgress.clientWidth,chartProgress.clientHeight); if(progressHistory.length<2){ ctx.fillStyle='#74808a'; ctx.font='12px sans-serif'; ctx.fillText('No trend',10,80); return;} ctx.strokeStyle='#2d8fff'; ctx.lineWidth=2; ctx.beginPath(); progressHistory.forEach((p,i)=>{ const x=i/(progressHistory.length-1)*(chartProgress.clientWidth-20)+10; const y= chartProgress.clientHeight-30 - (p/100)*(chartProgress.clientHeight-60); if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); }); ctx.stroke(); ctx.fillStyle='rgba(45,143,255,.25)'; ctx.lineTo(chartProgress.clientWidth-10,chartProgress.clientHeight-30); ctx.lineTo(10,chartProgress.clientHeight-30); ctx.closePath(); ctx.fill(); ctx.strokeStyle='#46535f'; ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(10,chartProgress.clientHeight-30); ctx.lineTo(chartProgress.clientWidth-10,chartProgress.clientHeight-30); ctx.stroke(); ctx.fillStyle='#b9c6d2'; ctx.font='10px sans-serif'; ctx.textAlign='right'; ctx.fillText((progressHistory.at(-1)||0)+'%',chartProgress.clientWidth-12,14); }
function updateKpis(){ if(!kpiTotal) return; const total=ERRORS.length; const err=ERRORS.filter(e=>e.severity==='ERROR').length; const topOcc=Math.max(0,...ERRORS.filter(e=>e.severity==='ERROR').map(e=>e.occurrences||1)); const resolvedPct= total? Math.round((RESOLVED_COUNT/total)*100):0; kpiTotal.textContent=String(total); kpiErrors.textContent= String(err); kpiResolved.textContent= `${RESOLVED_COUNT} (${resolvedPct}%)`; kpiTop.textContent= topOcc? String(topOcc):'0'; }

if(btnAnalytics && analyticsModal){
  const openAnalytics=()=>{ if(analyticsModal.classList.contains('hidden')){ analyticsModal.classList.remove('hidden'); analyticsModal.setAttribute('aria-hidden','false'); renderAnalytics(); trapAnalyticsFocus(); } };
  const closeAnalytics=()=>{ if(!analyticsModal.classList.contains('hidden')){ analyticsModal.classList.add('hidden'); analyticsModal.setAttribute('aria-hidden','true'); } };
  btnAnalytics.addEventListener('click',openAnalytics);
  analyticsClose && analyticsClose.addEventListener('click',closeAnalytics);
  analyticsModal.addEventListener('click',e=>{ if(e.target===analyticsModal) closeAnalytics(); });
  document.addEventListener('keydown',e=>{ if(e.key==='Escape' && !analyticsModal.classList.contains('hidden')) closeAnalytics(); });
  // Focus trap for accessibility
  let prevFocus=null;
  function trapAnalyticsFocus(){ prevFocus=document.activeElement; const selectors='button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'; const nodes=[...analyticsModal.querySelectorAll(selectors)].filter(el=>!el.disabled); if(nodes.length){ nodes[0].focus(); } function loop(e){ if(e.key!=='Tab') return; const focusables=[...analyticsModal.querySelectorAll(selectors)].filter(el=>!el.disabled && el.offsetParent!==null); if(!focusables.length) return; const first=focusables[0]; const last=focusables[focusables.length-1]; if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); } else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); } } analyticsModal.__trapHandler=loop; document.addEventListener('keydown',loop); }
  function releaseAnalyticsFocus(){ if(analyticsModal.__trapHandler){ document.removeEventListener('keydown',analyticsModal.__trapHandler); analyticsModal.__trapHandler=null; } if(prevFocus && typeof prevFocus.focus==='function') prevFocus.focus(); }
}

// Email Report
function buildEmailBody(){
  const total = ERRORS.length;
  const errs = ERRORS.filter(e=>e.severity==='ERROR');
  const warns = ERRORS.filter(e=>e.severity==='WARN');
  const infos = ERRORS.filter(e=>e.severity==='INFO');
  const resolved = RESOLVED_COUNT;
  const resolvedPct = total? Math.round((resolved/total)*100):0;
  const files = PENDING_FILE_NAMES.length ? PENDING_FILE_NAMES : [];
  const lines = [];
  lines.push('This is an automated log analysis report generated by the Log Analyzer tool.');
  if(emailFrom && emailFrom.value){ lines.push(`Reporter: ${emailFrom.value}`); }
  lines.push('');
  // Metrics summary
  lines.push('Summary Metrics');
  lines.push('---------------');
  lines.push(`Total Entries: ${total}`);
  lines.push(`Errors: ${errs.length}`);
  lines.push(`Warnings: ${warns.length}`);
  lines.push(`Info: ${infos.length}`);
  lines.push(`Resolved (this session): ${resolved} (${resolvedPct}%)`);
  lines.push('');
  // Files table (markdown style kept simple for mail clients)
  if(files.length){
    lines.push('Files Ingested');
    lines.push('--------------');
    lines.push('| # | File Name |');
    lines.push('|---|-----------|');
    files.forEach((f,i)=> lines.push(`| ${i+1} | ${f} |`));
    lines.push('');
  }
  // Top Errors (first 15)
  if(errs.length){
    lines.push('Top Error Samples (first 15)');
    lines.push('-----------------------------');
    errs.slice(0,15).forEach((e,i)=>{
      const msg=(e.message||'').replace(/\s+/g,' ').slice(0,240);
      lines.push(`${i+1}. ${msg}`);
    });
    if(errs.length>15) lines.push(`... ${errs.length-15} more error entries not shown.`);
    lines.push('');
  } else {
    lines.push('No ERROR level entries detected.');
    lines.push('');
  }
  // Recommended next steps
  lines.push('Recommended Next Steps');
  lines.push('----------------------');
  if(errs.length){
    lines.push('- Review unresolved critical errors and generate resolutions as needed.');
    lines.push('- Group recurring patterns and batch resolve where appropriate.');
  } else {
    lines.push('- No immediate error remediation required.');
  }
  lines.push('- Share this report with stakeholders if follow-up actions are required.');
  lines.push('- Re-run analysis after applying fixes to measure improvement.');
  lines.push('');
  lines.push('Disclaimer: This automated summary may omit contextual nuances present in full logs. Validate critical actions manually.');
  return lines.join('\n');
}
function openEmailModal(){
  if(!emailModal) return;
  if(emailSubject && !emailSubject.value){
    const d=new Date();
    const y=d.getFullYear();
    const m=String(d.getMonth()+1).padStart(2,'0');
    const day=String(d.getDate()).padStart(2,'0');
    emailSubject.value = `Automated Log Analysis Report - ${y}-${m}-${day}`;
  }
  emailBody && (emailBody.value = buildEmailBody());
  emailModal.classList.remove('hidden');
  emailModal.setAttribute('aria-hidden','false');
  trapEmailFocus && trapEmailFocus();
}
function closeEmailModal(){ if(emailModal && !emailModal.classList.contains('hidden')){ emailModal.classList.add('hidden'); emailModal.setAttribute('aria-hidden','true'); releaseEmailFocus(); } }
btnEmailReport && btnEmailReport.addEventListener('click',openEmailModal);
emailClose && emailClose.addEventListener('click',closeEmailModal);
emailModal && emailModal.addEventListener('click',e=>{ if(e.target===emailModal) closeEmailModal(); });
btnCopyEmailBody && btnCopyEmailBody.addEventListener('click',()=>{ if(emailBody.value){ navigator.clipboard.writeText(emailBody.value); toast({title:'Copied',msg:'Email body copied'}); } });
btnGenerateMailto && btnGenerateMailto.addEventListener('click',()=>{ generateMailto(false); });
btnSendOutlook && btnSendOutlook.addEventListener('click',()=>{ generateMailto(true); });
function generateMailto(open){
  if(emailBody && !emailBody.value){ emailBody.value = buildEmailBody(); }
  const to=(emailTo.value||'').split(/;|,/).map(s=>s.trim()).filter(Boolean).join(';');
  const subject=encodeURIComponent(emailSubject.value||'Log Analyzer Error Report');
  const body=encodeURIComponent(emailBody.value||buildEmailBody());
  const url=`mailto:${to}?subject=${subject}&body=${body}`;
  if(open){ window.location.href=url; }
  else { toast({title:'Mailto',msg:'Link generated'}); }
}
// Focus trap for email modal
let emailPrevFocus=null;
function trapEmailFocus(){ emailPrevFocus=document.activeElement; const selectors='button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'; function loop(e){ if(!emailModal || emailModal.classList.contains('hidden')) return; if(e.key==='Escape'){ closeEmailModal(); return; } if(e.key!=='Tab') return; const focusables=[...emailModal.querySelectorAll(selectors)].filter(el=>!el.disabled && el.offsetParent!==null); if(!focusables.length) return; const first=focusables[0]; const last=focusables[focusables.length-1]; if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); } else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); } } emailModal.__trapHandler=loop; document.addEventListener('keydown',loop); }
function releaseEmailFocus(){ if(emailModal && emailModal.__trapHandler){ document.removeEventListener('keydown',emailModal.__trapHandler); emailModal.__trapHandler=null; } if(emailPrevFocus && typeof emailPrevFocus.focus==='function') emailPrevFocus.focus(); }
