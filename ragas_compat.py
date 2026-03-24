# Patch for RAGAS/Multiprocessing embedding issues
# Ensures OpenAIEmbeddings and AzureOpenAIEmbeddings are always available and patched globally
import os, sys, types

# Dummy OpenAIEmbeddings
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

# Dummy AzureOpenAIEmbeddings
class AzureOpenAIEmbeddings(OpenAIEmbeddings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

embeddings_patch = types.SimpleNamespace(
    OpenAIEmbeddings=OpenAIEmbeddings,
    AzureOpenAIEmbeddings=AzureOpenAIEmbeddings
)
sys.modules['langchain_openai.embeddings'] = embeddings_patch
sys.modules['langchain.embeddings.openai'] = embeddings_patch
