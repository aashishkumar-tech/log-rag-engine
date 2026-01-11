# Cost Analysis

High‑level monthly cost projection focused on GPT-4o token consumption (all ingestion, indexing, and retrieval run locally at zero marginal cost aside from hardware/electricity).

## 1. Assumptions
- Only paid component: Azure OpenAI GPT-4o (prompt + completion tokens)
- Average question length (user input): 120 tokens
- Retrieved context added per query: 1,200 tokens (after compression)
- System / instruction overhead: 150 tokens
- Model output (answer + citations): 220 tokens average
- 1K token pricing (example placeholder – adjust to your contract):
  - Prompt: $0.0025 / 1K tokens
  - Completion: $0.010 / 1K tokens

Effective tokens per query:
- Prompt side ≈ 120 + 1,200 + 150 = 1,470
- Completion side ≈ 220
- Total ≈ 1,690 tokens ≈ 1.69K tokens

Cost per query ≈ (1.47K * 0.0025) + (0.22K * 0.010) ≈ $0.003675 + $0.0022 ≈ $0.0059
(Round up to $0.006 for buffer)

## 2. Scenarios
| Scenario | Monthly Queries | Approx Tokens (K) | Est. Cost/Query | Monthly Cost |
|----------|-----------------|-------------------|-----------------|--------------|
| Light | 3,000 | 3,000 * 1.69 ≈ 5,070 | $0.006 | ~$18–$20 |
| Moderate | 25,000 | 25,000 * 1.69 ≈ 42,250 | $0.006 | ~$250 |
| Heavy | 300,000 | 300,000 * 1.69 ≈ 507,000 | $0.006 | ~$3,040 |

(Your earlier rough figure ($55 / $5,500) assumed higher per‑query token usage or pricing; adjust after actual logs.)

## 3. Sensitivity (Key Levers)
| Lever | Effect | Example Impact |
|-------|--------|----------------|
| Context length | Largest driver | Cut context 1,200→800 tokens = ~27% savings |
| Re-rank Top-N | Fewer chunks = fewer tokens | Reduce N 12→8 saves ~300 tokens |
| Summarization | Shrinks noisy logs | Improves context density → smaller prompt |
| Caching | Reuse popular answers | 10% cache hit lowers spend same amount |
| Model tier | Cheaper alternative | Swap to GPT-4o-mini (if quality ok) cuts 40–60% |

## 4. Optimization Roadmap
1. Implement per-query token logging (prompt vs completion) → baseline
2. Add retrieval budget (max context tokens) + adaptive truncation
3. Introduce semantic dedupe of overlapping chunks
4. Cache (hash: normalized question + retrieval set signature)
5. Summarize long logs before embedding
6. Periodic review: top 50 queries → handcrafted instructions to shorten answers

## 5. Break-Even Notes
- Local processing (FAISS, BM25) scales near-zero cost after initial embedding.
- Embedding cost (if using local MiniLM) = $0; if switched to API embeddings reevaluate.
- Human escalation cost avoided (if each prevented escalation valued at >$5, ROI achieved at <1K monthly queries).

## 6. Tracking Metrics
| Metric | Purpose |
|--------|---------|
| Tokens / Query (prompt/completion split) | Primary cost dial |
| Context tokens retained vs dropped | Retrieval efficiency |
| Cache hit rate | Marginal cost reduction |
| Re-rank latency vs N | Trade-off tuning |
| Answer reuse rate | Candidate for caching |

## 7. Actionable Next Steps
- Add token accounting wrapper around generation call
- Log (question_hash, prompt_tokens, completion_tokens, context_doc_ids)
- Set soft cap: 1,600 prompt tokens; truncate oldest/lowest-score chunks first
- Trial smaller answer style (structured bullet template)

## 8. Risk / Variance Factors
| Risk | Mitigation |
|------|------------|
| Unexpected long user inputs | Pre-truncate or summarize question >300 tokens |
| Pathological context explosion | Hard cap + similarity-based pruning |
| Price changes from provider | Externalized pricing constants in config |
| Quality regression after shrinking context | A/B token budget before rollout |

## 9. Summary
With disciplined context control and caching, sustainable spend can remain well under earlier rough estimates. Revisit after 2 weeks of real token telemetry to recalibrate.

> Replace placeholder pricing with actual Azure invoice rates before publishing.
