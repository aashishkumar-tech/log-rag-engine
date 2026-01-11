# RAG Pipeline – Detailed Architecture & Code Flow Guide

Version: 2025-09-23  
Scope: Current simplified FastAPI + LangChain + Hybrid Retrieval + Minimal Enterprise UI (v7)

---
## 1. Executive Summary
This project ingests raw log files, extracts error/warning lines ("issues"), builds a hybrid retrieval index (FAISS vectors + BM25 lexical), and provides on‑demand AI resolutions for each issue. The UI supports upload → inspect → resolve → batch operations → multi‑format export. Indexing may be asynchronous; readiness gating prevents premature resolution calls.

---
## 2. High-Level Flow
```
User Uploads Logs --> /upload
   ├─ Parse + Extract issue lines
   ├─ Chunk context (surrounding lines & full logs)
   ├─ (Async) Build / augment FAISS + BM25 stores
   └─ Return issues immediately (QA may still be building)

User Selects Issue in UI
   ├─ UI fetches context sources (/context)
   └─ User clicks Generate (/resolve) once QA ready

Resolution Returned
   ├─ Stored in ERROR_STORE[id]._answer
   └─ Marked resolved (auto or manual batch mark)

Exports (/export) JSON / CSV / XLSX (optionally filtered or lite)
```

---
## 3. Core Components
| Layer | File(s) | Responsibility |
|-------|---------|----------------|
| API | `api.py` | Endpoints, global state, indexing orchestration |
| Retrieval | `rag/vectorstore.py` | FAISS + BM25 management |
| Embeddings | `rag/embeddings.py` | HuggingFace (or OpenAI) embedding backend |
| Split / Chunk | `rag/splitter.py` | Context windows for retrieval |
| Loader | `rag/loaders.py` | Log file reading & issue extraction (severity rules) |
| Retriever builder | `rag/retriever.py` | Ensemble (weighted vector + BM25) and source fetch |
| QA Chain | `rag/chain.py` | LangChain RetrievalQA construction + custom prompt |
| Wrapper | `rag/wrapper.py` | Reusable ingestion/query abstraction (not yet wired into API) |
| UI | `web/index.html`, `web/app.js`, `web/styles.css` | Interaction, progress, batch ops, accessibility |
| Utils | `utils/logger.py` | Structured logging |
| Tests | `tests/*.py` | Validation of taxonomy / end-to-end behavior |

---
## 4. Global State & Data Structures (`api.py`)
```python
VECTORSTORES: VectorStores  # holds FAISS + BM25 retrievers
ENSEMBLE: EnsembleRetriever | None
QA_CHAIN: RetrievalQA | None
ERROR_STORE: dict[id -> issue dict]
BUILDING: bool  # indexing in progress
LAST_BUILD_TS: float | None
```
Issue record canonical fields:
```
{
  id, severity, task_name, process_name, error_type,
  message, file_id, run_id, line_no, snippet,
  manual_resolved (bool), answer_ts (ISO), _answer (QA output, internal)
}
```

---
## 5. Indexing Lifecycle
1. `/upload` reads uploaded files into temp disk files.
2. `load_log_files()` → list[Document] each line (with metadata: source + line_no).
3. `extract_issue_docs()` filters ERROR/WARN lines.
4. Builds a snippet (±2 line window, marking the focal line with `>>`).
5. `split_context()` creates larger retrieval fragments for embedding.
6. If first time: `VECTORSTORES.build(issue_docs, context_docs)` else `.add()` (incremental augmentation).
7. `_rebuild_chain()` builds ensemble retriever + QA chain.
8. If `ASYNC_BUILD=1`, steps 6–7 run in a background thread; UI polls `/stats` until `qa_ready`.

---
## 6. Hybrid Retrieval Strategy
| Component | Purpose | Notes |
|-----------|---------|-------|
| FAISS (cosine) | Semantic similarity | Dense embeddings (sentence-transformers default) |
| BM25 | Lexical keyword match | Captures exact token relevance |
| EnsembleRetriever | Weighted merge | Default weights (0.6 vector, 0.4 BM25) |

`fetch_sources()` merges top-k docs for context & builds citation list: `[{source, line_no}]`.

---
## 7. QA Chain (`rag/chain.py`)
A LangChain RetrievalQA ("stuff" chain) pattern with a custom system prompt composed of sections:
- Diagnosis
- Evidence (supported by retrieved context)
- Remediation Steps
- Impact
- Uncertainty (explicit self-estimation)

Model selection via env var (`OPENAI_MODEL` or fallback to a local LLM if replaced). The chain returns:
```
{
  'answer': <string>,
  'sources': [ { 'source': <file>, 'line_no': <int>, ... }, ... ]
}
```

---
## 8. Endpoints Overview
| Method | Path | Summary | Key Response Fields |
|--------|------|---------|---------------------|
| POST | /upload | Stage files & trigger indexing | errors[], index_building, qa_ready |
| GET | /errors | List issues + resolved status | errors[] (resolved, answer) |
| GET | /context?id= | Retrieve citations for an issue | context.context_text, citations[] |
| POST | /resolve | Run QA for a single issue | answer.text, answer.citations |
| POST | /resolve_batch | Batch QA generation | results[] per id |
| POST | /mark_resolved | Manual mark/unmark | updated[] |
| GET | /export | Multi-format export | JSON / file stream |
| GET | /stats | Build + readiness + counts | qa_ready, index_building, resolved_total |
| GET | /ready | Lightweight readiness | qa_ready |
| POST | /reset | Reset indices (optional keep issues) | status |
| GET | /health | Simple health probe | status, retriever_ready |

### Export Parameters
- `format` or `fmt`: `json|md|csv|xlsx`
- `ids`: comma separated subset
- `lite=1`: reduced columns (id, severity, message, resolved)

---
## 9. Resolution & Resolved Semantics
An issue is considered resolved if:
- It has `_answer` (AI generated), or
- It is manually marked (`manual_resolved=true`)

`answer_ts` is recorded when the first resolution (AI or manual) occurs.

Batch operations:
- `/resolve_batch` – invokes QA for each id (skips missing).
- `/mark_resolved` – flips manual flag (no QA call).

---
## 10. UI Architecture (`web/`)
| Concept | Implementation |
|---------|---------------|
| Layout | Two panes (issues list / detail) + top actions & global progress |
| State | In-browser arrays (ERRORS), sets (SELECTED), flags (QA_READY) |
| Batch | Checkbox selection + batch bar (resolve/mark/export) |
| Progress | Global bar (indexing), mini resolved % bar, inline resolution bar |
| Skeleton | Placeholder list while server processes upload parsing |
| Sources | Lazy-loaded citations, collapsible panel |
| Accessibility | ARIA roles: progressbar, status regions, focus styling |
| Interaction Lock | Temporary body `.locked` during indexing (search/filter exempt) |
| Export | Dropdown format + Lite toggle + selected subset export |

### Frontend Flow (Upload)
```
User selects files → click Upload → show overlay & skeleton
POST /upload → receive errors[] (possibly qa_ready=false)
Render issues → If BUILDING: poll /stats every 2s → when qa_ready → enable Generate
```

### Frontend Flow (Resolve)
```
Select issue → fetch /context (citations) → user clicks Generate → POST /resolve
Show inline progress bar → replace with answer → mark resolved + update counts
```

---
## 11. Detailed Sequence Example
### Sample Log Snippet
```
2025-09-23 10:00:00 INFO Starting job X
2025-09-23 10:00:02 WARN Retryable network glitch
2025-09-23 10:00:05 ERROR Failed to connect to DB timeout=30s
2025-09-23 10:00:06 INFO Backoff scheduled
```
### Extraction
- WARN line and ERROR line become issue docs.
- Snippet for ERROR includes preceding WARN + following INFO lines (window ±2).

### Index Build
- Documents chunked (e.g., 1000 char windows).
- Embeddings generated → FAISS index updated → BM25 updated.
- Ensemble retriever constructed.

### Resolution
User selects ERROR → QA prompt contains:
- User Query: raw error line text.
- Context: weighted aggregate of top-k vector + BM25 chunks.
Model responds with structured answer. Citations list ties back to source file & lines.

---
## 12. Key Pseudocode Summaries
### Upload Handler (condensed)
```python
def upload(files):
  docs = load_log_files(temp_paths)
  issues = extract_issue_docs(docs)
  build_snippets(issues, docs)
  context_docs = split_context(docs)
  if ASYNC_BUILD: background(_index_build, issues, context_docs)
  else: VECTORSTORES.build(...); _rebuild_chain()
  return issues, qa_ready=not ASYNC_BUILD
```

### Resolve (single)
```python
def resolve(id):
  row = ERROR_STORE[id]
  assert QA_CHAIN
  res = run_qa(QA_CHAIN, row['message'])
  row['_answer']=res; row['answer_ts']=utc_now()
  return res['answer'], res['sources']
```

---
## 13. Configuration (Environment Variables)
| Variable | Default | Meaning |
|----------|---------|---------|
| CHUNK_SIZE | 1000 | Max characters per context chunk |
| CHUNK_OVERLAP | 150 | Overlap between chunks |
| TOP_K | 8 | Retrieval depth (merged) |
| EMBED_BACKEND | hf | Embedding provider (customizable) |
| OPENAI_MODEL | gpt-3.5-turbo | LLM model name if OpenAI used |
| ASYNC_BUILD | 1 | Enable background indexing |
| DISABLE_PERSIST | (unset) | If implemented, skip persistence (future) |

---
## 14. Wrapper (`rag/wrapper.py`) Usage Pattern
Purpose: Reuse ingestion + retrieval outside this FastAPI service.
```python
from rag.wrapper import RAGWrapper
rag = RAGWrapper(embedding_backend="hf")
rag.ingest_logs(["/path/app.log"])   # or ingest_texts([...])
rag.build()                           # explicit if not auto
res = rag.query("Failed to connect to DB timeout=30s")
print(res.answer, res.sources)
```
Integration Steps:
1. Instantiate once per tenant/session.
2. Feed logs or documents.
3. Call `build()` (or rely on auto call inside ingest if implemented).
4. Use `query()`; capture sources for UI.
5. Reset with `reset()` when switching datasets.

---
## 15. Exports Deep Dive
| Mode | Purpose | Notes |
|------|---------|-------|
| JSON | Raw list of issues + flags | Good for pipeline chaining |
| Markdown | Table for quick reports | Omits long text trimming logic (basic) |
| CSV | Full or lite | `lite=1` reduces size |
| XLSX | Spreadsheet consumption | Requires `openpyxl` |
| IDs Filter | `?ids=id1,id2` | Combine with format + lite |

---
## 16. Performance Considerations
| Aspect | Mitigation / Strategy |
|--------|----------------------|
| Large logs | Streaming parse line-by-line (current: reads into docs; can stream) |
| Many issues | Use virtualized list (future) |
| Embedding latency | Batch embeddings; potential async concurrency |
| Repeated queries | Introduce local answer cache keyed by (message hash) |
| Memory | Offload FAISS to disk (persist) |

Potential future: Add reranker (e.g., BGE, Cohere ReRank) after initial recall.

---
## 17. Error Handling & Status Codes
| Code | Scenario |
|------|----------|
| 400 | Missing files / invalid params / unsupported export format |
| 404 | Issue ID not found |
| 503 | QA chain not built yet (resolve early) |
| 500 | Internal errors (index build / XLSX save) |

UI automatically retries a 503 resolve once after a short delay.

---
## 18. Accessibility Checklist
| Feature | Status |
|---------|--------|
| ARIA progressbar | YES (global bar) |
| Live regions | YES (status, toasts) |
| Keyboard focus states | Unified via `:focus-visible` |
| Reduced motion toggle | NOT YET (planned) |
| Semantic buttons/labels | YES (copy, export, filters) |

Improvements: Add skip link, high-contrast toggle.

---
## 19. Security & Hardening (Future)
| Concern | Action |
|---------|--------|
| Arbitrary file upload | Enforce size caps & sanitize content |
| Prompt injection (logs) | Add guardrails / system prompt sanitation |
| Rate limiting | Add IP or token bucket (FastAPI middleware) |
| Auth | OAuth/JWT layer in front (e.g., API key header) |
| PII leakage | Optional redaction pass pre-index |

---
## 20. Extensibility Patterns
| Goal | Approach |
|------|----------|
| Add streaming answers | Replace `/resolve` with SSE or WebSocket yielding partial tokens |
| Swap embedding model | Extend `embeddings.py` to branch on `EMBED_BACKEND` |
| Add reranker | After merged docs, apply cross-encoder scoring; reorder before chain input |
| Multi-tenant | Instance map: `TENANTS[id] = { VECTORSTORES, ENSEMBLE, ... }` + per-tenant API key |
| Persistence | Serialize FAISS + BM25 state per build; load at startup |
| Doc ingestion beyond logs | Extend loader to accept PDFs/HTML → unify into wrapper |

---
## 21. Testing Strategy
Current tests (examples):
- `tests/test_end_to_end.py`: Validates end-to-end minimal ingestion & answer path.
- `tests/test_taxonomy.py`: Severity categorization rules.

Suggested additional tests:
- Export formatting integrity (CSV/XLSX columns)
- Batch resolve idempotency
- Async build gating (resolve returns 503 pre-ready)

---
## 22. Example Full cURL Session
```bash
# Upload two log files
curl -F "files=@app.log" -F "files=@worker.log" http://localhost:8000/upload

# Poll stats
curl http://localhost:8000/stats

# List errors
curl http://localhost:8000/errors

# Get context for one id
curl "http://localhost:8000/context?id=<ISSUE_ID>"

# Resolve one
curl -X POST -H 'Content-Type: application/json' -d '{"id":"<ISSUE_ID>"}' http://localhost:8000/resolve

# Batch resolve
curl -X POST -H 'Content-Type: application/json' -d '{"ids":["<ID1>","<ID2>"]}' http://localhost:8000/resolve_batch

# Export lite CSV for selected
curl "http://localhost:8000/export?format=csv&ids=<ID1>,<ID2>&lite=1" -o selected_lite.csv
```

---
## 23. Troubleshooting Matrix
| Symptom | Likely Cause | Remedy |
|---------|--------------|--------|
| 503 on /resolve repeatedly | Index build failed | Check server logs; look for exception in `_index_build` |
| CSV empty | No issues extracted | Confirm logs have ERROR/WARN tokens |
| XLSX 400 | Missing dependency | `pip install openpyxl` |
| Low quality answers | Insufficient context | Increase CHUNK_SIZE or TOP_K |
| Slow build | Large file set | Set ASYNC_BUILD=1 & show progress; consider chunk batching |

---
## 24. Roadmap (Suggested)
1. Streaming answer generation
2. Reranker integration (quality uplift)
3. Theming + light mode + high contrast
4. Multi-tenant wrapper adoption in API
5. Persistent on-disk index & warm start
6. Source excerpt highlighting in answer (inline citations)
7. Saved sessions & diff-based incremental indexing

---
## 25. Quick Glossary
| Term | Definition |
|------|------------|
| Issue | Single log line categorized as ERROR or WARN |
| Snippet | Local window lines around issue for human inspection |
| Context Chunk | Larger aggregated text unit used for retrieval embeddings |
| QA Chain | LLM-powered retrieval augmented question answering pipeline |
| Ensemble Retrieval | Weighted combination of vector similarity + BM25 lexical matches |

---
## 26. Minimal Integration (External Script)
```python
import requests, time
# Upload
files = [('files', ('app.log', open('app.log','rb'), 'text/plain'))]
upload = requests.post('http://localhost:8000/upload', files=files).json()
issue_id = upload['errors'][0]['id']
# Wait for readiness
while True:
    s = requests.get('http://localhost:8000/stats').json()
    if s['qa_ready']: break
    time.sleep(1)
# Resolve
ans = requests.post('http://localhost:8000/resolve', json={'id': issue_id}).json()
print(ans['answer']['text'])
```

---
## 27. Design Principles Applied
- Lean state: Only minimal metadata kept per issue; derived states (resolved flags) computed.
- Progressive disclosure: Sources hidden until toggled.
- Non-blocking ingestion: Async build path ensures fast UI feedback.
- Extensibility first: Wrapper isolates ingestion + retrieval surfaces.
- Accessibility baseline: ARIA roles, focus outlines, live regions.

---
## 28. Frequently Asked Questions
| Question | Answer |
|----------|--------|
| Can I use a different embedding model? | Set EMBED_BACKEND or modify `embeddings.py` to select model. |
| How to add new severity levels? | Extend extraction logic (loader) + badge styles. |
| Why hybrid retrieval? | Lexical (BM25) catches raw token errors; semantic matches contextual synonyms. |
| Is streaming supported? | Not yet—convert `/resolve` to an SSE endpoint with incremental token yield. |

---
## 29. Change Impact Areas
When modifying:
| Area | Check Also |
|------|------------|
| Retrieval weights | Prompt output quality, speed |
| Chunk sizing | Embedding latency, recall quality |
| Export schema | Frontend batch export naming |
| State shape (ERROR_STORE) | /errors, /export, tests |

---
## 30. Summary
This codebase implements a pragmatic, production-lean RAG workflow for log diagnostics: fast ingestion, hybrid retrieval, structured LLM resolutions, and actionable UI ergonomics. The architecture isolates concerns cleanly, enabling incremental upgrade (reranking, streaming, multi-tenancy) without rewrites. Refer to this document as an onboarding and extension blueprint.

---
End of Document.
