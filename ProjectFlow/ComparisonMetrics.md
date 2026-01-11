# Ingestion & Retrieval Comparison Metrics

Purpose: Provide a single reference capturing size, time, cost-relevant signals for each ingestion run to compare optimizations.

## Metrics Definition
| Field | Description |
|-------|-------------|
| run_id | UUID if TRACE_RUN enabled; else blank |
| timestamp | ISO time when ingestion completed (index build end) |
| source_files | Number of uploaded files |
| total_lines | Total raw log lines processed before filtering |
| filtered_lines | Lines retained after pre-filter (future feature) |
| issue_count | Extracted issue/error/warn documents |
| context_chunks | Number of context chunks after splitting |
| chunk_size | Config CHUNK_SIZE used |
| chunk_overlap | Config CHUNK_OVERLAP used |
| embedded_docs | Documents actually embedded (after SKIP_ISSUE_EMBED) |
| bm25_enabled | Boolean if BM25 active post-build |
| bm25_auto_disabled | Boolean if auto threshold disabled BM25 |
| bm25_auto_threshold | Threshold value used |
| bm25_docs_used | Docs given to BM25 (cap) |
| faiss_ms | Milliseconds to build/add FAISS phase |
| bm25_ms | Milliseconds for BM25 construction/update |
| persist_ms | Milliseconds for persistence to disk |
| total_ms | Total build/add duration |
| incremental | Whether incremental add path was used |
| model_name | Active LLM model (answer stage) |
| embed_backend | Embedding backend selected |
| estimated_context_tokens | Approx tokens of concatenated retrieval context per future query (heuristic) |
| memory_est_mb | Estimated embedding vectors memory footprint |

## Collection Approach
1. During /upload completion (background or sync), gather raw counts (issue_docs, context_docs).  
2. After vectorstore build/add, pull last timing via VECTORSTORES.get_last_timing().  
3. Compute memory_est_mb = embedded_docs * embedding_dim * 4 / 1e6 (float32). (Need embedding_dim from backend model; MiniLM-L6 = 384)  
4. Store record appended to logs/runs/<run_id>-metrics.jsonl (or metrics.log if no run_id).  
5. Optionally expose latest metrics via /stats (future flag).  

## Heuristics
- estimated_context_tokens ≈ context_chunks * (chunk_size * 0.75 / 4) (rough char→token conversion 4 chars/token; assume average utilization 75%).  
- memory_est_mb accuracy improves if using actual dimension from embedding model instance.  

## Usage
Compare successive ingests to validate improvements (e.g., BM25 gating reduces bm25_ms; larger chunk_size reduces context_chunks and total_ms).  

## Example Record
```json
{
  "run_id": "3049c946-05eb-4e07-84cc-7d1f67761fd2",
  "timestamp": "2025-10-09T12:34:56Z",
  "source_files": 3,
  "total_lines": 205432,
  "filtered_lines": 205432,
  "issue_count": 982,
  "context_chunks": 12450,
  "chunk_size": 1000,
  "chunk_overlap": 150,
  "embedded_docs": 12450,
  "bm25_enabled": false,
  "bm25_auto_disabled": true,
  "bm25_auto_threshold": 20000,
  "bm25_docs_used": 0,
  "faiss_ms": 87456.22,
  "bm25_ms": 0.0,
  "persist_ms": 1120.54,
  "total_ms": 90200.91,
  "incremental": false,
  "model_name": "gpt-4o",
  "embed_backend": "hf",
  "estimated_context_tokens": 934000,
  "memory_est_mb": 19.15
}
```

## Future Extensions
- Add prompt/completion token accounting per /resolve.
- Track duplicate/skipped lines for dedupe effectiveness.
- Add failure counters (embedding_retry, skipped_batches).
- Capture CPU time vs wall time for embedding concurrency evaluation.

## Implementation Notes
- Minimal code touch: api.py after build completion, append to metrics file.
- Guard with METRICS_LOG=1 env to enable.
- Use jsonlines for efficient append.

## Benefits
Provides empirical feedback loop to tune chunking, gating thresholds, and embedding strategies toward lower latency and cost.
