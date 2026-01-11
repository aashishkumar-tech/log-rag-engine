# Call Flow Deep Dive – Function Jump Map (End‑to‑End)
Date: 2025-09-23
Scope: Current implementation (FastAPI + Hybrid Retrieval + UI v7)

Notation:
Module.Function()  -> next call
[SE] = Side Effect   [COND] = Conditional branch   (*) = Potential performance hotspot

---
## 1. Upload (ASYNC_BUILD = 1)
POST /upload  (api.upload)
  -> tempfile.NamedTemporaryFile (per file) [SE: disk temp]
  -> load_log_files(paths)  (rag.loaders)
       -> open() line iteration -> construct Document(list) with metadata
  -> extract_issue_docs(docs)  (rag.loaders)
  -> build snippets inline (loop) using in‑memory line grouping
  -> split_context(docs, CHUNK_SIZE, CHUNK_OVERLAP)  (rag.splitter)
  -> background task scheduled: _index_build(issue_docs, context_docs)
     (returns immediately to client with index_building=True, qa_ready=False)

Background thread: _index_build(issue_docs, context_docs)
  -> acquire STATE_LOCK
  -> if VECTORSTORES.faiss_store is None:
         VectorStores.build(issue_docs, context_docs)
     else:
         VectorStores.add(issue_docs, context_docs)
       VectorStores.build / add:
         -> embed context docs (*)  (rag.embeddings via internal call)
         -> construct FAISS index (*)
         -> build BM25 retriever (tokenization) (*)
         -> (optional) persist FAISS + BM25 state [SE: disk]
  -> _rebuild_chain()
       -> VECTORSTORES.as_retrievers(k)  (returns vector & bm25 retrievers)
       -> build_ensemble(vector, bm25)  (rag.retriever)
       -> build_chain(ensemble, model_name)  (rag.chain)
            -> (LLM client init) (*)
  -> set BUILDING = False

Client Side (web/app.js)
 upload() -> fetch /upload
    -> render issues list skeleton -> after response: ERRORS assigned
    -> pollStats(true): set timer every 2s
       pollStats() -> GET /stats -> if index_building True continue; once qa_ready True:
         -> stopIndeterminate(); enable Generate button

---
## 2. Upload (ASYNC_BUILD = 0)
POST /upload (api.upload)
  (same initial steps) THEN inside request thread:
  -> VectorStores.build / add (blocking) (*)
  -> _rebuild_chain()
  -> return issues with qa_ready=True immediately (no polling wait required)

---
## 3. Issue Selection + Context Retrieval
Frontend selectIssue(id)
  -> (local) CURRENT_ID update
  -> fetchSources(id)
       -> GET /context?id=...
           api.get_context
             -> row = ERROR_STORE[id]
             -> fetch_sources(ENSEMBLE, query=row['message']) (rag.retriever)
                 -> ensemble.get_relevant_documents(query)
                      -> vector_retriever.get_relevant_documents(query) (*)
                          -> FAISS similarity search
                      -> bm25_retriever.get_relevant_documents(query)
                      -> merge + reweight scores (custom logic)
             -> build citations list (source, line_no)
           Response -> UI populate sources list

---
## 4. Single Resolution
User clicks Generate (btnResolve)
 resolve() (frontend)
   -> POST /resolve with id
     api.resolve
       -> row = ERROR_STORE[id]
       -> run_qa(QA_CHAIN, row['message']) (rag.chain)
           RetrievalQA.invoke({'query': message})
             -> retriever.get_relevant_documents(query)  (same ensemble path)
             -> assemble prompt (sections)
             -> LLM call (*)
             -> produce answer text
           -> convert returned docs to sources list
       -> store row['_answer'] = result; row['answer_ts'] = now [SE]
       -> return {'answer': {text, citations}}
   -> UI updates resolutionBox + increments RESOLVED_COUNT

503 Retry Path:
 If /resolve returns 503 (QA not ready)
   -> frontend waits ~1200ms -> pollStats() -> reattempt resolve()

---
## 5. Batch Resolution
User selects multiple -> clicks Batch Resolve
 batchResolve() (frontend)
   -> POST /resolve_batch {ids:[...]}
     api.resolve_batch
       loop ids:
         row = ERROR_STORE[id]
         run_qa(QA_CHAIN, row['message']) (same path per id) (*)
         row['_answer']=res; row['answer_ts']=now
       aggregate per-id statuses
   -> UI success toast & count update

---
## 6. Manual Mark Resolved
batchMarkResolved() (frontend)
  -> POST /mark_resolved {ids, resolved:true}
     api.mark_resolved
       loop ids: row['manual_resolved']=True; set answer_ts if absent
  -> UI marks visually (.resolved class)

---
## 7. Export (Global or Selected)
Frontend (global): btnExport -> exportX()
  -> GET /export?format=csv&lite=1 (example)
    api.export
      -> parse params (format|fmt, ids?, lite?)
      -> iterate ERROR_STORE -> build payload list
      -> branch:
         json: return JSON object
         md: build pipe table
         csv: csv.DictWriter -> text/csv Response stream
         xlsx: openpyxl.Workbook -> write rows -> binary stream
  -> Browser downloads file

Selected subset path: batchExport()
  -> includes ids=comma,separated
  -> same export code but filtered

---
## 8. Stats Polling & Readiness Loop
pollStats() (frontend)
  -> GET /stats
     api.stats
       -> severity_counts via Counter
       -> resolved_total derived from ERROR_STORE
       -> return readiness booleans (vector_initialized, retriever_ready, qa_ready, index_building)
  -> frontend: update flags, QA_READY, progress bar state, interaction lock (setInteractionLock)

---
## 9. Interaction Lock Cycle
During indexing:
 pollStats() -> d.index_building True -> setInteractionLock(true)
   setInteractionLock(true): add body.locked (CSS disables pointer-events for [data-lockable])
 After build completes -> pollStats() -> index_building False -> setInteractionLock(false)

Exemptions:
 searchBox + filter buttons flagged as lock-exempt; remain interactive.

---
## 10. Reset
POST /reset?confirm=true&preserve_errors=false
  api.reset
   -> acquire STATE_LOCK
   -> delete FAISS_DIR + BM25_STATE (best effort) [SE: disk]
   -> reinitialize VectorStores (empty)
   -> clear ERROR_STORE (unless preserve_errors)
   -> ENSEMBLE=None; QA_CHAIN=None
   -> next /upload triggers full rebuild

---
## 11. Internal Build vs Add
Scenario: second upload after first build finished
  /upload -> extract issue_docs/context_docs
  ASYNC_BUILD triggers _index_build
    -> VectorStores.add(...)
        -> (Implementation simplicity) may rebuild FAISS/BM25 from combined docs (*)
        -> Persist new index
    -> _rebuild_chain() (fresh ensemble + QA chain)

---
## 12. Ensemble Retrieval Merge (Conceptual Jump)
vector_results = FAISS k docs (scores normalized)
lexical_results = BM25 k docs (BM25 scores normalized)
for doc in union:
  combined_score = w_vec * vec_score + w_bm25 * bm25_score
sort combined_score desc -> take top K -> pass to chain

---
## 13. Answer Object Structure
run_qa() returns (normalized):
{
  'answer': <str>,
  'sources': [ {'source': file, 'line_no': line}, ... ]
}
Stored in ERROR_STORE[id]['_answer'] untouched (plus timestamp).

---
## 14. Failure / Edge Path Call Sequences
A. Resolve before indexing finished:
  resolve() -> QA_CHAIN is None -> 503 -> frontend retry logic -> pollStats loop
B. XLSX export missing dependency:
  export() -> import openpyxl fails -> HTTPException 400 returned
C. Background build exception:
  _index_build() except block logs error -> BUILDING False; QA_CHAIN may stay None -> repeated 503 until next upload

---
## 15. High-Level Sequence Diagram (Text Form)
UPLOAD (async)
User -> api.upload -> loaders/splitter -> (return issues) -> BG:_index_build -> VectorStores.build -> _rebuild_chain -> build_ensemble -> build_chain
User(select) -> api.context(get_context) -> fetch_sources -> ensemble retrieval
User(resolve) -> api.resolve -> run_qa -> RetrievalQA -> ensemble retrieval -> LLM -> answer -> ERROR_STORE update
User(export) -> api.export -> format branch -> stream response

---
## 16. Primary Jump Table (Function → Next Hop)
| Function | Primary Next Calls |
|----------|--------------------|
| api.upload | load_log_files, extract_issue_docs, split_context, _index_build/build+_rebuild_chain |
| _index_build | VectorStores.build/add, _rebuild_chain |
| _rebuild_chain | VectorStores.as_retrievers, build_ensemble, build_chain |
| build_chain | (LLM client init), RetrievalQA construction |
| api.get_context | fetch_sources |
| fetch_sources | ensemble.get_relevant_documents |
| ensemble.get_relevant_documents | vector_retriever + bm25_retriever |
| api.resolve | run_qa |
| run_qa | RetrievalQA.invoke (retriever + LLM) |
| api.resolve_batch | run_qa (loop) |
| api.mark_resolved | (none – inline state updates) |
| api.export | (payload loop) -> csv/md/xlsx formatting functions |
| api.stats | Counter(), derive resolved_total |
| app.js.upload | fetch /upload -> pollStats |
| app.js.pollStats | fetch /stats -> setInteractionLock, start/stop progress |
| app.js.resolve | fetch /resolve (+ optional retry) |
| app.js.batchResolve | fetch /resolve_batch |
| app.js.fetchSources | fetch /context |

---
## 17. Performance Focus Points
| Step | Cost Driver | Mitigation Options |
|------|-------------|-------------------|
| Embedding (build/add) | Model inference | Batch embed, cache vectors |
| Retrieval (FAISS + BM25) | Top-k scans | Limit k, compress index |
| LLM invocation | API latency & tokens | Use smaller model, add answer cache |

---
## 18. Quick Trace Examples
A. From Log Line to Answer:
log line -> load_log_files -> extract_issue_docs -> issue.id -> resolve -> run_qa -> retriever -> FAISS+BM25 -> prompt -> LLM -> answer stored

B. Marking Resolved (No LLM):
checkbox select -> batchMarkResolved -> /mark_resolved -> set manual_resolved -> UI re-render

C. Export Selected Lite:
select ids -> batchExport -> /export?format=csv&ids=...&lite=1 -> build payload subset -> csv writer -> Response stream -> download

---
## 19. Future Insert Points (Where New Functions Would Jump In)
| Feature | Insert After |
|---------|--------------|
| Reranker | fetch_sources (post-ensemble merge) |
| Streaming Answers | run_qa: replace invoke with token stream yield |
| Persistent Warm Load | App startup: call VectorStores.try_load() then _rebuild_chain() if success |
| Dedup Similar Issues | After extract_issue_docs: cluster & fold duplicates |
| Semantic Caching | Before run_qa: check (issue.message hash) cache |

---
## 20. Summary
This document maps every major functional jump from initial ingestion to export. Use sections 1–8 for runtime tracing, 16 for quick navigation, and 19 for planned extension insertion points.

End of File.
