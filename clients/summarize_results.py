"""Summarise per-question QASPER result files: counts by kind, mean token F1 on the text-answer set, yes/no accuracy,
unanswerable handling, tokens and cost. Usage: python clients/summarize_results.py results/qasper/a_full.jsonl ..."""
import json
import statistics
import sys

for path in sys.argv[1:]:
    rows = [json.loads(l) for l in open(path)]
    ok = [r for r in rows if r["http_status"] == 200]
    text = [r["score"]["f1"] for r in ok if r["score"]["kind"] == "text"]
    yn = [r["score"]["correct"] for r in ok if r["score"]["kind"] == "yes_no"]
    un = [r["score"]["model_said_unanswerable"] for r in ok if r["score"]["kind"] == "unanswerable"]
    pt, ct = sum(r["prompt_tokens"] for r in ok), sum(r["cached_tokens"] for r in ok)
    print(f"{path}: {len(ok)}/{len(rows)} answered | text-answer set n={len(text)} mean token F1={statistics.mean(text):.3f} | "
          f"yes/no n={len(yn)} correct={sum(yn)} | unanswerable-gold n={len(un)} model-said-unanswerable={sum(un)} | "
          f"prompt tokens={pt} cached={ct} ({ct / pt:.1%}) | cost={sum(r['cost'] for r in ok):.6f} USD")
