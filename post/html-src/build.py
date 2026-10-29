"""Builds docs/index.html from index.src.html: inlines the three diagram SVGs (unique ids, accessible labels)
and adds data-label attributes to table cells so tables reflow to stacked cards on phones.
Run from the repo root: python3 post/html-src/build.py"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "post/html-src/index.src.html"
OUT = ROOT / "docs/index.html"
ASSETS = ROOT / "post/assets"

LABELS = {
    "DIAGRAM1": ("diagram-1-system.svg", "d1", "Diagram 1: the system. Consumers and four identity paths on the left, the gateway in the centre, the model catalog on the right, and the audit bar underneath."),
    "DIAGRAM2": ("diagram-2-resolved-principal.svg", "d2", "Diagram 2: the resolved principal. Four paths converge into one principal record, with the downstream controls as chips."),
    "DIAGRAM3": ("diagram-3-delegated-call.svg", "d3", "Diagram 3: one delegated call across five lanes, with the audit row from the run."),
}


def inline_svg(name, prefix, label):
    s = (ASSETS / name).read_text()
    s = s.replace('id="a"', f'id="{prefix}a"').replace('id="g"', f'id="{prefix}g"')
    s = s.replace("url(#a)", f"url(#{prefix}a)").replace("url(#g)", f"url(#{prefix}g)")
    s = re.sub(r'\swidth="\d+"\sheight="\d+"', "", s, count=1)
    s = s.replace("<svg ", f'<svg role="img" aria-label="{label}" ', 1)
    return s


def label_tables(html):
    def fix(m):
        table = m.group(0)
        heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)]
        if not heads:
            return table
        out = []
        for row in re.split(r"(?=<tr)", table):
            if "<td" not in row:
                out.append(row)
                continue
            i = [0]

            def cell(c):
                h = heads[i[0]] if i[0] < len(heads) else ""
                i[0] += 1
                tag = c.group(0)
                return tag[:-1] + f' data-label="{h}">' if h else tag
            out.append(re.sub(r"<td[^>]*>", cell, row))
        return "".join(out)
    return re.sub(r'<table class="rt">.*?</table>', fix, html, flags=re.S)


html = SRC.read_text()
for key, (name, prefix, label) in LABELS.items():
    html = html.replace("{{" + key + "}}", inline_svg(name, prefix, label))
html = label_tables(html)
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(html)
(OUT.parent / ".nojekyll").write_text("")
gk = OUT.parent / ".gitkeep"
if gk.exists():
    gk.unlink()
print(OUT, len(html), "bytes")
