# Single Log Line Journey

Illustrates how one raw ERROR log line moves through the RAG pipeline from ingestion to answer generation.

## 1. Raw Log Line
```csv
ERROR,2025/09/16 04:47:37.000,ae2-rpa-d03-125,adm-in010025271,\Common\Credential\Credential_LoginFlow,BankDownloads,"Error: [Unable to locate child bot (BOA_Login) in the Control Room...] at Line [25]",""
```

## 2. Ingestion & Normalization
| Field | Value |
|-------|-------|
| log_level | ERROR |
| timestamp_raw | 2025/09/16 04:47:37.000 |
| timestamp_iso | 2025-09-16T04:47:37Z |
| host | ae2-rpa-d03-125 |
| user | adm-in010025271 |
| task_name | \Common\Credential\Credential_LoginFlow |
| category | BankDownloads |
| description | Unable to locate child bot (BOA_Login) in the Control Room... |
| line_ref | 25 |
| run_id | (assigned) |
| step_idx | (sequence index) |

Actions:
- Detect CSV format and parse.
- Normalize timestamp to ISO.
- Extract line reference (25).
- Assign run_id via surrounding START/END markers.
- Increment step_idx.

## 3. Chunking & Enrichment
Chunk composition:
- Core ERROR line + ±10 neighboring context lines.
- Attach entities: child_bot=BOA_Login.
- Classify error_type=MissingChildBot.
- Severity=ERROR.

Optional enrichment:
- Summarizer produces short abstraction of repetitive lines.
- Taxonomy tags (credential_flow, missing_dependency).

## 4. Indexing
| Step | Result |
|------|--------|
| Embedding | all-MiniLM-L6-v2 → 384-d vector |
| Vector store | Insert into FAISS with metadata (ids, task_name, severity, error_type) |
| Lexical index | Store raw + normalized text in BM25 (Whoosh) |
| Metadata schema | Ensures filterable facets: date, severity, error_type, entity.child_bot |

## 5. User Query
User asks:
```
Why did login fail for Nashville lockbox 37?
```
Query normalization:
- Lowercase + strip punctuation.
- Extract key terms: login fail, Nashville, lockbox 37.
- Map synonyms (login → credential; fail → error).

## 6. Hybrid Retrieval
Process:
1. BM25 retrieves candidates with exact terms (loginflow, lockboxId 37, error).
2. FAISS retrieves semantic matches (child bot missing, credential flow failure).
3. Merge + dedupe (Jaccard / ID set).
4. Score normalization (z or min-max) prior to re-rank set selection.

## 7. Re-ranking
- Cross-encoder evaluates merged candidates.
- Produces relevance scores.
- Top-N selected (includes our ERROR chunk).
- Diversity filter removes near-duplicate credential errors.

## 8. Context Assembly
Included elements (ordered):
1. ERROR line (child bot missing).
2. Preceding INFO: credentials validated.
3. WARN: skipping Nashville lockbox 37.
4. Compact summary of prior successful attempts (if present).

Citations appended: (chunk_id, timestamp, task_name, line_range).

## 9. Prompt (Conceptual Skeleton)
```text
System: You are a diagnostic assistant...
User Question: Why did login fail for Nashville lockbox 37?
Context:
[1] (ERROR) 2025-09-16T04:47:37Z Unable to locate child bot (BOA_Login)...
[2] (WARN) 2025-09-16T04:47:35Z Skipping Nashville lockbox 37...
...
Instructions: Provide diagnosis, evidence citations, remediation, impact.
```

## 10. Answer Generation (Azure GPT-4o)
Model output (structured):
```json
{
  "diagnosis": "Login flow failed because required child bot BOA_Login was not found in the Control Room during Credential_LoginFlow.",
  "evidence": [
    {"citation": 1, "reason": "Direct missing bot error"},
    {"citation": 2, "reason": "Shows skipped target lockbox"}
  ],
  "remediation": [
    "Republish or upload BOA_Login bot to Control Room",
    "Verify correct folder / path mapping",
    "Check permissions for executing child bots"
  ],
  "impact": "Nashville ministry lockbox 37 was skipped in credential processing.",
  "confidence": 0.83
}
```

## 11. Key Trace Points
| Stage | Log Metric |
|-------|------------|
| Ingestion | records_loaded, parse_errors |
| Chunking | chunks_created, avg_tokens_per_chunk |
| Retrieval | k_vector, k_bm25, merged_size |
| Re-ranking | rerank_input, rerank_latency_ms |
| Context | context_tokens, unique_citations |
| Generation | prompt_tokens, completion_tokens, latency_ms |

## 12. Failure Modes & Mitigations
| Issue | Cause | Mitigation |
|-------|-------|-----------|
| Missing run_id | No START/END markers | Fallback heuristic by time gap |
| Low recall | Chunk too large | Reduce chunk token cap |
| Irrelevant context | Weak entity filtering | Add entity-weighted rerank feature |
| Hallucinated remediation | Insufficient evidence | Require minimum 2 citations before output |

## 13. Summary
This single ERROR line becomes a richly contextualized, retrievable knowledge element powering precise diagnostic answers with traceable evidence.

# Sample Flow Example (Simplified System)

Walk-through: uploading two log files and resolving one extracted issue.

## 1. Upload
User selects `app1.log` and `app2.log` in the UI and clicks Upload.

Backend (`POST /upload`):
1. Read lines from both files.
2. Extract issue docs (lines containing 'ERROR' or 'WARN').
3. Build display snippets (issue ± a few neighboring lines).
4. Chunk entire raw line set into context docs (fixed char window, no taxonomy).
5. Build indices (sync) OR schedule background build if `ASYNC_BUILD=1`.
6. Return JSON listing issues:
```
[
  {"id": "e_0", "severity": "ERROR", "line_no": 57, "file": "app1.log", "message": "Unable to locate child bot (BOA_Login)..."},
  {"id": "w_1", "severity": "WARN",  "line_no": 12, "file": "app2.log", "message": "Retry threshold approaching"}
]
```

## 2. Index Build (Details)
VectorStores.build:
- Concatenate issue + context docs -> embed -> create FAISS index.
- Create BM25Retriever over same docs.
- Persist: `data/index/faiss/` + `data/index/bm25_docs.json` (unless `DISABLE_PERSIST=1`).

If async:
- UI shows overlay "Indexing...".
- `/stats` polled until `qa_ready=true`.

## 3. Selecting an Issue
User clicks the ERROR item (id `e_0`). UI calls:
```
POST /resolve { "id": "e_0" }
```
Backend flow:
1. Lookup issue in ERROR_STORE.
2. Construct question text (issue message).
3. Call retriever (ensemble → FAISS + BM25 top-k merge).
4. Run RetrievalQA chain with merged documents.
5. Return answer.

## 4. Answer Response Example
```json
{
  "answer": {
    "text": "Login failed because required child bot BOA_Login was not found during the credential flow.",
    "citations": [
      {"source": "app1.log", "line_no": 57},
      {"source": "app1.log", "line_no": 55}
    ]
  }
}
```

## 5. Citations Mapping
The UI can highlight cited line numbers (e.g., scroll to line 57 in snippet panel).

## 6. Failure / Edge Examples
| Situation | Response |
|-----------|----------|
| Resolve before index built | 503 with message chain not ready |
| No issues found in upload | Empty array; QA chain not built |
| Duplicate file re-upload | Rebuilds entire store (no incremental diff yet) |

## 7. Metrics to Add (Planned)
| Metric | Purpose |
|--------|---------|
| build_time_ms | Track ingestion/index duration |
| vector_count | Number of docs indexed |
| last_build_at | UI freshness display |
| prompt_tokens / completion_tokens | Cost tracking |

## 8. Extending This Flow
| Enhancement | Where |
|-------------|------|
| Add streaming answer | Replace RetrievalQA call with streaming API |
| Introduce reranker | Insert step before QA invoke |
| File hash caching | Pre-check existing embeddings |

Lean example demonstrates core path without legacy taxonomy or rerank complexity.
