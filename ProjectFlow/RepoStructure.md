# Repository Structure (Current)

```text
RAG-Pipeline/
├─ api.py                  # FastAPI app (upload, resolve, stats, reset, ui)
├─ headless_test.py        # Scripted ingestion + query example
├─ cli_inspect.py          # (Optional) quick inspection utilities
├─ config/
│  └─ settings.toml        # Basic tunables (chunk sizes, etc.)
├─ data/
│  └─ index/               # Persisted FAISS + bm25_docs.json
├─ rag/
│  ├─ loaders.py           # load_log_files, extract_issue_docs
│  ├─ splitter.py          # split_context
│  ├─ embeddings.py        # get_embeddings backend selector
│  ├─ vectorstore.py       # VectorStores (FAISS + BM25 + persistence)
│  ├─ retriever.py         # Ensemble / single retriever construction
│  ├─ chain.py             # build_chain + run_qa (RetrievalQA)
│  └─ __init__.py
├─ utils/
│  └─ logger.py            # Basic logger helper
├─ web/
│  ├─ index.html           # Single-page UI
│  ├─ app.js               # UI logic (upload, resolve, toasts)
│  └─ styles.css           # Styling
├─ tests/
│  ├─ test_end_to_end.py   # Upload → resolve pipeline test
│  └─ test_taxonomy.py     # (Legacy test placeholder - can be removed)
├─ ProjectFlow/            # Documentation (updated to simplified flow)
│  ├─ CheatSheet.md
│  ├─ CodeFlowOverview.md
│  ├─ FunctionFlow.md
│  ├─ Flow Recap (One Log Journey).md
│  ├─ Implementation Flow.md
│  ├─ HLD.md
│  ├─ Prerequisites.md
│  ├─ RepoStructure.md
│  ├─ CostAnalysis.md
│  └─ SampleFlowExample.md (legacy example; to update/remove)
├─ requirements.txt        # Dependency pins (lean stack)
├─ README.md               # Top-level overview
└─ result.json / run*.json # Sample run artifacts
```

## Notes
| Item | Status |
|------|--------|
| Legacy ingestion/processing/indexing folders | Removed (logic collapsed into rag/*) |
| Taxonomy / rerank modules | Removed |
| tests/test_taxonomy.py | Legacy; consider pruning |
| SampleFlowExample.md | Still legacy example (next to update) |

## Regeneration
- Delete `data/index/` and call `/reset` or re-upload to rebuild stores.

## Extension Targets
| Area | File |
|------|------|
| Custom ranking | `rag/retriever.py` |
| Alternate prompt | `rag/chain.py` |
| New file formats | `rag/loaders.py` |
| Auth / middleware | `api.py` |

Structure emphasizes minimal surface for faster iteration.
