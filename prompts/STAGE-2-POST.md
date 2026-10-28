# STAGE 2 — ARTICLE — argus-token-factory-gateway

Write the article for the token factory POC built in Stage 1, and package it for Medium. Run this only after the operator approves Stage 1's `RUN-REPORT.md`. This stage's approved draft is Stage 3's main input. Stop for operator review at the end; do not start Stage 3, and do not publish anything or change the repo's visibility in this stage — the launch sequence lives at the end of Stage 3.

## Inputs (read all before writing)

- `RUN-REPORT.md` (repo root) and the raw artifacts exported in Stage 1's Phase 5: every POC number in the article must trace to them. Invent nothing. Note that the POC infrastructure was destroyed at teardown; nothing can be re-run to check a figure, so if a number cannot be traced, leave it out and flag it in the stage report.
- `sources/framework-report.md`: the reference framework (four identity paths, gateway design, resolved principal).
- `sources/evidence-bank.md` and `sources/evidence-refresh-2026.md`: the citation bank, already refreshed to 2026 editions. Take every figure from the refresh document at write time. This prompt deliberately states no figures of its own; if anything you remember or infer disagrees with the refresh document, the refresh document wins, and the mismatch is flagged in your stage report. Use only citations the bank marks verified, and honour every caveat the bank carries.
- `sources/cost-per-outcome.md`: the author's earlier measured results (Post 1). This is the sole source for the consumer-side cost figures in the cost tenet, and for the served model's selection rationale. Quote its figures verbatim; do not derive new ones.

## Deliverables

- `post/post.md`: the article, in Medium-compatible markdown. Medium does not render markdown tables: use short lists and the diagrams for structured information, never tables.
- `post/assets/diagram-1-system.svg`, `diagram-2-resolved-principal.svg`, `diagram-3-delegated-call.svg`: the three diagrams (spec below) as clean SVG, plus PNG exports at 2x made with resvg (check it is installed first; if not, `brew install resvg` or the platform equivalent). Restrict SVG text to a widely available sans stack (Arial, Helvetica) and inspect the PNGs; if letters render differently than designed, outline the text before exporting.

## Article shape (fixed)

- Voice: a proposal from the provider's chair. These are the tenets the author holds important; this is one way to build a service that honours them; the POC is a small working instance offered as supporting evidence. Do not scrutinise, grade, or name-and-compare other providers. Do not claim a feature is absent from the market because launch messaging omits it.
- The POC is described as a completed run, in the past tense. Its infrastructure was destroyed at teardown and `factory.harishparam.com` no longer serves a live endpoint; never write as though readers can call it.
- Structure: (1) opening: what a token factory sells and the five tenets as commitments — lowest cost; federate with the customer's IdP; isolate each tenant's data and cache; cap each tenant's spend; audit every call. (2) The tenets argued in this order: isolation, audit, federation, spend cap, cost — each with its why-it-matters framing built on the bank's strongest verified citation(s), then the framework mechanism, then the POC evidence for that tenet drawn from the run report (cache sequence for isolation; audit reconstruction for audit; Tenant B and the agent for federation; the mid-batch budget stop for the cap; the POC cost ledger plus the author's earlier measured cost-per-outcome results for cost). (3) The framework in brief, with Diagram 1 and Diagram 2 placed here. (4) Diagram 3 with the delegated call. (5) Scope and limits, plainly: paths A, B, C live and D designed; no sandbox layer and why; one model served; what production adds. (6) Close: what the author would build next.
- Title: propose 3 options in your stage report only. Do not put them in `post.md`, not even as comments; the file is pasted into Medium as-is at launch, and anything in it would be published. Titles are plain, with no contrast framing and no clickbait.

## Claims discipline

- POC build time and phase timings are never mentioned, in any form. They exist only in the run report's internal record.
- The cache CVE is cited for measurability of the side channel, with its low severity stated if severity is mentioned at all. Preprints are labelled preprints.
- EU AI Act logging is framed as the direction of regulation, never as currently applicable law (applicability was deferred; the bank carries the dates).
- The federation argument is built from identity-attack data and federation standards per the bank; the bank found no verified "SSO is table stakes" percentage, so none may appear.
- QASPER results are reported as measured (papers, questions, F1, setup) without claiming comparability to published leaderboard numbers, which used different prompts and models.

## Diagram spec

- Style (from the operator's references): white and light-grey surfaces, one blue accent, clean sans type, flat cards, dotted connectors, generous whitespace. Labels are 1-3 words or icons; explanation lives in the caption under each figure, never as paragraphs inside it.
- D1 The system: consumers and four identity paths (left), gateway with capability tiles (centre), model catalog grouped by job (right), audit bar underneath; paths marked Live or Design per the run report, and the catalog marks the one model the POC actually served.
- D2 The resolved principal: four paths converging into one principal record (field names only), with the downstream controls as small chips.
- D3 One delegated call: five lanes (user, agent, IdP, gateway, endpoint), five beats (sign in, exchange, resolve and stamp, serve, audit row). If Stage 1 ran the agent live, caption it as run evidence and use the real audit row values from the run report; if not, label it "as designed" and mark the audit row illustrative.

## Style rules (author's, non-negotiable)

Plain language, written like a person. No em dashes. No contrast-framing constructions ("not X, but Y"). No rule-of-three padding, no puffy transitions, no LLM diction ("delve", "leverage" as a verb, "landscape" as filler, "crucial"). Short paragraphs. Numbers carry their units and sources.

## Stage report (end of stage)

- The 3 title options, a one-paragraph summary of the draft, and the word count.
- Every figure used, with the bank section or input file it came from.
- Any mismatch found between remembered or inferred figures and the refresh document, and any POC number that could not be traced and was therefore omitted.
- Confirmation that no tables, no build-time mentions, no present-tense live-endpoint language, and no unverified claims are in the draft.
- Stop here. Launch (secrets sweep, repo flip, Medium posting, final README) happens at the end of Stage 3, after the HTML and README exist, so the article never links to an empty front door.
