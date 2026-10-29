# Stage 3 report: companion page, README, launch preparation

Status: the page and README are built and committed on `main` in the private repository. The repository is still private. Launch steps 2 to 6 wait for the operator.

## What was built

- `docs/index.html`: one self-contained file (about 136 KB). All CSS is inline, the three diagrams are inline SVG, and there are no external fonts, scripts, images, links to stylesheets or imports. `docs/` holds only this file and `.nojekyll` (the placeholder `.gitkeep` was removed).
- `post/html-src/index.src.html` and `post/html-src/build.py`: the source and build script for the page. `python3 post/html-src/build.py` rebuilds `docs/index.html` (it inlines the SVGs with unique ids and adds `data-label` attributes so tables reflow to stacked cards on phones).
- `README.md`: front door with the five commitments, links in the required order (article and Pages URL are marked placeholders, `ARTICLE_URL` and `PAGES_URL`), repo map, condensed run description, status, dataset and model credits.
- Sections of the page, in the prompt's order: overview with Diagram 1; the framework in full (four paths, principal with Diagram 2, gateway choice as licensing facts, isolation, audit record, architecture, checklist); the evidence bank per tenet as sourced cards with caveats; the POC in full; the delegated call with Diagram 3 and a step table; reproduce it; limits and open questions; an appendix of claims checked and not cited.

## Verification

- **Offline rendering.** Loaded from `file://` in headless Chrome with no network needed. A grep for `<script`, `<link`, `@import`, `src=`, `url(http` and `<img` finds none.
- **Layout.** Desktop screenshot at 1280 px and a 375 px render: document width equals viewport width, with no element past the right edge outside `pre` and `details` blocks (the wide verbatim psql outputs sit in collapsed `details`, and scroll inside their own box). Tables stack as labelled cards at 720 px and below. All in-page anchors resolve. The diagrams scale down on a phone and their meaning is repeated in the captions.
- **Number trace.** All 405 distinct numbers in the page text were compared programmatically against `RUN-REPORT.md`, the raw results, the exports, `post/post.md` and the four source documents. Two did not match literally, and both are derived: `2.32` is `2.319` rounded for the ledger summary sentence, and `0.0000069426` is `6.9426e-06` from `exports/audit_joined.csv` written in decimal. No other number is untraced.
- **No secrets or internal paths.** A grep of the page and README for local paths, the secrets directory, the public hostname, the droplet and pod addresses and server paths found nothing.
- **Style discipline.** No em dashes, no phase or build timings, no live-endpoint wording, no provider grading, quotes replaced by paraphrase. Pitfall 3 (slow starts) is stated without durations.

## Choices and deltas from the article

`post/post.md` was not changed. Differences between the page and the article:

- The page adds, beyond the article: all four path flows and pitfalls, the validation checklist, licensing table, reviewer checklist, per-demo detail, the full D2 table, QASPER partial run, ledger, 14 pitfalls, reproduce steps, and the appendix.
- The evidence cards use the 2026 refresh figures, matching the article. The superseded 2025 figures appear only in the appendix, labelled as superseded.
- The three evidence-bank items that name or grade providers (a per-provider spend-cap analysis, a named key-theft incident at a coding-tool vendor, a named provider's cache incident) are omitted, as in the article, and the appendix says so without naming them.
- The page cites the earlier cost-per-outcome post and its workbench repo (`hariparam81/inference-economics-workbench`), which the article also relies on. The earlier post's own dark, web-font design was not reused, because this stage requires system fonts and a white and blue design.
- Not carried onto the page: the DigitalOcean SSH-key open item, the duckdns hostname, the infrastructure addresses and ids, and the phase timing table.

## Launch status

| step | status |
|---|---|
| 1. Secrets sweep, pass one | Done. gitleaks over the full history (10 commits, with this stage's commit): no leaks found. |
| 1. Secrets sweep, pass two | Done. 29 literal values from the local secrets directory (sweep reference, pod, droplet, Tailscale, tenant and ZITADEL files, the private key body) were compared programmatically against the full history and the current tree. No secret value is present. Four values matched and none is a secret: the gateway URL (a dead hostname used in two client scripts), the ZITADEL instance domain, the project id and the device-code application client id. They are public identifiers of a demo setup and appear in the run report, configs and scripts. The Mac agent's refresh token and machine credential were among the values compared and do not appear. |
| 2. Flip repo public | Waiting for operator confirmation. Note: `sources/` becomes public with it, together with `prompts/`, `exports/` and the whole history. |
| 3. Enable GitHub Pages (`docs/` on `main`) | After step 2. |
| 4. Medium paste of `post/post.md` | Operator, manual. |
| 5. Final commit with both URLs | After steps 3 and 4. URLs to be recorded here: article ____, Pages ____. |
| 6. Cleanup | After launch: delete `~/.argus-secrets/SWEEP-REFERENCE.txt`, revoke the Tailscale key, rotate or delete the ZITADEL machine credential and remove it from the agent's local env, revoke the DigitalOcean token. Completion to be recorded here. |

Incidents: none. No secret reached the history.

## Open items for the operator

- Confirm the flip to public (step 2), and read `sources/` once with that in mind.
- Delete the DigitalOcean SSH key `argus-tfg` in the console, remove the DuckDNS record, and later replace the pod 2 ledger line with the RunPod billing API's final figure.
