"""Builds post/medium/post-medium.html: the review draft (draft-source.html) in the dark theme of the first post in the series.
Applies the factual and numbering fixes listed in post/medium/CHANGES.md. Run from the repo root."""
import re
from pathlib import Path

D = Path(__file__).resolve().parent
src = (D / "draft-source.html").read_text()
main = src[src.index("<main"):src.index("</main>")]
svgs = re.findall(r"<svg.*?</svg>", main, flags=re.S)
main = re.sub(r"<svg.*?</svg>", lambda m: "@@SVG%d@@" % svgs.index(m.group(0)), main, flags=re.S)

# ---- text fixes (each must match exactly once) ----
FIX = [
 ("Each paper carries about three questions, so the set was three papers and 33 questions.", "The set was three papers and 33 questions, 10 to 12 per paper."),
 ("Eleven broken or forged credentials were sent at the gateway in testing. All eleven were refused.",
  "Eleven checks ran against the public gateway in testing. The seven that carried bad credentials were all refused with a 401, and the four good paths succeeded."),
 ("Eleven bad credentials were sent at the gateway during testing. All eleven were refused.",
  "Seven bad credentials were refused during testing: no token, an unregistered issuer, a tampered token, a forged algorithm, a tenant claimed by header, an expired token and the wrong audience."),
 ("Full per-pass data in the table above.", "The full per-pass data is on the companion page."),
 ("Every call joined from audit to spend, including sixteen budget refusals from a setup mistake of ours. The record kept the failure as faithfully as the successes.",
  "Every call joined from audit to spend, including sixteen budget refusals, fifteen of them from a setup mistake of mine. The record kept the failure as faithfully as the successes."),
 ("The pod was reachable only from the droplet's gateway container, behind vLLM's API key.",
  "The pod sat behind vLLM's API key, and the droplet's egress rules let only the LiteLLM container reach it."),
 ("vLLM's own documentation says the salt is not an isolation boundary [14].", "vLLM's own documentation says the salt is not an isolation boundary."),
 ("A proposal is easy to write. We wanted one working instance, the smallest factory that keeps all five tenets, with a real workload running through it. What follows is that instance, told once, with nothing dressed up.",
  "A proposal is easy to write. I wanted one working instance, the smallest factory that keeps all five tenets, with a real workload running through it. What follows is that instance, told once, with nothing dressed up."),
 ("Tenant A's own budget cap fired on our repeat passes and stopped them. We raised the cap and reran all five passes.",
  "Tenant A's own budget cap fired on my repeat passes and stopped them. I raised the cap and reran all five passes."),
]
for a, b in FIX:
    assert main.count(a) == 1, a[:50]
    main = main.replace(a, b)

# ---- reference renumbering: order of first appearance ----
# cost post 5->1, Menlo 1->2, FinOps 2->4, Demirer 3->3, McKinsey cost 4->5; CSA 20->19, EU 19->20
m = {5: 1, 1: 2, 2: 4, 3: 3, 4: 5, 20: 19, 19: 20}
body, refs = main.split('<ol class="refs">')
refs_html, tail = refs.split("</ol>", 1)
body = re.sub(r"\[(\d+)\]", lambda x: "[%d]" % m.get(int(x.group(1)), int(x.group(1))), body)
items = re.findall(r"<li>.*?</li>", refs_html, flags=re.S)
order = sorted(range(1, 23), key=lambda new: next(o for o, n in {**{i: i for i in range(1, 23)}, **m}.items() if n == new))
new_items = [items[next(o for o in range(1, 23) if m.get(o, o) == new) - 1] for new in range(1, 23)]
main = body + '<ol class="refs">' + "".join("\n" + i for i in new_items) + "\n</ol>" + tail

# ---- svg recolour for the dark surface ----
MAP = {"#FFFFFF": "#0f1410", "#F4F5F7": "#141a14", "#E8F0FE": "#10301e", "#D5D9E0": "#2c3a2c",
       "#1F2933": "#eef5ee", "#6B7280": "#8fa68f", "#5B6470": "#8fa68f", "#2F6FED": "#2dff7a"}
def dark(s):
    s = re.sub(r"#[0-9A-Fa-f]{6}", lambda x: MAP.get(x.group(0).upper(), x.group(0)), s)
    return re.sub(r'\swidth="\d+"\sheight="\d+"', "", s, count=1)
for i, v in enumerate(svgs):
    main = main.replace("@@SVG%d@@" % i, dark(v))

# ---- structure: numbered tenets get kicker numbers, principle becomes a pick box, closing line a callout ----
main = re.sub(r'<h2><span class="n">(\d)</span>(.*?)</h2>', lambda x: '<h2><span class="num">0%s</span>%s</h2>' % (x.group(1), x.group(2)), main)
main = main.replace('<h2>The five tenets</h2>', '<h2><span class="num">SUMMARY</span>The five tenets</h2>')
main = main.replace('<h2>The proof, told once</h2>', '<h2><span class="num">PROOF</span>The proof, told once</h2>')
main = main.replace('<h2>What this does not show</h2>', '<h2><span class="num">CLOSE</span>What this does not show</h2>')
main = main.replace('<h2>References</h2>', '<h2><span class="num">REFERENCES</span>References</h2>')
main = main.replace('<p class="principle">', '<p class="pick">')
main = re.sub(r"<section>\s*(<h2>|<p>The first)", r"<section>\n\1", main)
main = main.replace('<ol>\n<li><strong>Lowest cost', '<ol class="steps">\n<li><strong>Lowest cost')
# bold closing takeaways -> callouts (last <p><strong>..</strong>.. in each numbered tenet section)
def callout(sec):
    ps = list(re.finditer(r"<p>(<strong>[^<]+</strong>[^<]*)</p>", sec))
    if not ps: return sec
    p = ps[-1]
    return sec[:p.start()] + '<p class="callout">' + p.group(1) + "</p>" + sec[p.end():]
secs = re.split(r"(?=<section>)", main)
secs = [callout(s) if re.search(r'<span class="num">0\d', s) else s for s in secs]
main = "".join(secs)
main = main.replace("<section>", "<section>", 1)

CSS = """:root{--bg:#0a0f0a;--surface:#0f1410;--surface2:#141a14;--text:#c8d4c8;--strong:#eef5ee;--muted:#8fa68f;--green:#2dff7a;--green-dim:#1aaa4e;--blue:#4dc8ff;--amber:#ffb84d;--border:#ffffff12;--border2:#ffffff24;color-scheme:dark}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:19px/1.7 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--green);text-decoration:none;overflow-wrap:anywhere}a:hover{text-decoration:underline}
.bar{position:sticky;top:0;z-index:5;background:#0a0f0acc;backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}
.bar .in{max-width:1144px;margin:0 auto;padding:0 24px;height:60px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{display:flex;align-items:center;gap:10px;color:var(--strong);font-weight:700;white-space:nowrap}
.bar nav{display:flex;gap:22px;font-size:14px}.bar nav a{color:var(--text)}
.btn{display:inline-flex;align-items:center;gap:8px;border-radius:10px;padding:10px 16px;font:600 14px/1 Inter,sans-serif;border:1px solid var(--border2);color:var(--strong)}
.btn.primary{background:var(--green);color:#04110a;border-color:var(--green);box-shadow:0 0 24px #2dff7a40}
.btn:hover{text-decoration:none;border-color:var(--green-dim)}
.hero{text-align:center;padding:80px 24px 40px;background:radial-gradient(ellipse 60% 55% at 50% 0%,#2dff7a16,transparent 70%)}
.pill{display:inline-flex;align-items:center;gap:8px;border:1px solid #2dff7a40;background:#2dff7a0d;border-radius:999px;padding:7px 14px;font:500 11.5px/1 "JetBrains Mono",monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--green)}
.pill i{width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green)}
.hero h1{color:var(--strong);font-size:clamp(34px,6vw,60px);line-height:1.07;font-weight:800;letter-spacing:-.035em;margin:24px auto 0;max-width:900px}
.hero h1 .g{color:var(--green)}
.hero .sub{max-width:680px;margin:20px auto 0;font-size:19px}
.hero .cta{display:flex;gap:12px;justify-content:center;margin-top:28px;flex-wrap:wrap}
.meta{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:26px}
.chip{font:500 12px/1 "JetBrains Mono",monospace;border:1px solid var(--border2);border-radius:999px;padding:7px 11px;color:var(--text)}
.layout{max-width:1144px;margin:0 auto;padding:10px 32px 0}
article{min-width:0}article>*{max-width:1080px;margin-left:auto!important;margin-right:auto!important}
article section{max-width:1080px;margin:0 auto}
article h2{color:var(--strong);font-size:34px;line-height:1.2;font-weight:800;letter-spacing:-.02em;margin:88px 0 18px;scroll-margin-top:80px}
article h2 .num{display:block;font:500 12px "JetBrains Mono",monospace;letter-spacing:.16em;color:var(--green);margin-bottom:10px}
article h3{color:var(--strong);font-size:22px;margin:44px 0 10px}
article p{margin:0 0 18px}article strong{color:var(--strong)}
code{font:15px "JetBrains Mono",monospace;background:var(--surface2);padding:1px 6px;border-radius:5px}
p.pick{background:linear-gradient(180deg,#2dff7a10,transparent 90%),var(--surface);border:1px solid #2dff7a55;border-radius:12px;padding:16px 18px}
p.callout{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--amber);border-radius:12px;padding:16px 18px;font-size:17.5px}
div.definition{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--blue);border-radius:12px;padding:16px 18px;margin:24px 0}
div.definition p{margin:0;font-size:17.5px}
figure{margin:36px 0;border:1px solid var(--border);border-radius:14px;overflow:hidden;background:var(--surface)}
figure svg{display:block;width:100%;height:auto}
figcaption{font:500 13px/1.55 "JetBrains Mono",monospace;color:var(--muted);padding:12px 16px;border-top:1px solid var(--border)}
figcaption strong{color:var(--text)}
ol.steps{list-style:none;counter-reset:s;padding:0;display:grid;gap:10px}
ol.steps li{counter-increment:s;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px 14px 58px;position:relative;font-size:17px;margin:0}
ol.steps li::before{content:counter(s,decimal-leading-zero);position:absolute;left:18px;top:14px;font:700 14px "JetBrains Mono",monospace;color:var(--green)}
ol,ul{padding-left:22px}li{margin:8px 0}
ol.refs{font-size:15.5px;color:var(--text)}ol.refs li{margin:9px 0}
footer{max-width:1080px;margin:80px auto 0;padding:28px 24px 44px;border-top:1px solid var(--border);color:var(--muted);font-size:14px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
@media (max-width:900px){.bar nav{display:none}}
@media (max-width:640px){body{font-size:17px}.hero{padding-top:52px}.layout,.bar .in{padding-left:16px;padding-right:16px}article h2{font-size:25px}}"""

HEAD = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>A Framework for Running a Shared Inference Service</title><meta name="description" content="Five tenets decide whether tenants can trust a shared inference service. Here is the set, with the reasoning behind each.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
{CSS}
</style></head><body>
<div class="bar"><div class="in"><a class="brand" href="#top"><svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true"><rect x="1" y="1" width="24" height="24" rx="7" fill="none" stroke="#2dff7a" stroke-width="2"/><path d="M7 13h12M13 7v12" stroke="#2dff7a" stroke-width="2" stroke-linecap="round"/></svg>Token Factory</a>
<nav><a href="#the-five-tenets">Tenets</a><a href="#proof">The proof</a><a href="#references">References</a></nav>
<a class="btn" href="https://github.com/hariparam81/argus-token-factory-gateway">Repo →</a></div></div>
<header class="hero" id="top"><span class="pill"><i></i>Shared inference, five tenets</span>
<h1>A Framework for Running a <span class="g">Shared Inference</span> Service</h1><p class="sub">Five tenets decide whether tenants can trust it. Here is the set, with the reasoning behind each.</p>
<div class="cta"><a class="btn primary" href="#the-five-tenets">See the five tenets</a><a class="btn" href="#proof">See the proof →</a></div>
<div class="meta"><span class="chip">Cost</span><span class="chip">Identity</span><span class="chip">Isolation</span><span class="chip">Spend</span><span class="chip">Audit</span></div></header>
<div class="layout"><article>
"""
def slug(m):
    return m.group(0)
main = main.replace("<main", "<div", 1).replace("</main>", "")
main = re.sub(r'<div class="wrap">', "", main, count=1)
for t, i in [("The five tenets", "the-five-tenets"), ("The proof, told once", "proof"), ("References", "references")]:
    main = re.sub(r"<h2>(<span class=\"num\">[A-Z]+</span>%s)</h2>" % re.escape(t), r'<h2 id="%s">\1</h2>' % i, main)
FOOT = """
</article></div>
<footer><span><b style="color:var(--strong)">Argus Token Factory Gateway</b> · Harish Parameswaran</span><span>Every number traces to a committed results file.</span></footer>
</body></html>
"""
(D / "post-medium.html").write_text(HEAD + main + FOOT)
print("ok", len(HEAD + main + FOOT))
