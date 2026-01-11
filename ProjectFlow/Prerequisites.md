# Project Prerequisites (Simplified Stack)

## 1. Environment
| Item | Requirement |
|------|-------------|
| OS | Windows 10/11 (Linux/macOS fine) |
| CPU | 4+ cores recommended |
| RAM | 8–16 GB (depends on log volume) |
| Disk | ~2 GB free for indices/cache |
| GPU | Optional (not required) |

## 2. Python
- Version: 3.10 / 3.11 (current tested)
- Create venv (PowerShell):
```
python -m venv .venv; . .venv\Scripts\Activate.ps1
```

## 3. Core Dependencies (Current)
| Purpose | Packages |
|---------|----------|
| Web API | fastapi, uvicorn |
| LLM / Chains | langchain, langchain-openai (if using OpenAI/Azure) |
| Embeddings (local) | sentence-transformers |
| Vector DB | faiss-cpu |
| Lexical | (BM25 via langchain_community BM25Retriever) |
| Utilities | python-dotenv (optional), pytest |

(Previously used whoosh, cross-encoder reranker, taxonomy libs — all removed.)

Install:
```
pip install -r requirements.txt
```

## 4. Keys / Credentials
| Need | Vars |
|------|------|
| Azure OpenAI (optional) | AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT_NAME |
| OpenAI (fallback) | OPENAI_API_KEY |

If no keys present → local HF embeddings + (optionally) local model or disabled LLM until configured.

## 5. Environment Variables
| Var | Purpose | Default |
|-----|---------|---------|
| EMBED_BACKEND | 'hf' or 'openai' | hf |
| ASYNC_BUILD | Background index build | 0 |
| DISABLE_PERSIST | Skip saving FAISS/BM25 | 0 |
| TOP_K | Retrieval documents | 8 |
| CHUNK_SIZE | Approx chunk char size | 800 |
| CHUNK_OVERLAP | Overlap chars | 0 |

Set (PowerShell example):
```
$env:EMBED_BACKEND = 'hf'
$env:ASYNC_BUILD = '1'
```

## 6. Data Inputs Supported
| Format | Notes |
|--------|------|
| .txt / .log | Line-based logs |
| .json (planned) | Future enhancement |

(Current simplified flow treats inputs as plain text lines.)

## 7. Quick Start
```
uvicorn api:app --reload
# Open http://localhost:8000/ui/
```
Upload one or more .log/.txt files → wait for index build → click an issue → Resolve.

## 8. Validation Checklist
| Check | Command |
|-------|---------|
| Python version | python -V |
| Install deps | pip install -r requirements.txt |
| API starts | uvicorn api:app --reload |
| Health ready | curl http://localhost:8000/health |

## 9. Common Issues
| Symptom | Fix |
|---------|-----|
| FAISS import error | Reinstall `faiss-cpu` (wheel architecture mismatch) |
| 503 on resolve | Wait until `/stats` shows `qa_ready: true` |
| No issues listed | File lacks 'ERROR'/'WARN' lines (case sensitive) |
| Slow upload | Enable `ASYNC_BUILD=1` or reduce CHUNK_SIZE |

## 10. Future Enhancements
| Area | Plan |
|------|------|
| JSON input | Add loader for structured event arrays |
| Incremental build | Hash-based skip for unchanged files |
| Auth | API key or JWT layer |
| Streaming LLM | SSE / websocket for live tokens |

Simplified prerequisites reflect the lean architecture now deployed.
