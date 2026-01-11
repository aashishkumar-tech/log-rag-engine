# Function Flow (Current FastAPI + LangChain Version)

Focused reference of active functions/classes only (legacy ingestion/, processing/, indexing/, rerank code removed).

Legend: I=Inputs  O=Outputs  SE=Side Effects  * = Potential performance hotspot

---
## api.py (Selected)
### upload(files) -> JSON
I: Multipart file list
Flow:
 1. Read file bytes -> lines
 2. Extract issue docs (ERROR/WARN lines) with metadata (source, line_no, severity)
 3. Build snippets (neighbor lines)
 4. Build context chunks (windowed splitter)
 5. If ASYNC_BUILD=1 -> schedule _index_build(issue_docs, context_docs) in background
 6. Else call vectorstores.build(issue_docs, context_docs) then rebuild QA chain
O: { issues:[...], index_building:bool, qa_ready:bool }
SE: Disk writes (if persistence enabled)

### resolve(id) -> JSON
I: issue id
Flow: fetch issue text -> run QA chain (question = issue message) -> return answer + citations
O: { answer:{ text, citations[] } }

### stats() / health()
Provide readiness flags: vector_initialized, retriever_ready, qa_ready, index_building

### reset()
Clears in-memory stores and deletes index dir (unless disabled) -> forces rebuild on next upload

---
## rag/loaders.py
### load_log_files(file_paths) -> List[Document]
Reads raw files line-by-line; returns Documents with metadata {source, line_no}

### extract_issue_docs(all_line_docs) -> List[Document]
Filters for lines containing 'ERROR' or 'WARN'; metadata adds severity

---
## rag/splitter.py
### split_context(docs, chunk_size, chunk_overlap) -> List[Document]
Simple text chunking across lines preserving (source, line_no) of first line in chunk

---
## rag/embeddings.py
### get_embeddings(backend) -> Embeddings
backend: 'hf' (default SentenceTransformers MiniLM) or 'openai' if env + package available

---
## rag/vectorstore.py (VectorStores)
### build(issue_docs, context_docs)
Embeds all docs -> FAISS.from_documents + BM25Retriever.from_documents; persists if enabled

### add(new_issue_docs, new_context_docs)
Extends internal doc lists then rebuilds (full rebuild simplicity)

### as_retrievers(k=8) -> (vector_retriever?, bm25_retriever?)
Returns configured retrievers (vector may be None until built)

Persistence:
- _persist(all_docs): save_local FAISS + JSON doc dump for BM25 rebuild
- _try_load(): best-effort disk load at init

---
## rag/retriever.py
### get_ensemble(vector_retriever, bm25_retriever) -> Retriever
Returns:
- Both present: EnsembleRetriever (score normalized merge)
- Only one: that retriever

---
## rag/chain.py
### build_chain(retriever) -> QA_CHAIN
Creates RetrievalQA chain (stuff) with prompt template (diagnosis style). Chooses LLM:
- AzureChatOpenAI if AZURE env vars present
- ChatOpenAI else

### run_qa(chain, query) -> dict
Executes chain.invoke({'query': query}) -> returns {'text': answer, 'citations': extracted metadata list}

---
## utils/logger.py
### get_logger(name) -> Logger
Basic stdout logger (used optionally)

---
## In-Memory Structures
| Name | Description |
|------|-------------|
| ERROR_STORE | id -> issue dict (severity, snippet, message, file, line_no) |
| VECTORSTORES | Singleton VectorStores instance |
| QA_CHAIN | RetrievalQA chain or None |
| BUILD_FLAGS | { index_building, qa_ready } |

---
## Query Flow (Simplified)
issue_id -> resolve() -> issue.message -> retriever.get_relevant_documents -> prompt -> LLM -> answer

---
## Error / Edge Handling
| Function | Behavior |
|----------|----------|
| upload | Returns empty issues list if no ERROR/WARN lines |
| resolve | 404 if id missing; 503 if QA not ready |
| build_chain | Raises if no retriever (no docs yet) |
| _try_load | Logs warning on failure, continues clean state |

---
## Performance Hotspots
| Area | Note |
|------|------|
| Embedding build | Dominant on first upload (FAISS + BM25) |
| LLM invoke | Network latency & token cost |

---
## Extension Points
| Need | Where |
|------|------|
| Add severity filter | modify retriever logic before merging |
| Reranking | Wrap retriever results before QA chain |
| Caching answers | Decorate run_qa with (query + doc ids hash) |
| Streaming responses | Replace RetrievalQA with streaming LLM calls |
| Incremental indexing | Implement doc id hashing before build() |

---
## Minimal Document Shapes
Issue Document metadata:
```
{ 'source': 'foo.log', 'line_no': 57, 'severity': 'ERROR' }
```
Context Document metadata:
```
{ 'source': 'foo.log', 'line_no': 120 }
```
Answer object:
```
{ 'text': 'diagnosis...', 'citations': [ { 'source': 'foo.log', 'line_no': 57 }, ... ] }
```

---
## Removed Legacy Functions (Reference Only)
normalize_records, assign_run_ids, taxonomy classification, cross-encoder reranker, context_builder, generator, summarizer
