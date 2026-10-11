# Alignment Audit (Rules 85-100 / 16 items) — schema-clamp v0.1.1

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Safety/Ethics section | N/A | Not a security-research repo; no dual-use surface. Fails closed (exit 2) on unreadable/corrupt inputs |
| 2 | Privacy/dezero | PASS | No secrets/tokens/real names anywhere; only contact line uses hcac4735@agent.qq.com; grep `(sk-\|ghp_\|api[_-]?key\s*=\s*['"][A-Za-z0-9])` → 0 hits |
| 3 | Copyright boundary | PASS | All comparisons (jsonschema/pydantic/structured outputs) are structural restatements of public knowledge, no >50-char copied text; MIT LICENSE present, "zhengming contributors" |
| 4 | Fact-check annotation | PASS | ~5 s test-suite runtime marked [Measured] with repro `python self_test.py`; per-doc ms figure marked [estimated]; all other claims qualitative |
| 5 | Confidence grading | PASS | Opener claim [High ≥80%]; subset-coverage assumption [Medium]; visible in opener and [Core Assumptions] (≥2 explicit labels) |
| 6 | PLAN B built-in | PASS | "Minimal Fallback (PLAN B)" section: grep/jq-level sanity gate with zero setup |
| 7 | Timeout preset | PASS | Quickstart states "~2 min" total with per-step ≈1 s / ≈5 s markers |
| 8 | Rule-conflict arbitration | PASS | "Design Trade-offs" opens with priority order: correctness of location > determinism of repair > coverage > performance |
| 9 | Version changelog | PASS | CHANGELOG.md v0.1.0 + v0.1.1; v0.1.1 lists self-review-driven fixes and test delta |
| 10 | Exemption instruction | N/A | Session-level rule; static repo content not applicable |
| 11 | External-knowledge cutoff | PASS | No vendor-specific time-sensitive claims; equivalent-absence claim dated "as of 2026-10-11" |
| 12 | Assumption explicitness | PASS | "[Core Assumptions]" section with 5 items |
| 13 | Logic-check trio | PASS | self_test.py tiers: [A] functional (22), [B] exception/CLI paths (18), [C] extreme edges (16: empty/200k-char/300-deep/unicode/NaN/bool-int); plus [R2] round-2 block (15). Final run: `python self_test.py` → `SUMMARY: PASS 71/71` |
| 14 | Socratic question | PASS | FAQ "When NOT to use this tool?" with 4 concrete anti-use-cases (oneOf schemas, prevention-available, non-JSON, provenance) |
| 15 | Pareto improvement | PASS | v0.1.1: test count 56→71 (+27% ≥20% gate) + 2 correctness fixes (required pointer semantics, applied-fix path prefix); documented in CHANGELOG, suite re-run green |
| 16 | Ultimate fallback (≤60-word opener) | PASS | First paragraph = 55 words, contains what/who-needs-it judgment sentence |

Second-order effects (rule 16 bonus): PASS — "Limits & Second-order Effects" lists clamp-complacency, prompt-regression masking, recursion ceiling, metric-gaming effects.

Scan evidence: `grep -rEn "(sk-|ghp_|api[_-]?key\s*=\s*['\"][A-Za-z0-9])" .` → 0 hits; `grep -rn "hcac4735@agent.qq.com" README.md` → 1 hit.
