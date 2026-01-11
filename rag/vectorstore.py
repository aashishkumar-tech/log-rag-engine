from typing import List, Optional
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_community.retrievers import BM25Retriever
from .embeddings import get_embeddings
import os
import json
from utils.logger import get_logger
from time import perf_counter
import math
from langchain_core.retrievers import BaseRetriever  # NEW import

logger = get_logger("vectorstore")

INDEX_DIR = os.path.join('data', 'index')
FAISS_DIR = os.path.join(INDEX_DIR, 'faiss')
BM25_STATE = os.path.join(INDEX_DIR, 'bm25_docs.json')  # simple persistence of raw docs for BM25 rebuild

class VectorStores:
    def __init__(self, embedding_backend: str = 'hf'):
        logger.debug("Init VectorStores backend=%s", embedding_backend)
        self.embeddings = get_embeddings(embedding_backend)
        self.faiss_store: Optional[FAISS] = None
        self.bm25_retriever: Optional[BM25Retriever] = None  # retained for future use
        self._issue_docs: List[Document] = []
        self._context_docs: List[Document] = []
        self._embedded_docs: List[Document] = []
        os.makedirs(FAISS_DIR, exist_ok=True)
        os.makedirs(INDEX_DIR, exist_ok=True)
        self.disable_persist = os.getenv('DISABLE_PERSIST', '0') == '1'
        self.skip_issue_embed = os.getenv('SKIP_ISSUE_EMBED', '1') == '1'
        self.incremental_add = os.getenv('INCREMENTAL_ADD', '1') == '1'
        self.disable_bm25 = True  # force BM25 off (FAISS only)
        self.bm25_auto_disabled = True
        self.lazy_embed = False  # lazy path removed
        self.small_corpus_threshold = int(os.getenv('SMALL_CORPUS_THRESHOLD', '400'))
        self.always_faiss = True  # always build FAISS immediately now
        self._last_timing = {}
        self._embedding_cache = {}
        self.embedding_dim: int | None = None  # NEW: track embedding dimensionality
        # Try auto-load (will keep FAISS if existing index present)
        self._try_load()

    # ---------------- Core Build/Add -----------------
    def build(self, issue_docs: List[Document], context_docs: List[Document]):
        logger.info("Build start issues=%d context=%d", len(issue_docs), len(context_docs))
        t_start = perf_counter()
        self._issue_docs = issue_docs
        self._context_docs = context_docs
        embed_docs = context_docs if self.skip_issue_embed else (issue_docs + context_docs)
        # Always build FAISS (lazy removed)
        t_faiss_start = perf_counter()
        if embed_docs:
            # Derive embedding dimension once (probe first doc)
            try:
                probe_vec = self.embeddings.embed_query(embed_docs[0].page_content[:2000])  # slice avoids huge lines
                if isinstance(probe_vec, list):
                    self.embedding_dim = len(probe_vec)
                else:  # fallback if backend returns ndarray
                    try:
                        self.embedding_dim = len(probe_vec)  # type: ignore
                    except Exception:
                        self.embedding_dim = None
            except Exception as e:  # pragma: no cover
                logger.warning("Probe embed failed (dimension unknown): %s", e)
                self.embedding_dim = None
            self.faiss_store = FAISS.from_documents(embed_docs, self.embeddings, distance_strategy=DistanceStrategy.COSINE)
            # --- Patch embedding_function to guarantee 1D vector output ---
            try:
                orig_fn = self.faiss_store.embedding_function
                def _safe_embed(q):  # type: ignore
                    v = orig_fn(q)
                    # Convert numpy arrays to list
                    try:
                        import numpy as _np
                        if hasattr(v, 'shape') and len(getattr(v, 'shape', [])) == 1:
                            return v.tolist() if hasattr(v, 'tolist') else list(v)
                    except Exception:
                        pass
                    if isinstance(v, list) and v and isinstance(v[0], (list, tuple)):
                        # Nested: take first if single nested else flatten first level
                        if len(v) == 1:
                            v = v[0]
                        else:
                            v = v[0]
                    # Final assert: must be 1D list[float]
                    if isinstance(v, list) and v and isinstance(v[0], (int, float)):
                        return v
                    # Fallback: attempt flatten
                    try:
                        from itertools import chain
                        return list(chain.from_iterable(v))  # type: ignore
                    except Exception:
                        return v
                self.faiss_store.embedding_function = _safe_embed  # type: ignore
            except Exception as e:  # pragma: no cover
                logger.warning("Failed to wrap embedding_function safely: %s", e)
            t_faiss_ms = (perf_counter() - t_faiss_start) * 1000
            self._embedded_docs = list(embed_docs)
            t_persist_start = perf_counter()
            if not self.disable_persist:
                self._persist()
            t_persist_ms = (perf_counter() - t_persist_start) * 1000
            total_ms = (perf_counter() - t_start) * 1000
            self._last_timing = {
                'faiss_ms': round(t_faiss_ms, 2),
                'bm25_ms': 0.0,
                'persist_ms': round(t_persist_ms, 2),
                'total_ms': round(total_ms, 2),
                'embedded_docs': len(self._embedded_docs),
                'bm25_auto_disabled': True,
                'small_corpus_fast_path': False,
            }
            logger.info("FAISS build timing=%s dim=%s", self._last_timing, self.embedding_dim)
        else:
            self.faiss_store = None
            self._embedded_docs = []
            self._last_timing = {}

    def add(self, new_issue_docs: List[Document], new_context_docs: List[Document]):
        logger.debug("Add docs issues+=%d context+=%d", len(new_issue_docs), len(new_context_docs))
        t_start = perf_counter()
        self._issue_docs.extend(new_issue_docs)
        self._context_docs.extend(new_context_docs)
        new_embeds_docs = new_context_docs if self.skip_issue_embed else (new_issue_docs + new_context_docs)
        total_docs = (len(self._context_docs) if self.skip_issue_embed else len(self._issue_docs)+len(self._context_docs))
        if self.faiss_store is None:
            logger.info("Building FAISS (add path) total_docs=%d", total_docs)
            return self.build(self._issue_docs, self._context_docs)
        if not new_embeds_docs:
            return
        texts = [d.page_content for d in new_embeds_docs]
        try:
            vectors = self.embeddings.embed_documents(texts)
        except Exception as e:
            logger.warning("Pre-embedding new docs failed; rebuilding FAISS: %s", e)
            return self.build(self._issue_docs, self._context_docs)
        lengths = {len(v) for v in vectors if isinstance(v, list)}
        if len(lengths) != 1:
            logger.warning("Inconsistent embedding lengths %s; rebuilding FAISS to recover", lengths)
            return self.build(self._issue_docs, self._context_docs)
        new_dim = lengths.pop() if lengths else None
        if self.embedding_dim is not None and new_dim is not None and new_dim != self.embedding_dim:
            logger.warning("Embedding dim changed old=%d new=%d; full rebuild", self.embedding_dim, new_dim)
            return self.build(self._issue_docs, self._context_docs)
        if self.embedding_dim is None and new_dim is not None:
            self.embedding_dim = new_dim
        try:
            t_faiss_start = perf_counter()
            used_add_embeddings = False
            if hasattr(self.faiss_store, 'add_embeddings'):
                try:
                    pairs = list(zip(texts, vectors))  # (text, embedding)
                    self.faiss_store.add_embeddings(text_embeddings=pairs, metadatas=[d.metadata for d in new_embeds_docs])  # type: ignore
                    used_add_embeddings = True
                except Exception as e:
                    logger.warning("add_embeddings failed (%s); falling back to add_texts (re-embed)", e)
            if not used_add_embeddings:
                if hasattr(self.faiss_store, 'add_texts'):
                    self.faiss_store.add_texts(texts, metadatas=[d.metadata for d in new_embeds_docs])  # type: ignore
                else:
                    self.faiss_store.add_documents(new_embeds_docs)  # last resort
            # Ensure embedding_function still safe (some versions overwrite after add)
            try:
                orig_fn = self.faiss_store.embedding_function
                def _safe_embed(q):  # type: ignore
                    v = orig_fn(q)
                    try:
                        import numpy as _np
                        if hasattr(v, 'shape') and len(getattr(v, 'shape', [])) == 1:
                            return v.tolist() if hasattr(v, 'tolist') else list(v)
                    except Exception:
                        pass
                    if isinstance(v, list) and v and isinstance(v[0], (list, tuple)):
                        v = v[0]
                    return v
                self.faiss_store.embedding_function = _safe_embed  # type: ignore
            except Exception:
                pass
            t_faiss_ms = (perf_counter() - t_faiss_start) * 1000
            self._embedded_docs.extend(new_embeds_docs)
            t_persist_start = perf_counter()
            if not self.disable_persist:
                self._persist()
            t_persist_ms = (perf_counter() - t_persist_start) * 1000
            total_ms = (perf_counter() - t_start) * 1000
            self._last_timing = {
                'faiss_ms': round(t_faiss_ms, 2),
                'bm25_ms': 0.0,
                'persist_ms': round(t_persist_ms, 2),
                'total_ms': round(total_ms, 2),
                'embedded_docs': len(self._embedded_docs),
                'bm25_auto_disabled': True,
                'small_corpus_fast_path': False,
            }
            logger.info("FAISS add timing=%s dim=%s", self._last_timing, self.embedding_dim)
        except Exception as e:
            logger.warning("Incremental add failed after validation; rebuilding FAISS: %s", e)
            self.build(self._issue_docs, self._context_docs)

    # --------------- Retrieval Helpers ----------------
    def _ensure_faiss(self):
        return self.faiss_store

    def as_retrievers(self, k: int = 8):
        vect = self.faiss_store.as_retriever(search_kwargs={'k': k}) if self.faiss_store else None
        return vect, None

    def _persist(self):
        if self.disable_persist:
            return
        try:
            if self.faiss_store:
                self.faiss_store.save_local(FAISS_DIR)
            serializable = [{
                'page_content': d.page_content,
                'metadata': d.metadata
            } for d in self._embedded_docs]
            with open(BM25_STATE, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, ensure_ascii=False)
            logger.debug("Persisted embedded_docs=%d", len(self._embedded_docs))
        except Exception as e:
            logger.warning("Failed to persist indices: %s", e)

    def _try_load(self):
        try:
            if os.path.isdir(FAISS_DIR) and any(os.scandir(FAISS_DIR)) and os.path.isfile(BM25_STATE):
                self.faiss_store = FAISS.load_local(FAISS_DIR, self.embeddings, distance_strategy=DistanceStrategy.COSINE, allow_dangerous_deserialization=True)
                with open(BM25_STATE, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                docs = [Document(page_content=r['page_content'], metadata=r['metadata']) for r in raw]
                self._embedded_docs = docs
                self._issue_docs = []
                self._context_docs = docs
                # Infer dimension by probing
                try:
                    probe_vec = self.embeddings.embed_query("probe")
                    self.embedding_dim = len(probe_vec) if isinstance(probe_vec, list) else None
                except Exception:
                    self.embedding_dim = None
                logger.info("Loaded indices embedded=%d dim=%s bm25=%s auto_disabled=%s", len(docs), self.embedding_dim, bool(self.bm25_retriever), self.bm25_auto_disabled)
            else:
                logger.debug("No indices to load")
        except Exception as e:
            logger.warning("Failed to load existing indices: %s", e)

    def get_last_timing(self):
        return self._last_timing

# LexicalFirstHybridRetriever left intact for potential future BM25 re-introduction
class LexicalFirstHybridRetriever(BaseRetriever):
    def __init__(self, vs: VectorStores, bm25: BM25Retriever, k: int = 8, embed_top: int | None = None):
        self.vs = vs
        self.bm25 = bm25
        self.k = k
        self.embed_top = embed_top or max(k*2, 10)
    def _get_relevant_documents(self, query: str, *, run_manager=None):
        docs = self.bm25.get_relevant_documents(query)[:self.embed_top]
        if not docs:
            return []
        qv = self.vs.embeddings.embed_query(query)
        q_norm = math.sqrt(sum(a*a for a in qv)) or 1.0
        scored = []
        for d in docs:
            key = id(d)
            if key not in self.vs._embedding_cache:
                self.vs._embedding_cache[key] = self.vs.embeddings.embed_query(d.page_content)
            dv = self.vs._embedding_cache[key]
            d_norm = math.sqrt(sum(a*a for a in dv)) or 1.0
            sim = sum(a*b for a,b in zip(qv, dv)) / (q_norm * d_norm + 1e-9)
            scored.append((sim, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:self.k]]
    async def _aget_relevant_documents(self, query: str, *, run_manager=None):
        return self._get_relevant_documents(query, run_manager=run_manager)
