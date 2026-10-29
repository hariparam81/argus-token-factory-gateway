# Stage 2 report: article draft

## Title options (not in `post.md`; the file is pasted into Medium as-is)
1. A Proposal for a Token Factory: Five Commitments and a Small Working Instance
2. Building a Multi-Tenant Inference Service: Isolation, Audit, Federation, Spend Caps and Cost
3. What a Token Factory Owes Its Tenants

## Draft summary
`post/post.md` is a proposal written from the provider's side. It states five commitments (lowest cost, federate with the customer's identity provider, isolate each tenant's data and cache, cap each tenant's spend, audit every call) and argues them in the fixed order: isolation, audit, federation, spend cap, cost. Each section gives the reason from the verified evidence, the framework mechanism, and the proof-of-concept result drawn from `RUN-REPORT.md`. It then describes the framework with Diagrams 1 and 2, walks through one delegated call with Diagram 3 (run evidence), states scope and limits, and closes with what the author would build next. The proof of concept is described in the past tense as a completed run.

Word count: about 3,400 (body text, excluding image markdown). Three diagrams: `post/assets/diagram-*.svg` with 2x PNG exports made with resvg 0.49.0 (Arial/Helvetica only; the PNGs were inspected and the text renders as designed). `post/assets/build_diagrams.py` regenerates them.

## Every figure used, with its source
Evidence figures (from `sources/evidence-refresh-2026.md` unless noted):
- FinOps State of FinOps 2026: 98% manage AI spend; AI cost management the top skill to develop; 1,192 respondents; over $83 billion annual cloud spend; released 19 Feb 2026 (refresh section 1).
- Verizon DBIR 2026: vulnerability exploitation 31%, credential abuse 13%, more than 22,000 confirmed breaches (refresh section 2).
- Menlo Ventures: inference the majority workload for 74% of startups and 49% of enterprises (mid-year update, 31 Jul 2025, 150 technical leaders); $37B enterprise AI spend in 2025 (Dec 2025 annual); no 2026 edition of either as of Oct 2026 (refresh section 3; evidence-bank Tenet 1 for the survey size).
- Microsoft Digital Defense Report 2026: password spray over 99% of observed cloud initial-access efforts (scoped to cloud, qualifier kept), 124,146,529 attacks; password attacks down 26% year on year; share of AiTM phishing and token theft more than doubled in H1 2026; chapter title "Legitimate access becomes the threat"; covering July 2025 to June 2026 (refresh section 4).
- CrowdStrike 2026 Global Threat Report: 82% malware-free; valid-account abuse 35% of cloud incidents (refresh section 5).
- Evidence bank (`sources/evidence-bank.md`): KVGov preprint arXiv 2608.09225 (149.6 ms cold vs 32.8 ms cached, 2,119-token prefix, up to 100% attack success; labelled preprint, single author, defence in simulation); Chu et al. arXiv 2508.08438 (PromptPeek 99%, EarlyBird 89%; labelled preprint); CVE-2025-46570, vLLM before 0.9.0, CVSS 2.6 LOW; AWS SaaS Architecture Fundamentals whitepaper; EU AI Act Articles 12 and 19 and Regulation (EU) 2026/1744 deferral dates (stated as direction of regulation); CSA survey (418 respondents, 82%, 65%, commissioned by Token Security, stated); NIST AI RMF MANAGE 4.1 and 4.3; NIST SP 800-63C-4; OpenID Shared Signals, CAEP and RISC finalized 16 Sep 2025; Mandiant "AI Risk and Resilience in 2026" (over 15,000 calls, about $50,000); McKinsey (93% over budget, about 60% refinement cost, factor-of-30); Harness 2026 State of AI in FinOps (72%, 73%, 13%, 700 respondents, labelled vendor survey); Demirer et al. December 2025 (more than 20 providers, 90% cheaper).
- `sources/framework-report.md`: cache_salt mechanics and the vLLM statement that the salt is not an isolation boundary; RFC 8693 `act` claim; the IETF identity-assertion draft as an upgrade path; LiteLLM's JWT/OIDC authentication listed as an Enterprise feature in its documentation; the identity-path and principal-record design.
- `sources/cost-per-outcome.md` (quoted verbatim): Qwen2.5-Coder-7B 93.3% (14/15) at $0.0165 per 1k queries; Text2SQL 77.5% at $0.0110 per 1k queries; API model 80.6% at roughly 6.5 times the cost per query; Secure Cloud RTX 4090 at $0.89/hr; published 18 Oct 2026.

Proof-of-concept figures (all from `RUN-REPORT.md` and its raw exports): isolation sequence 0 of 4,481 versus 4,480 of 4,481, repeat passes, medians 0.969 s and 1.028 s, the client-supplied salt call (2,976 of 2,991); D4 totals (259 calls, 1,039,846 tokens, $0.206264, 163 / 84 / 10 calls, 2 mints, 17 zero-spend rows, 13 rejected calls and their reasons); the 11 identity checks (4 succeed, 7 refused); D1 ($0.0143 budget, 18 of 33, 54.5%, 422, $0.014329, $0.000029 overshoot); team budget test ($0.0015 cap, $0.0018); agent limit (6 per minute, 429 on call 7, team spend delta $0.00204787); price derivation (121,430 tokens in 96.67 s, 4,522,034 tokens/hr, $0.897/hr, $1.98e-07 per token, about $0.198 per million tokens); run cost about $2.49; QASPER F1 0.456 and 0.457, n=29, 3 of 3 yes/no, 1 unanswerable; 3 papers, 33 questions; CC BY 4.0. One figure comes from the repository rather than the run report: the shim's size of about 240 lines (`wc -l gateway/shim/app.py` gave 236).

## Mismatches against the refresh document
None found: the article uses only refresh figures where the refresh supersedes the original bank (FinOps 98%, DBIR 31% and 13%, Microsoft 2026 lines). The older bank entries for those series (FinOps 63%, Microsoft 97% and 32%, DBIR 22% and 12,195, and "credential abuse is the leading vector") were not used. The bank's own summary and Tenet 2 text still carry those 2025 figures, so Stage 3 should read the refresh document first.

## Omitted by design or for traceability
- Evidence the voice rules exclude: the per-provider spend-cap analysis (Socialvik), the OpenCode key-theft incident and the OpenAI Redis incident name or compare providers, so they are not used.
- No POC number was left out for lack of a trace. Ledger line items are omitted because the article states only the whole-run cost.
- Flagged inherited caveats, kept in the text where a figure is used: preprints labelled; CSA survey commissioned by Token Security; Harness is a vendor survey; the EU deferral dates rest on law-firm analyses (stated as the direction of regulation, never as applicable law); the Mandiant passage was captured through the search index of the verified page (bank flag).

## Confirmations
- No tables in `post.md` (checked: no pipe characters).
- No build-time, phase-timing or restart-duration mentions.
- No present-tense live-endpoint language; no hostname appears.
- No em dashes; no contrast-framing phrases found by scan and by reading; no banned diction found by scan.
- No title options in the file.
- Not claimed: any SSO percentage, any "credential abuse is number one" line, any leaderboard comparison.

Nothing was published and the repository's visibility is unchanged. Launch happens at the end of Stage 3.
