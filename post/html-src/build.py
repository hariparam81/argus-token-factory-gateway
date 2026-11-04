"""Builds docs/index.html from index.src.html: inlines the three diagram SVGs (unique ids, accessible labels)
and adds data-label attributes to table cells so tables reflow to stacked cards on phones.
Run from the repo root: python3 post/html-src/build.py"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "post/html-src/index.src.html"
OUT = ROOT / "docs/index.html"
ASSETS = ROOT / "post/html-src/assets"

LABELS = {
    "DIAGRAM1": ("diagram-1-system.svg", "d1", "Diagram 1: the system. Consumers and four identity paths on the left, the gateway in the centre, the model catalog on the right, and the audit bar underneath."),
    "DIAGRAM2": ("diagram-2-resolved-principal.svg", "d2", "Diagram 2: the resolved principal. Four paths converge into one principal record, with the downstream controls as chips."),
    "DIAGRAM3": ("diagram-3-delegated-call.svg", "d3", "Diagram 3: one delegated call across five lanes, with the audit row from the run."),
    "DIAGRAM4": ("diagram-4-test-bed.svg", "d4", "Diagram 4: the proof of concept as built. Client interface, ZITADEL Cloud, the gateway droplet and the model pod."),
    "DIAGRAM5": ("diagram-5-cache-contrast.svg", "d5", "Diagram 5: cached tokens on Tenant B's first call, with salting on and off."),
}
# diagrams 2 and 3 were drawn in the first palette; map them to the current theme
RECOLOUR = {"#2F6FED": "#1E8E4E", "#E8F0FE": "#EAF4EC", "#D5D9E0": "#8FA39A", "#F4F5F7": "#F6F8F7", "#6B7280": "#5B6B63", "#5B6470": "#5B6B63"}


def inline_svg(name, prefix, label):
    s = (ASSETS / name).read_text()
    s = re.sub(r"#[0-9A-Fa-f]{6}", lambda m: RECOLOUR.get(m.group(0).upper(), m.group(0)), s)
    for i in ("a", "g", "ak", "ag"):
        s = s.replace(f'id="{i}"', f'id="{prefix}{i}"').replace(f"url(#{i})", f"url(#{prefix}{i})")
    s = re.sub(r'\swidth="\d+"\sheight="\d+"', "", s, count=1)
    s = re.sub(r'\srole="img"\saria-label="[^"]*"', "", s, count=1)
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
