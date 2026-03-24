
# Ensure embedding patch is loaded in all processes
import ragas_compat
from dotenv import load_dotenv
load_dotenv()

# Monkey-patch OpenAIEmbeddings and AzureOpenAIEmbeddings globally for RAGAS compatibility
import sys, os, types
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from rag.embeddings import OpenAIEmbeddings as LocalOpenAIEmbeddings

# Dummy AzureOpenAIEmbeddings (inherits from OpenAIEmbeddings)
class AzureOpenAIEmbeddings(LocalOpenAIEmbeddings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

embeddings_patch = types.SimpleNamespace(
    OpenAIEmbeddings=LocalOpenAIEmbeddings,
    AzureOpenAIEmbeddings=AzureOpenAIEmbeddings
)
sys.modules['langchain_openai.embeddings'] = embeddings_patch
sys.modules['langchain.embeddings.openai'] = embeddings_patch
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset
import json, os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def load_ground_truth(path="eval/ground_truth.json"):
    with open(path) as f:
        return json.load(f)

def run_evaluation():
    from rag.wrapper import RAGWrapper
    wrapper = RAGWrapper(model_name=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
    # Ingest logs before evaluation to ensure QA chain is ready
    # You can change the log path as needed
    log_path = os.path.join("data", "index", "bm25_docs.json")
    if os.path.exists(log_path):
        import json as _json
        with open(log_path, "r", encoding="utf-8") as f:
            bm25_docs = _json.load(f)
        # Accept 'text', 'page_content', or fallback to ''
        texts = [d.get("text") or d.get("page_content") or "" for d in bm25_docs]
        meta_list = [d.get("meta") or d.get("metadata") or {} for d in bm25_docs]
        wrapper.ingest_texts(texts, meta_list=meta_list, build=True)
    else:
        # Fallback: try to ingest a sample log file if present
        log_txt = os.path.join("data", "dummy_logs.txt")
        if os.path.exists(log_txt):
            with open(log_txt, "r", encoding="utf-8") as f:
                lines = f.readlines()
            wrapper.ingest_texts(lines, build=True)
        else:
            raise RuntimeError("No log data found for ingestion. Please provide logs in data/index/bm25_docs.json or data/dummy_logs.txt.")

    ground_truth = load_ground_truth()

    data = {"question": [], "answer": [], "contexts": [], "ground_truth": []}

    for item in ground_truth:
        result = wrapper.query(item["question"])
        data["question"].append(item["question"])
        data["answer"].append(result.get("answer", ""))
        # Convert sources (list of dicts) to list of strings for RAGAS
        sources = result.get("sources", [])
        contexts = [s["page_content"] if isinstance(s, dict) and "page_content" in s else str(s) for s in sources]
        data["contexts"].append(contexts)
        data["ground_truth"].append(item["ground_truth"])

    dataset = Dataset.from_dict(data)
    scores = evaluate(dataset, metrics=[
        faithfulness, answer_relevancy,
        context_precision, context_recall
    ])

    os.makedirs("eval/results", exist_ok=True)
    results_df = scores.to_pandas()
    results_df.to_json("eval/results/baseline_results.json", indent=2)
    print(scores)
    return scores

if __name__ == "__main__":
    run_evaluation()
