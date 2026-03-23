# RAG Evaluation

This folder contains evaluation assets for the RAGPipeline project.

## How to Run Evaluation

1. Ensure dependencies are installed:

   ```bash
   pip install -r requirements.txt
   ```

2. Run the evaluation pipeline:

   ```bash
   python eval/ragas_pipeline.py
   ```

3. Results will be saved in `eval/results/`.

- `ground_truth.json`: 25 Q&A pairs for evaluation
- `results/`: Output metrics and scores
