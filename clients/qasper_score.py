"""QASPER scoring for the POC.

Rule per question, from the gold annotations: if any annotator gave an extractive or free-form answer, the
question is scored by token F1 (SQuAD-style normalisation), taking the maximum over those annotators. Otherwise,
if any annotator answered yes/no, it is scored as yes/no accuracy and reported separately. Otherwise the gold is
unanswerable and it is reported separately as whether the model also declared the question unanswerable.
F1 is therefore computed on the answerable text-answer set only.
"""
import re
import string
from collections import Counter

SYSTEM_PROMPT = ("Answer the question about the paper below. Be brief: one short phrase or sentence. "
                 "For a yes/no question answer 'yes' or 'no'. If the paper does not contain the answer, reply 'unanswerable'.\n\n")


def normalize(s):
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def token_f1(pred, gold):
    p, g = normalize(pred).split(), normalize(gold).split()
    if not p or not g:
        return float(p == g)
    common = Counter(p) & Counter(g)
    n = sum(common.values())
    if n == 0:
        return 0.0
    prec, rec = n / len(p), n / len(g)
    return 2 * prec * rec / (prec + rec)


def score(pred, golds):
    text_golds = [g["text"] for g in golds if g["type"] in ("extractive", "free_form") and g["text"].strip()]
    if text_golds:
        return {"kind": "text", "f1": max(token_f1(pred, g) for g in text_golds)}
    yn = [g["text"] for g in golds if g["type"] == "yes_no"]
    if yn:
        return {"kind": "yes_no", "correct": normalize(pred).split()[:1] == [yn[0]]}
    return {"kind": "unanswerable", "model_said_unanswerable": "unanswerable" in normalize(pred)}
