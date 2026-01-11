from typing import List
from langchain_core.documents import Document
from langchain.retrievers import EnsembleRetriever
from utils.logger import get_logger

logger = get_logger("retriever")


def build_ensemble(vector_retriever, bm25_retriever, weights=(0.6,0.4)):
    retrievers = []
    wts = []
    if vector_retriever:
        retrievers.append(vector_retriever)
        wts.append(weights[0])
    if bm25_retriever:
        retrievers.append(bm25_retriever)
        wts.append(weights[1])
    if not retrievers:
        logger.warning("No retrievers available to build ensemble")
        return None
    if len(retrievers) == 1:
        logger.info("Single retriever active (bm25=%s vector=%s)", bool(bm25_retriever), bool(vector_retriever))
        return retrievers[0]
    s = sum(wts)
    wts = [w/s for w in wts]
    logger.info("Ensemble built (n=%d weights=%s)", len(retrievers), wts)
    return EnsembleRetriever(retrievers=retrievers, weights=wts)


def fetch_sources(retriever, query: str, k: int = 8) -> List[Document]:
    if retriever is None:
        logger.debug("fetch_sources called with None retriever")
        return []
    docs = retriever.get_relevant_documents(query)
    logger.debug("fetch_sources query_len=%d returned=%d", len(query), len(docs))
    return docs
