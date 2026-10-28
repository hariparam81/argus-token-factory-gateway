"""Select the QASPER workload: papers whose full text fits the served context, >= 30 questions total.

Source is the parquet conversion of allenai/qasper, pinned by commit. Output: workload/workload.json
(papers with full text, questions, gold answers) and workload/selection.md (IDs and token counts).
"""
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer

REPO = "allenai/qasper"
PARQUET_COMMIT = "06806e4608976fc2fac0a090ac425d5b2b29caf4"
SPLIT_FILE = "qasper/validation/0000.parquet"
MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
MAX_PAPER_TOKENS = 11000  # paper + question + answer budget must fit --max-model-len with margin
ANSWER_BUDGET = 256
MIN_QUESTIONS = 30
MAX_PAPERS = 10

out_dir = Path(__file__).parent
tok = AutoTokenizer.from_pretrained(MODEL)

path = hf_hub_download(REPO, SPLIT_FILE, repo_type="dataset", revision=PARQUET_COMMIT)
rows = pq.read_table(path).to_pylist()


def paper_text(row):
    parts = [row["title"], "", "Abstract: " + row["abstract"], ""]
    ft = row["full_text"]
    for name, paras in zip(ft["section_name"], ft["paragraphs"]):
        parts.append(name or "")
        parts.extend(paras)
        parts.append("")
    return "\n".join(parts)


def gold_answers(qa_answers):
    """Collapse each annotator's answer into text plus type."""
    golds = []
    for ann in qa_answers["answer"]:
        if ann["unanswerable"]:
            golds.append({"type": "unanswerable", "text": ""})
        elif ann["yes_no"] is not None:
            golds.append({"type": "yes_no", "text": "yes" if ann["yes_no"] else "no"})
        elif ann["extractive_spans"]:
            golds.append({"type": "extractive", "text": " ".join(ann["extractive_spans"])})
        else:
            golds.append({"type": "free_form", "text": ann["free_form_answer"]})
    return golds


candidates = []
for row in rows:
    text = paper_text(row)
    n_tok = len(tok(text)["input_ids"])
    if n_tok > MAX_PAPER_TOKENS:
        continue
    qs = row["qas"]
    questions = [
        {"question_id": qid, "question": q, "gold": gold_answers(ans)}
        for qid, q, ans in zip(qs["question_id"], qs["question"], qs["answers"])
    ]
    candidates.append({"paper_id": row["id"], "title": row["title"], "tokens": n_tok, "text": text, "questions": questions})

# Prefer papers with the most questions, then fewest tokens, until the question floor is met.
candidates.sort(key=lambda c: (-len(c["questions"]), c["tokens"]))
chosen, total = [], 0
for c in candidates:
    if len(chosen) >= MAX_PAPERS:
        break
    chosen.append(c)
    total += len(c["questions"])
    if total >= MIN_QUESTIONS:
        break

if total < MIN_QUESTIONS:
    sys.exit(f"only {total} questions available under the token ceiling")

max_prompt = max(c["tokens"] for c in chosen) + 200 + ANSWER_BUDGET
(out_dir / "workload.json").write_text(json.dumps({
    "dataset": REPO, "parquet_commit": PARQUET_COMMIT, "split_file": SPLIT_FILE, "license": "cc-by-4.0",
    "tokenizer": MODEL, "papers": chosen}, indent=1))

lines = ["# Workload selection", "", f"Source: {REPO}, parquet conversion commit {PARQUET_COMMIT}, file {SPLIT_FILE}.",
         "License (dataset card tag): cc-by-4.0.", f"Questions: {total}. Papers: {len(chosen)}.",
         f"Largest prompt estimate (paper tokens + question margin + answer budget): {max_prompt} tokens.", "",
         "| paper_id | tokens | questions |", "|---|---|---|"]
lines += [f"| {c['paper_id']} | {c['tokens']} | {len(c['questions'])} |" for c in chosen]
(out_dir / "selection.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
