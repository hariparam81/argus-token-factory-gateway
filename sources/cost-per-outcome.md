# Cost-per-outcome results — the author's earlier measurements (Post 1)

Source: the author's published article, "A Cost-Per-Outcome Framework for Choosing AI Models" (Medium, published 2026-10-18): https://medium.com/@harishparam/a-cost-per-outcome-framework-for-choosing-ai-models-6da36fb478ee

Method in brief: an extensible model-selection workbench. Eight self-hosted open models (plus API models for comparison) measured on three workloads; the measure is accuracy per dollar at the workload level, not token price. Self-hosted runs served on a rented RunPod RTX 4090 (Secure Cloud, $0.89/hr at the time of the runs).

## Headline results (cite exactly)

- **RAG / document Q&A ("Company Brain"):** Qwen2.5-Coder-7B — **93.3% (14/15)** at **$0.0165 per 1k queries**.
- **Support / tool calling:** gpt-oss-20b — **96.7% (29/30)** at **$0.0298 per 1k queries**.
- **Text2SQL (Spider dev, 1,034 questions, execution accuracy):** Qwen2.5-Coder-7B — **77.5%** at **$0.0110 per 1k queries**. The highest raw accuracy on this track was an API model (gpt-6-luna) at 80.6%, at roughly 6.5x the cost per query.

## Why this file exists in the repo

- It is the evidence behind the POC's served model: Qwen2.5-Coder-7B-Instruct was selected because it won two of the three measured workloads at the lowest cost per outcome (Stage 1, run report model justification).
- It is Stage 2's source for the article's cost tenet on the consumer side: the framework for choosing what to serve, measured before the factory was built. Quote the figures above verbatim; do not derive new figures from them.
