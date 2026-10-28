# STAGE 3 — STANDALONE HTML + LAUNCH — argus-token-factory-gateway

Build the detailed standalone HTML companion to the article, finish the repo's front door, and run the launch sequence. Run this only after the operator approves Stage 2's article draft. Stop for operator review at the end.

## Inputs

- `post/post.md` (approved draft) and `post/assets/` (the three diagrams, SVG sources).
- `RUN-REPORT.md` and Stage 1's Phase 5 raw exports (full POC results; the infrastructure is destroyed, so these files are the only evidence that exists).
- `sources/framework-report.md`, `sources/evidence-bank.md`, `sources/evidence-refresh-2026.md`, `sources/cost-per-outcome.md`. Note: the `sources/` folder is not part of the Pages site (only `docs/` is served there), but it is an ordinary part of the repo and becomes public when the repo flips at launch.

## Deliverables

- `docs/index.html`: ONE self-contained HTML file. All CSS inline, diagrams inline as SVG, no external fonts, scripts, or images; it must render fully offline. It lives in `docs/` because GitHub Pages serves from that folder; on GitHub itself the file would display as source, so the README links the Pages URL, never the file path. Before launch, confirm `docs/` contains nothing but this file and a `.nojekyll` marker (required, so GitHub Pages serves the file untouched instead of running it through Jekyll), because Pages publishes the entire folder. This page is the detailed companion to the article — more detailed than the article, not a copy of it.
- `README.md` rewritten as the project front door (below).
- `STAGE-3-REPORT.md`: what was built, verification results, launch status, and any deltas from the article.

## HTML content (fixed sections)

1. **Overview.** What the project is, the five tenets, Diagram 1. The POC is presented as a completed run with its dates, never as a live service.
2. **The framework in full.** All four identity paths with their flows, validation rules, budget and audit attachment, and pitfalls (from the framework report); the resolved principal with Diagram 2; the gateway choice stated as licensing facts with their doc sources, in neutral terms: LiteLLM's JWT/OIDC authentication sits in its Enterprise tier per LiteLLM's documentation, its OSS tier covers virtual keys, budgets, and the spend ledger, and the shim exists because of that tier boundary. No provider is graded or compared.
3. **The evidence bank.** Per tenet: the why-it-matters synthesis and its citations as sourced cards with dates and links, caveats attached, refreshed 2026 figures (the refresh document supersedes). Include the "not verified, do not cite" material in a clearly marked appendix so the discipline is visible.
4. **The POC in full.** Architecture as built (including the pod networking path and egress placement, as recorded in the run report), Phase 0 findings, all four demo outputs verbatim from the run report and its raw exports, QASPER setup (papers, questions, license) and F1 results, the complete cost ledger, pitfalls, and the scope statement (layers exercised, sandbox layer reserved and why). Phase timings and total build time do not appear here; they live only in the run report.
5. **The delegated call.** Diagram 3 with the full step table from the run report's audit reconstruction.
6. **Reproduce it.** Condensed setup path (accounts, resources, order of operations) pointing at the repo's `gateway/` configs, `clients/`, and the stage prompts in `prompts/`; expected cost ranges from the run report's ledger.
7. **Limits and open questions.** Everything the sources flagged as unverified or open, carried honestly.

## Design

- Same visual language as the diagrams: white and light-grey surfaces, one blue accent, clean sans type (system font stack only), flat cards, generous whitespace, short labels, tables for data (tables are fine here; the no-tables rule was Medium's).
- Responsive: readable on a phone with no sideways scrolling; wide tables reflow to stacked cards.
- Accessibility basics: semantic headings, alt text on figures via captions, sufficient contrast.

## README (repo front door)

- Project name and one-paragraph statement (the tenets in one line each).
- Links in this order: the article (leave a clearly marked placeholder until the launch step fills it), the standalone HTML via its GitHub Pages URL (filled in the launch step), the run report.
- What is in the repo (map of directories), how the POC was run (condensed, pointing to Stage 1 configs), the dataset credit and license (QASPER, Allen Institute), and the model credit (Qwen2.5-Coder-7B, Apache 2.0).
- A short "status" line: a completed run (with dates), which paths were live, which are design-only. Nothing in the README may imply a live endpoint at `factory.harishparam.com`.

## Verification before launch

- Open `docs/index.html` with networking disabled (or equivalent check) and confirm full rendering.
- Screenshot desktop and phone widths; check for overflow, clipped text, broken anchors.
- Confirm every number in the HTML traces to `RUN-REPORT.md`, its raw exports, or the evidence documents; list any number that does not in `STAGE-3-REPORT.md` rather than shipping it silently.
- Confirm no secrets or internal file paths appear anywhere in the HTML or README, and that `docs/` holds only the Pages file.

## Launch sequence (in this order, after verification)

1. Secrets sweep, two passes. Pass one: a scanner (for example gitleaks) over the repo and its full git history. Pass two: grep the full git history for the literal secret values taken from the sweep reference copy preserved in Stage 1's Phase 5 (the droplet `.env` values, the pod's vLLM API key, the Tailscale auth key) and from the Mac agent's `.env` — the tenant salts and keys are random strings no scanner pattern will recognise; compare values programmatically and never print them. Any hit in either pass stops the launch: the value is rotated and history is dealt with before proceeding, and the incident is recorded in `STAGE-3-REPORT.md`.
2. Flip the repo public (operator confirms this step). Note for the operator: the `sources/` documents become public at this point as ordinary repo files; they are written as research documents and are fit to be read, but the operator confirms that at this step.
3. Enable GitHub Pages (source: `docs/` folder on the default branch); verify the Pages URL renders the page.
4. Operator pastes `post/post.md` into Medium (Medium has no posting API; this step is manual), sets title and subtitle, places the three diagram PNGs at full width, adds tags and the repo link, and publishes.
5. Final commit: README updated with the live article URL and the Pages URL; record both URLs in `STAGE-3-REPORT.md`.
6. Post-launch cleanup: delete the sweep reference copy preserved in Stage 1's Phase 5; revoke the Tailscale auth key (if the overlay path was used); rotate or delete the ZITADEL machine credential and remove its old value from the Mac agent's `.env`. Record completion of each in `STAGE-3-REPORT.md`.

## Constraints

- Same claims discipline as Stage 2: proposal voice, no provider scrutiny, no build-time or phase-timing mentions, past-tense completed-run framing, caveats travel with citations, figures taken from the refresh document.
- Do not change the article (`post/post.md`) in this stage; deltas are reported, not applied.
