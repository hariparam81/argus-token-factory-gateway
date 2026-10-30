# Changes from the review draft to post-medium.html

`draft-source.html` is the review draft as supplied. `build.py` regenerates `post-medium.html` from it in the dark theme of the first post in the series, with these fixes.

Facts corrected against RUN-REPORT.md:
1. "Each paper carries about three questions" is wrong. The 33 questions split 12, 11 and 10 across the three papers.
2. "Eleven broken or forged credentials ... all eleven were refused" is wrong (post, twice, and the README draft). The identity test had 11 checks: 4 succeeded (user call, delegation mint, delegated call, Tenant A key with an ignored header) and 7 returned 401.
3. The test-bed caption said the pod was reachable only from the gateway container. The run report records a public TCP port gated by vLLM's API key, with egress rules letting only the LiteLLM container reach it from the droplet. Caption now says that.
4. "Sixteen budget refusals from a setup mistake" is 15 from the setup failure plus 1 from the planned D1 stop.
5. The D2 figure caption pointed to "the table above", which the post does not contain. It now points to the companion page.

Structure and wording:
6. References renumbered so numbers follow first appearance. The cost-post reference opens the post, so it is now [1]. The CSA survey and the EU AI Act swap places in the audit section.
7. The vLLM "salt is not an isolation boundary" sentence cited the CVE entry [14], which does not say it. The citation was removed. That statement comes from vLLM's documentation, which is not in the reference list.
8. First-person plural in the proof section ("we", "our") changed to "I" and "my", matching the byline.
9. Review-draft footer replaced with the series footer.

Not changed, for the author to decide:
- `docs/` holds `README.md`, `claude-review-bundle.zip` and `post-for-claude-review.html`. Pages would publish them. Move them out before the flip.
- The README draft repeats the "eleven refused" error and links the Pages URL as if live.
- Repository and companion links are launch-time URLs.
