"""Generates the three article diagrams as SVG (Arial/Helvetica only, flat cards, one blue accent, dotted connectors).
Run: python3 build_diagrams.py && for f in diagram-*.svg; do resvg -z 2 $f ${f%.svg}.png; done"""
BLUE, BLUE_L, GREY, BORDER, TEXT, MUTED = "#2F6FED", "#E8F0FE", "#F4F5F7", "#D5D9E0", "#1F2933", "#6B7280"
FONT = "Arial, Helvetica, sans-serif"


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="{FONT}">'
            f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{BLUE}"/></marker>'
            f'<marker id="g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>'
            f'<rect width="{w}" height="{h}" fill="#FFFFFF"/>{body}</svg>')


def rect(x, y, w, h, fill=GREY, stroke=BORDER, rx=14, sw=2):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def text(x, y, s, size=22, weight="normal", fill=TEXT, anchor="start"):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{s}</text>'


def badge(x, y, live):
    if live:
        return rect(x, y, 84, 34, BLUE, BLUE, 17, 0) + text(x + 42, y + 24, "Live", 20, "bold", "#FFFFFF", "middle")
    return rect(x, y, 100, 34, "#FFFFFF", MUTED, 17, 2) + text(x + 50, y + 24, "Design", 20, "bold", MUTED, "middle")


def dotted(d, marker=None, color=BLUE):
    m = f' marker-end="url(#{marker})"' if marker else ""
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" stroke-dasharray="3 9" stroke-linecap="round"{m}/>'


def solid(d, marker="a", color=BLUE):
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" marker-end="url(#{marker})"/>'


PATHS = [("Factory key", "API key", True), ("Federated token", "Tenant identity", True),
         ("Delegated agent", "Agent for a user", True), ("Trial credential", "Email, hard cap", False)]

# ---------- Diagram 1: the system ----------
b = ""
b += text(40, 66, "Consumers", 24, "bold", MUTED) + text(450, 66, "Gateway", 24, "bold", MUTED) + text(850, 66, "Models by job", 24, "bold", MUTED)
for i, (t, sub, live) in enumerate(PATHS):
    y = 100 + i * 124
    b += rect(40, y, 320, 104) + text(62, y + 42, t, 26, "bold") + text(62, y + 80, sub, 20, "normal", MUTED)
    b += badge(360 - 22 - (84 if live else 100), y + 54, live)
    b += dotted(f"M360,{y + 52} L450,{y + 52}", "a")
b += rect(450, 100, 300, 476, "#FFFFFF", BLUE, 18, 3)
for i, label in enumerate(["Identity", "Cache salt", "Budgets", "Rate limits", "Allowlist", "Audit stamp"]):
    y = 124 + i * 74
    b += rect(470, y, 260, 62, BLUE_L, BLUE, 12, 1.5) + f'<circle cx="498" cy="{y + 31}" r="8" fill="{BLUE}"/>' + text(522, y + 40, label, 24, "bold")
catalog = [("Document Q&amp;A", "Qwen2.5-Coder-7B", True), ("Tool calling", "gpt-oss-20b", False), ("Text2SQL", "Qwen2.5-Coder-7B", True)]
for i, (job, model, served) in enumerate(catalog):
    y = 100 + i * 162
    b += rect(850, y, 310, 140) + text(872, y + 38, job, 22, "bold", MUTED)
    b += rect(872, y + 54, 266, 70, BLUE_L if served else "#FFFFFF", BLUE if served else BORDER, 12, 2)
    b += text(890, y + 83, model, 23, "bold", BLUE if served else TEXT) + text(890, y + 110, "Served in POC" if served else "Designed", 19, "normal", BLUE if served else MUTED)
    b += dotted(f"M750,{y + 70} L850,{y + 70}", "a")
b += dotted("M600,576 L600,626", "a")
b += rect(40, 626, 1120, 96, BLUE_L, BLUE, 18, 3) + text(64, 684, "Audit every call", 28, "bold", BLUE)
for i, f in enumerate(["tenant", "mode", "subject", "actor", "model", "cost"]):
    x = 390 + i * 128
    b += rect(x, 654, 116, 40, "#FFFFFF", BLUE, 20, 1.5) + text(x + 58, 682, f, 21, "normal", TEXT, "middle")
open("diagram-1-system.svg", "w").write(svg(1200, 750, b))

# ---------- Diagram 2: the resolved principal ----------
b = text(40, 64, "Paths", 24, "bold", MUTED) + text(880, 64, "Controls", 24, "bold", MUTED)
ty = [226, 326, 426, 526]
for i, (t, sub, live) in enumerate(PATHS):
    y = 110 + i * 140
    b += rect(40, y, 330, 104) + text(62, y + 42, t, 26, "bold") + text(62, y + 80, sub, 20, "normal", MUTED)
    b += badge(370 - 22 - (84 if live else 100), y + 54, live)
    b += dotted(f"M370,{y + 52} C425,{y + 52} 425,{ty[i]} 480,{ty[i]}", "a")
b += rect(480, 90, 300, 580, "#FFFFFF", BLUE, 18, 3)
b += f'<path d="M480,154 L480,108 Q480,90 498,90 L762,90 Q780,90 780,108 L780,154 z" fill="{BLUE}"/>' + text(630, 134, "Principal", 30, "bold", "#FFFFFF", "middle")
for i, f in enumerate(["tenant_id", "identity_mode", "subject", "key_id", "actor", "models", "budget_account"]):
    y = 154 + i * 74
    if i:
        b += f'<line x1="500" y1="{y}" x2="760" y2="{y}" stroke="{BORDER}" stroke-width="2"/>'
    b += text(508, y + 46, f, 25, "bold")
for i, c in enumerate(["Budget check", "Model allowlist", "Cache salt", "Rate limit", "Audit row"]):
    y = 110 + i * 120
    b += rect(880, y, 280, 72, BLUE_L, BLUE, 14, 2) + text(1020, y + 46, c, 25, "bold", TEXT, "middle")
    b += dotted(f"M780,{y + 36} L880,{y + 36}", "a")
open("diagram-2-resolved-principal.svg", "w").write(svg(1200, 710, b))

# ---------- Diagram 3: one delegated call ----------
b = ""
lanes = [("User", 150), ("Agent", 375), ("IdP", 600), ("Gateway", 825), ("Endpoint", 1050)]
for name, cx in lanes:
    b += rect(cx - 95, 24, 190, 56, GREY) + text(cx, 61, name, 26, "bold", TEXT, "middle")
    b += f'<line x1="{cx}" y1="80" x2="{cx}" y2="670" stroke="{BORDER}" stroke-width="3" stroke-dasharray="3 9" stroke-linecap="round"/>'
b += solid("M150,160 L600,160") + text(375, 144, "1 Sign in", 26, "bold", BLUE, "middle")
b += solid("M600,214 L150,214", "g", MUTED) + text(375, 246, "token", 21, "normal", MUTED, "middle")
b += solid("M375,330 L825,330") + text(600, 314, "2 Exchange", 26, "bold", BLUE, "middle")
b += rect(715, 420, 220, 74, BLUE_L, BLUE, 14, 2) + text(825, 464, "3 Resolve + stamp", 23, "bold", TEXT, "middle")
b += solid("M825,580 L1050,580") + text(937, 564, "4 Serve", 26, "bold", BLUE, "middle")
b += solid("M1050,628 L825,628", "g", MUTED) + text(937, 660, "tokens", 21, "normal", MUTED, "middle")
b += dotted("M825,670 L825,716", "a")
b += rect(40, 716, 1120, 214, "#FFFFFF", BLUE, 18, 3) + text(64, 764, "5 Audit row", 28, "bold", BLUE)
b += rect(968, 734, 168, 40, BLUE, BLUE, 20, 0) + text(1052, 762, "Run evidence", 21, "bold", "#FFFFFF", "middle")
rows = [("tenant", "tenant-b"), ("mode", "delegated_agent"), ("status", "200"), ("subject", "397175765415756585"), ("actor", "397177372589197218"), ("model", "Qwen2.5-Coder-7B")]
for i, (k, v) in enumerate(rows):
    col, row = divmod(i, 3)
    x, y = 64 + col * 540, 820 + row * 44
    b += text(x, y, k, 22, "normal", MUTED) + text(x + 120, y, v, 22, "bold", TEXT)
open("diagram-3-delegated-call.svg", "w").write(svg(1200, 960, b))
print("ok")
