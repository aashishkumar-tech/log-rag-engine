# High-Level Design (Simplified FastAPI RAG)

Focus: Minimal ingestion + dual retrieval + RetrievalQA.

## Current Flow Diagram
```mermaid
graph LR
    classDef comp fill:#F0F7FF,stroke:#2563EB,color:#111;
    classDef store fill:#F5F5F5,stroke:#555,color:#111;
    classDef llm fill:#E8FDE8,stroke:#2F7D31,color:#111;
    U[User / UI] --> UP[/POST /upload/]
    UP --> EX[Extract Issues]
    EX --> SN[Build Snippets]
    EX --> CH[Chunk Context]
    SN --> IDX[VectorStores.build]
    CH --> IDX
    IDX --> FAISS[(FAISS)]
    IDX --> BM25[(BM25)]
    U --> RS[/POST /resolve/]
    RS --> RT[Retriever (Ensemble)]
    RT --> FAISS
    RT --> BM25
    RT --> QA[RetrievalQA Chain]
    QA --> ANS[(Answer + Citations)]
    class U comp; class UP,EX,SN,CH,IDX,RT,QA comp; class FAISS,BM25 store; class ANS llm;
```

## Stage Descriptions
| Stage | Responsibility |
|-------|----------------|
| Upload | Accept files & orchestrate extraction/build |
| Extract Issues | Identify ERROR/WARN lines |
| Snippets | Surround issue lines with local context for display |
| Chunk Context | Fixed window chunking across raw lines |
| VectorStores.build | Embed + construct FAISS + BM25 retrievers |
| Retriever | Ensemble (vector + lexical) or single fallback |
| RetrievalQA | Prompt assembly + LLM answer generation |

## Key Simplifications vs Legacy
| Removed | Reason |
|---------|-------|
| Taxonomy / entity enrichment | Not required for initial diagnostic value |
| Session/run segmentation | Line-level sufficient |
| Cross-encoder reranking | Acceptable quality with ensemble only |
| Custom context builder | Handled internally by LangChain chain |
| Summarization | Defer until token pressure observed |

## Data Persistence
| Artifact | Location | Notes |
|----------|----------|------|
| FAISS index | data/index/faiss/ | Saved via save_local |
| Raw docs (JSON) | data/index/bm25_docs.json | Rebuild BM25 + FAISS on load |

Toggle persistence with `DISABLE_PERSIST=1`.

## Readiness Flags (stats)
| Flag | Meaning |
|------|---------|
| index_building | Background build running |
| qa_ready | QA chain constructed |

## Configuration (Env Vars)
| Variable | Effect | Default |
|----------|--------|---------|
| ASYNC_BUILD | Background index build | 0 |
| DISABLE_PERSIST | Skip saving/loading indices | 0 |
| EMBED_BACKEND | 'hf' or 'openai' embeddings | hf |
| CHUNK_SIZE | Context chunk size (lines/approx) | 800 chars (example) |
| CHUNK_OVERLAP | Overlap between chunks | 0 |
| TOP_K | Retrieval k | 8 |

## Failure Modes & Handling
| Scenario | Behavior |
|----------|----------|
| Resolve before ready | 503 QA chain not ready |
| Empty upload | Returns empty issues; no build |
| Load failure | Logs warning; start fresh |
| Missing OpenAI creds | Falls back to HF or errors if forced |

## Extension Roadmap
| Area | Next Step |
|------|----------|
| Ranking | Optional reranker plug-in |
| Incremental indexing | Per-file hash diff before rebuild |
| UI feedback | Auto-poll /stats until qa_ready |
| Streaming answers | Switch to streaming Chat API |
| Metadata filters | Severity-only / file-based filtering |

Minimal design keeps operational surface small while enabling quick iteration.
