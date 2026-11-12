# Resume: OJ-SSCS source + running jobs (2026-11-12)

✍️ Claude-authored. Working buffer of the ONGOING thread "OJ-SSCS added as a source"; delete when it closes.

## Resume here

- Goal (Yi 2026-11-12): add IEEE Open Journal of the SSCS (punumber 8782712) to the paper log and the site; venue rank: JSSC > TCAS-I ≈ SSC-L ≈ OJ-SSCS > TCAS-II.
- State: config `ojsscs` pushed (9a61b2b). PC run got HTTP 418 (IEEE refuses the PC IP), stopped. Rerun through the Mac (Yi: "if u still fail in IEEE, use mac"): SOCKS tunnel `ssh -f -N -D 127.0.0.1:18080 yishenys-macmini`, background task b47abqzui running `scratchpad/ojsscs.sh` (scrape done 13:46: 2021-2026 year files; then affiliations, then restore_abstracts). The script pipes through `| tail`: check progress by files (`output/ojsscs/json/*.json` mtimes, `cache/ojsscs/`), not by its log (pitfall 38).
- Next: when b47abqzui ends: read its output; stop the tunnel (PowerShell: Stop-Process on the ssh with `-D 127.0.0.1:18080`); `update_database.py --no-scrape` (site + iCloud); docs: "12 sources (6 conferences, 6 journals)" in AGENTS §1, README, docs; close the thread; public push needs Yi's word (local: fe9af05, ba57681, b0abf0c, this).
- Also running: Opus agent re-deriving the CTAT question in `surveys/studies/ulp-vref/out/review-study.md` §7 (Yi: "ask a agent to check the CTAT part at ch7 again") → `work/ctat_check.md`, edits §7, review-check 0/0; then re-export units, translator for changed units (resume the earlier Sonnet translator or a new one), review-html, commit + push private.
- Lessons today: probe IEEE with one request before a long job; never report a job "running" without reading its log (global rule updated in CLAUDE-global).
