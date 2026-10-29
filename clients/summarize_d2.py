"""Summarise D2 per-call files in results/d2: first-call cached tokens, pass cached share, latency medians."""
import json
import statistics
from pathlib import Path

d = Path(__file__).parent.parent / "results" / "d2"


def load(name):
    return [json.loads(l) for l in (d / f"{name}.jsonl").read_text().splitlines()]


def line(name):
    r = load(name)
    pt = sum(x["prompt_tokens"] or 0 for x in r)
    ct = sum(x["cached_tokens"] for x in r)
    return (f"| {name} | {r[0]['cached_tokens']}/{r[0]['prompt_tokens']} | {r[0]['seconds']} | {ct}/{pt} ({ct / pt:.1%}) | "
            f"{statistics.median(x['seconds'] for x in r):.3f} |")


print("| pass | first call cached/prompt tokens | first call seconds | pass cached share | median call seconds |")
print("|---|---|---|---|---|")
for n in ["a_pass1", "b_pass1"]:
    print(line(n))
for n in [f"b_repeat{i}" for i in range(1, 6)] + [f"a_repeat{i}" for i in range(1, 6)]:
    print(line(n))
for n in ["c_a_pass1", "c_b_pass1"]:
    print(line(n))
for t in "ba":
    meds = [statistics.median(x["seconds"] for x in load(f"{t}_repeat{i}")) for i in range(1, 6)]
    print(f"\nTenant {t.upper()} repeat passes (steady state): median of the 5 per-pass median call latencies = {statistics.median(meds):.3f} s; per-pass medians {[round(m, 3) for m in meds]}")
