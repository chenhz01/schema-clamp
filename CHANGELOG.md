# Changelog — schema-clamp

All notable changes are documented here. Format: Keep a Changelog-ish, versions are content-iteration milestones (no runtime deps to bump).

## v0.1.1 — 2026-10-11 (round-2 self-review revision)

### Fixed
- `required` violations now point at the missing key itself (`/email`) instead of the parent object (`""`) — consumers of the `--json` report get an directly addressable location (self-review finding A02/B15).
- `clamp fix` applied-fix log lines used a `//`-prefixed path for root-level properties (`//properties/email`); now emits a valid pointer (`/properties/email`).

### Changed
- Test suite extended 56 → 71 cases (+27%, coverage dimension of the ≥20% round-2 improvement gate): exclusive bounds boundary values, min/max length boundaries, `maxItems` truncate suggestion, nested `additionalProperties` pointers, numeric-enum suggestions, no-fake-coercion guarantee for non-numeric strings, float→int narrowing in `fix`, `schema_path` recording, emoji-key pointer round-trip, array-of-arrays pointers, CLI error paths (directory input, unknown subcommand, `--max-errors 0`).

### Documented
- README: Why-not-X table gained the `pydantic` row; Limits gained the clamp-complacency and prompt-regression second-order effects.

## v0.1.0 — 2026-10-11 (first working draft)

### Added
- `clamp.py`: JSON Schema subset validator (type/required/properties/items/enum/minimum/maximum/exclusive*/pattern/minLength/maxLength/minItems/maxItems/additionalProperties), RFC 6901 JSON Pointer location (with `~0`/`~1` escaping), suggestion generator (defaults, safe coercions, nearest-enum via difflib), `apply_safe_fixes` deterministic repair pass.
- CLI: `validate` (exit 0/1/2, `--json` machine report, `--max-errors`) and `fix` (`-o`, `--check` dry-run).
- `self_test.py`: 56 cases across functional / exception-path / extreme-edge tiers (empty inputs, 200k-char strings, 300-level nesting, unicode keys, NaN, bool-vs-integer JSON semantics, malformed files).
- README (article-level), MIT LICENSE, this changelog.
