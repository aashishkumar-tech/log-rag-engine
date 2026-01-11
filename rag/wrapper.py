"""Generic RAG wrapper so the same pipeline can be reused
for log troubleshooting, documentation QA, etc.

Goals:
  - Single class that hides: embeddings, vector stores, ensemble retriever, QA chain.
  - Incremental ingestion (logs or arbitrary documents) with automatic (re)build.
  - Optional async build hook (caller can thread it) – kept simple here.
  - Stable interface: ingest_*, query, status, reset.

Can be integrated into FastAPI routes in place of ad‑hoc globals currently in api.py.

Example:
    from rag.wrapper import RAGWrapper
    rag = RAGWrapper()
    rag.ingest_texts(["First doc text", "Second..."], meta_list=[{"source":"mem1"},{"source":"mem2"}])
    answer = rag.query("What is in the first doc?")

For logs you can still use existing loaders for richer per‑line metadata.
"""
from __future__ import annotations
from typing import List, Dict, Any, Iterable, Optional, Sequence
import threading
import os

from langchain_core.documents import Document

from .vectorstore import VectorStores
from .retriever import build_ensemble, fetch_sources
from .chain import build_chain, run_qa
from .splitter import split_context
from .loaders import load_log_files, extract_issue_docs


class RAGWrapper:
    def __init__(
        self,
        embedding_backend: str | None = None,
        model_name: str | None = None,
        top_k: int = 8,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        weights: tuple[float, float] = (0.6, 0.4),
    ):
        self.embedding_backend = embedding_backend or os.getenv("EMBED_BACKEND", "hf")
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.top_k = top_k
        self.chunk_size = chunk_size or int(os.getenv("CHUNK_SIZE", 1000))
        self.chunk_overlap = chunk_overlap or int(os.getenv("CHUNK_OVERLAP", 150))
        self.weights = weights

        self._vs = VectorStores(embedding_backend=self.embedding_backend)
        self._retriever = None
        self._qa_chain = None
        self._issue_docs: List[Document] = []  # high value / error docs
        self._context_docs: List[Document] = []  # supporting context
        self._lock = threading.Lock()
        self._last_build_ts: float | None = None

    # ---------------------------- Ingestion ---------------------------------
    def ingest_logs(self, paths: Sequence[str], build: bool = True) -> Dict[str, int]:
        """Load raw log files, identify issue lines (ERROR/WARN), chunk full corpus.
        Returns counts for visibility.
        """
        docs = load_log_files(list(paths))
        issues = extract_issue_docs(docs)
        context = split_context(docs, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        with self._lock:
            self._issue_docs.extend(issues)
            self._context_docs.extend(context)
        if build:
            self._build()
        return {"issues": len(issues), "chunks": len(context), "total_raw": len(docs)}

    def ingest_documents(self, docs: Iterable[Document], as_issue: bool = False, build: bool = True) -> int:
        """Ingest pre-constructed LangChain Documents.
        Set as_issue=True to weight them similarly to log error lines.
        """
        docs_list = list(docs)
        with self._lock:
            if as_issue:
                self._issue_docs.extend(docs_list)
            else:
                self._context_docs.extend(docs_list)
        if build:
            self._build()
        return len(docs_list)

    def ingest_texts(
        self,
        texts: Sequence[str],
        meta_list: Optional[Sequence[Dict[str, Any]]] = None,
        as_issue: bool = False,
        build: bool = True,
    ) -> int:
        """Convenience for raw strings.
        meta_list (same length) optional: each dict merged as metadata.
        """
        docs: List[Document] = []
        for i, t in enumerate(texts):
            md = (meta_list[i] if meta_list and i < len(meta_list) else {}) | {"source": md_safe(meta_list, i, "source") or f"mem:{i}"}
            docs.append(Document(page_content=t, metadata=md))
        return self.ingest_documents(docs, as_issue=as_issue, build=build)

    # ---------------------------- Build / Reset -----------------------------
    def _build(self):
        """(Re)build underlying vector + BM25 stores and QA chain."""
        with self._lock:
            self._vs.build(self._issue_docs, self._context_docs)
            vect, bm25 = self._vs.as_retrievers(k=self.top_k)
            self._retriever = build_ensemble(vect, bm25, weights=self.weights)
            if self._retriever:
                self._qa_chain = build_chain(self._retriever, model_name=self.model_name)
                import time
                self._last_build_ts = time.time()

    def reset(self, clear_docs: bool = True):
        with self._lock:
            if clear_docs:
                self._issue_docs.clear()
                self._context_docs.clear()
            # Re-init underlying vectorstores (will attempt auto-load again)
            self._vs = VectorStores(embedding_backend=self.embedding_backend)
            self._retriever = None
            self._qa_chain = None
            self._last_build_ts = None

    # ---------------------------- Query -------------------------------------
    def query(self, question: str) -> Dict[str, Any]:
        if not self._qa_chain:
            raise RuntimeError("QA chain not ready. Ingest & build first.")
        return run_qa(self._qa_chain, question)

    def retrieve(self, query: str, k: Optional[int] = None) -> List[Document]:
        if not self._retriever:
            return []
        return fetch_sources(self._retriever, query, k or self.top_k)

    # ---------------------------- Status ------------------------------------
    def status(self) -> Dict[str, Any]:
        return {
            "issues_docs": len(self._issue_docs),
            "context_docs": len(self._context_docs),
            "vector_initialized": self._vs.faiss_store is not None,
            "bm25_enabled": self._vs.bm25_retriever is not None,
            "retriever_ready": self._retriever is not None,
            "qa_ready": self._qa_chain is not None,
            "embedding_backend": self.embedding_backend,
            "last_build_ts": self._last_build_ts,
        }


def md_safe(lst: Optional[Sequence[Dict[str, Any]]], idx: int, key: str):  # tiny helper
    try:
        if lst and idx < len(lst):
            return lst[idx].get(key)
    except Exception:
        return None
    return None
