# Dummy OpenAIEmbeddings and AzureOpenAIEmbeddings for compatibility with RAGAS or other libraries expecting them
class OpenAIEmbeddings:
    def __init__(self, model_name=None, **kwargs):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(os.getenv("HF_EMBEDDING_MODEL", "all-MiniLM-L6-v2"))

    def embed_query(self, text: str):
        v = self.model.encode(text)
        try:
            return list(map(float, v.tolist()))
        except Exception:
            return list(map(float, v))

    def embed_documents(self, texts):
        arr = self.model.encode(texts)
        try:
            return [list(map(float, a.tolist())) for a in arr]
        except Exception:
            return [list(map(float, a)) for a in arr]

# Dummy AzureOpenAIEmbeddings (inherits from OpenAIEmbeddings)
class AzureOpenAIEmbeddings(OpenAIEmbeddings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

# Register these classes globally for all processes (including subprocesses)
import sys, types
embeddings_patch = types.SimpleNamespace(
    OpenAIEmbeddings=OpenAIEmbeddings,
    AzureOpenAIEmbeddings=AzureOpenAIEmbeddings
)
sys.modules['langchain_openai.embeddings'] = embeddings_patch
sys.modules['langchain.embeddings.openai'] = embeddings_patch
import os
import os
import hashlib
from typing import List

# Minimal embedding factory for VectorStores compatibility.
# Tries to use sentence-transformers if available, otherwise falls back
# to a deterministic hash-based vector (stable across runs) with
# dimension defined by EMBEDDING_DIM environment variable (default 8).

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "8"))


class SimpleEmbeddings:
    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim

    def _hash_to_vector(self, text: str) -> List[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Turn bytes into floats in range [-1,1]
        vec = [((b - 128) / 128.0) for b in h[: self.dim]]
        return vec

    def embed_query(self, text: str) -> List[float]:
        return self._hash_to_vector(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_to_vector(t) for t in texts]

    # Make instances callable to support APIs that expect a function-like embedding
    def __call__(self, text: str):
        return self.embed_query(text)


def get_embeddings(backend: str = "hf"):
    """Return an embeddings-like object with methods `embed_query` and
    `embed_documents`. Prefer sentence-transformers if installed,
    otherwise return a stable simple fallback.
    """
    try:
        # Prefer sentence-transformers for quality embeddings when available
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("HF_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        model = SentenceTransformer(model_name)

        class STWrapper:
            def __init__(self, model, dim=None):
                self.model = model
                self.dim = dim

            def embed_query(self, text: str) -> List[float]:
                v = self.model.encode(text)
                try:
                    return list(map(float, v.tolist()))
                except Exception:
                    return list(map(float, v))

            def embed_documents(self, texts: List[str]) -> List[List[float]]:
                arr = self.model.encode(texts)
                try:
                    return [list(map(float, a.tolist())) for a in arr]
                except Exception:
                    return [list(map(float, a)) for a in arr]

            # Make wrapper callable so it can be used where a plain function is expected
            def __call__(self, text: str):
                return self.embed_query(text)

        return STWrapper(model)
    except Exception:
        return SimpleEmbeddings(EMBEDDING_DIM)
