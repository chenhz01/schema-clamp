#!/usr/bin/env python3
"""schema-clamp self-test: [A] functional, [B] exception paths, [C] extreme edges.

Run:  python self_test.py          (expect: SUMMARY: PASS n/n)
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clamp  # noqa: E402

RESULTS = []


def check(name, cond):
    RESULTS.append((name, bool(cond)))
    return bool(cond)


def codes(violations):
    return [v.code for v in violations]


def pointers(violations):
    return [v.pointer for v in violations]


def _deep(n):
    node = {"c": 1}
    for _ in range(n):
        node = {"c": node}
    return node


def _deep_schema(n):
    sch = {"type": "integer"}
    for _ in range(n):
        sch = {"type": "object", "properties": {"c": sch}}
    return sch


def _tmp(obj):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    return path


def _tmp_raw(text):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _cli(argv):
    proc = subprocess.run([sys.executable, os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "clamp.py")] + argv,
        capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


# --------------------------------------------------------------- [A] functional
SCHEMA_USER = {
    "type": "object",
    "required": ["id", "email"],
    "properties": {
        "id": {"type": "integer", "minimum": 1},
        "email": {"type": "string", "pattern": "^[^@]+@[^@]+$"},
        "role": {"type": "string", "enum": ["admin", "user", "guest"], "default": "user"},
        "score": {"type": "number", "minimum": 0, "maximum": 100},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
}

check("A01 valid doc passes", clamp.validate(
    {"id": 1, "email": "a@b.c", "role": "user", "score": 50.5, "tags": ["x"]},
    SCHEMA_USER) == [])

check("A02 missing required located", pointers(clamp.validate(
    {"id": 1}, SCHEMA_USER)) == ["/email"])

v = clamp.validate({"id": 1}, SCHEMA_USER)
check("A03 missing required has fill suggestion",
      any(x.code == "required" and "fill with" in (x.suggestion or "") for x in v))

check("A04 type violation message", any(
    x.code == "type" and "got string" in x.message
    for x in clamp.validate({"id": "1", "email": "a@b.c"}, SCHEMA_USER)))

check("A05 string-number coercion suggested", any(
    "parse string" in (x.suggestion or "")
    for x in clamp.validate({"id": "1", "email": "a@b.c"}, SCHEMA_USER)))

check("A06 enum violation + nearest member", any(
    x.code == "enum" and "admin" in (x.suggestion or "")
    for x in clamp.validate({"id": 1, "email": "a@b.c", "role": "adim"}, SCHEMA_USER)))

check("A07 minimum violation", codes(clamp.validate(
    {"id": 0, "email": "a@b.c"}, SCHEMA_USER)).count("min") == 1)

check("A08 maximum violation", codes(clamp.validate(
    {"id": 1, "email": "a@b.c", "score": 101}, SCHEMA_USER)).count("max") == 1)

check("A09 pattern violation on email", any(
    x.code == "pattern" and x.pointer == "/email"
    for x in clamp.validate({"id": 1, "email": "nope"}, SCHEMA_USER)))

check("A10 nested array item typed", any(
    x.pointer == "/tags/0" and x.code == "type"
    for x in clamp.validate({"id": 1, "email": "a@b.c", "tags": [3]}, SCHEMA_USER)))

check("A11 minItems violation", any(
    x.code == "items" and "minItems" in x.message
    for x in clamp.validate({"id": 1, "email": "a@b.c", "tags": []}, SCHEMA_USER)))

check("A12 deep nested pointer", any(
    x.pointer == "/a/b/0/c/d/type"
    for x in clamp.validate(
        {"a": {"b": [{"c": {"d": {"type": "wrong"}}}]}},
        {"type": "object", "properties": {"a": {"type": "object", "properties": {
            "b": {"type": "array", "items": {"type": "object", "properties": {
                "c": {"type": "object", "properties": {
                    "d": {"type": "object", "properties": {
                        "type": {"type": "string", "enum": ["x"]}}}}}}}}}}}})))

check("A13 positional items (draft-07)", any(
    x.pointer == "/1" for x in clamp.validate(
        [1, "x"], {"items": [{"type": "integer"}, {"type": "integer"}]})))

SCHEMA_CLOSED = {**SCHEMA_USER, "additionalProperties": False}

check("A14 additionalProperties false flagged", any(
    x.code == "props" and x.pointer == "/extra"
    for x in clamp.validate({"id": 1, "email": "a@b.c", "extra": 1}, SCHEMA_CLOSED)))

check("A15 exclusiveMinimum enforced", any(
    x.code == "min" for x in clamp.validate(
        {"id": 1, "email": "a@b.c", "score": 0},
        {**SCHEMA_USER, "properties": {**SCHEMA_USER["properties"],
                                       "score": {"type": "number", "exclusiveMinimum": 0}}})))

check("A16 maxLength violation", any(
    x.code == "len" for x in clamp.validate(
        {"id": 1, "email": "a" * 50 + "@b.c"},
        {"type": "object", "properties": {
            "id": {"type": "integer"}, "email": {"type": "string", "maxLength": 10}}})))

check("A17 bool is not integer (JSON semantics)", any(
    x.code == "type" for x in clamp.validate(
        {"id": True, "email": "a@b.c"}, SCHEMA_USER)))

_fixed, _applied, _remaining = clamp.apply_safe_fixes({"id": 1}, SCHEMA_USER)
check("A18 apply_safe_fixes fills required email", "email" in _fixed)

_fixed2, _applied2, _remaining2 = clamp.apply_safe_fixes({"id": "1", "email": "a@b.c"}, SCHEMA_USER)
check("A19 string->int coerced, applied logged",
      _fixed2["id"] == 1 and len(_applied2) == 1 and _applied2[0].startswith("/properties/id"))

check("A20 fix leaves genuinely broken doc with remaining violations",
      clamp.apply_safe_fixes({"id": None}, SCHEMA_USER)[2] != [])

_v = clamp.validate({"a~0b": 1}, {"type": "object",
                                 "properties": {"a~0b": {"type": "string"},
                                                "a/b": {"type": "string"}}})
check("A21 tilde token escaped per RFC 6901 (~0)", "/a~00b" in pointers(_v))

_v2 = clamp.validate({"a/b": 1}, {"type": "object",
                                  "properties": {"a/b": {"type": "string"},
                                                 "a~0b": {"type": "string"}}})
check("A22 slash token escaped per RFC 6901 (~1)", "/a~1b" in pointers(_v2))

# ------------------------------------------------------------------ [B] exception
check("B01 schema not an object reported", any(
    x.code == "schema" for x in clamp.validate(1, 42)))

check("B02 schema False forbids", any(
    x.code == "type" for x in clamp.validate(1, False)))

check("B03 unsupported type value stops traversal", any(
    x.code == "schema" and "unsupported type" in x.message
    for x in clamp.validate({}, {"type": "weird"})))

check("B04 bad enum shape reported", any(
    x.code == "schema" for x in clamp.validate("x", {"enum": []})))

check("B05 invalid regex reported not crashed", any(
    x.code == "schema" and "invalid regex" in x.message
    for x in clamp.validate("x", {"pattern": "([unclosed"})))

check("B06 non-list required tolerated", clamp.validate(
    {"a": 1}, {"type": "object", "required": "a", "properties": {"a": {}}}) != [])

check("B07 non-dict properties tolerated", any(
    x.code == "schema" for x in clamp.validate(
        {"a": 1}, {"type": "object", "properties": [1]})))

check("B08 non-dict items tolerated", isinstance(
    clamp.validate([1], {"items": 7}), list))

check("B09 CLI --max-errors 0 yields empty report", json.loads(_cli(
    ["validate", _tmp({"id": 1}), "--schema", _tmp(SCHEMA_USER),
     "--json", "--max-errors", "0"])[1])["violations"] == [])

check("B10 CLI validate exit 1 on violation", _cli(
    ["validate", _tmp({"id": 1}), "--schema", _tmp(SCHEMA_USER)])[0] == 1)

check("B11 CLI validate exit 0 on valid doc", _cli(
    ["validate", _tmp({"id": 1, "email": "a@b.c"}), "--schema",
     _tmp(SCHEMA_USER)])[0] == 0)

_r = _cli(["validate", _tmp({}), "--schema", "nope_missing.json"])
check("B12 CLI bad schema path exits non-zero with message",
      _r[0] != 0 and "cannot read" in _r[1])

check("B13 CLI malformed instance JSON exits non-zero", _cli(
    ["validate", _tmp_raw("{oops"), "--schema", _tmp(SCHEMA_USER)])[0] != 0)

check("B14 CLI malformed schema JSON exits non-zero", _cli(
    ["validate", _tmp({}), "--schema", _tmp_raw("[1,")])[0] != 0)

check("B15 CLI --json report is parseable and valid-flagged", (lambda rep:
      isinstance(rep, dict) and rep["valid"] is False and rep["violations"][0]["pointer"] == "/email"
      )(json.loads(_cli(["validate", _tmp({"id": 1}), "--schema", _tmp(SCHEMA_USER),
                         "--json"])[1])))

check("B16 CLI fix writes repaired output", (lambda out_path:
      _cli(["fix", _tmp({"id": 1}), "--schema", _tmp(SCHEMA_USER), "-o", out_path])[0] in (0, 1)
      and json.load(open(out_path, encoding="utf-8"))["id"] == 1
      )(os.path.join(tempfile.mkdtemp(), "fixed.json")))

check("B17 CLI no subcommand exits 2", _cli([])[0] == 2)

check("B18 CLI unknown subcommand exits 2", _cli(["frobnicate"])[0] == 2)

# ------------------------------------------------------------------ [C] edges
check("C01 empty instance vs required schema", clamp.validate(
    {}, SCHEMA_USER) != [])

check("C02 empty schema accepts anything", clamp.validate(
    {"a": [1, {"b": None}]}, {}) == [])

check("C03 null instance with type null", clamp.validate(None, {"type": "null"}) == [])

check("C04 deep 300 levels no crash", isinstance(
    clamp.validate(_deep(300), _deep_schema(300)), list))

check("C05 very long string handled", isinstance(clamp.validate(
    "x" * 200000, {"type": "string", "maxLength": 10}), list))

check("C06 huge array violation found at index 100", any(
    x.pointer == "/100" for x in clamp.validate(
        [0] * 101, {"type": "array", "items": {"type": "integer", "minimum": 1}})))

check("C07 unicode keys and values", any(
    x.code == "enum" for x in clamp.validate(
        {"名前": "猫"}, {"type": "object",
                        "properties": {"名前": {"type": "string", "enum": ["犬", "鳥"]}}})))

check("C08 emoji string passes unicode pattern", isinstance(clamp.validate(
    "héllo🎉", {"type": "string", "pattern": "^h.llo"}), list))

check("C09 NaN instance handled as number", isinstance(clamp.validate(
    float("nan"), {"type": "number", "minimum": 0}), list))

check("C10 bool enum membership", clamp.validate(
    True, {"enum": [True, False]}) == [])

check("C11 top-level array schema", clamp.validate(
    [1, 2], {"type": "array", "items": {"type": "integer"}}) == [])

check("C12 top-level scalar violation has empty pointer", any(
    x.code == "type" and x.pointer == ""
    for x in clamp.validate(5, {"type": "string"})))

check("C13 multiple violations aggregated", len(clamp.validate(
    {"id": 1, "email": "a@b.c", "score": -5, "tags": [1, 2]},
    SCHEMA_USER)) >= 2)

check("C14 fix cannot repair enum typo without content invention",
      clamp.apply_safe_fixes({"id": 3, "email": "a@b.c", "role": "adim"}, SCHEMA_USER)[2] != [])

check("C15 empty string instance", clamp.validate("", {"type": "string"}) == [])

check("C16 unknown extra schema keywords ignored", clamp.validate(
    5, {"type": "integer", "format": "uuid", "customThing": True}) == [])

# --------------------------------------------------- [R2] round-2 added coverage
check("R01 exclusiveMaximum enforced", any(
    x.code == "max" for x in clamp.validate(
        10, {"type": "number", "exclusiveMaximum": 10})))

check("R02 minimum boundary value passes", clamp.validate(
    5, {"type": "integer", "minimum": 5, "maximum": 5}) == [])

check("R03 maxLength exact boundary passes", clamp.validate(
    "abcde", {"type": "string", "maxLength": 5, "minLength": 5}) == [])

check("R04 minLength violation reported", any(
    x.code == "len" and "minLength" in x.message
    for x in clamp.validate("ab", {"type": "string", "minLength": 3})))

check("R05 maxItems suggests truncate", any(
    "truncate" in (x.suggestion or "") for x in clamp.validate(
        [1, 2, 3], {"type": "array", "maxItems": 2})))

check("R06 positional items longer than schema tolerated", clamp.validate(
    [1, 2, 3], {"items": [{"type": "integer"}]}) == [])

check("R07 nested additionalProperties flagged with nested pointer", any(
    x.pointer == "/meta/ghost" for x in clamp.validate(
        {"meta": {"ghost": 1}},
        {"type": "object", "properties": {"meta": {
            "type": "object", "additionalProperties": False}}})))

check("R08 numeric enum suggests first candidate", any(
    x.code == "enum" and x.suggestion for x in clamp.validate(
        7, {"type": "integer", "enum": [1, 2, 3]})))

check("R09 non-numeric string gets regen suggestion, not fake coercion", any(
    "re-generate" in (x.suggestion or "")
    for x in clamp.validate({"id": "abc", "email": "a@b.c"}, SCHEMA_USER)))

check("R10 integer in string slot flagged at nested pointer", any(
    x.code == "type" and x.pointer == "/0"
    for x in clamp.validate([5], {"type": "array", "items": {"type": "string"}})))

check("R11 fix narrows float 3.0 -> int 3", (lambda result:
      result[0]["id"] == 3 and isinstance(result[0]["id"], int)
      )(clamp.apply_safe_fixes({"id": 3.0, "email": "a@b.c"}, SCHEMA_USER)))

check("R12 schema_path records schema location", any(
    x.schema_path.endswith("/properties/role") for x in clamp.validate(
        {"id": 1, "email": "a@b.c", "role": 9}, SCHEMA_USER)))

check("R13 emoji key round-trips through pointer", any(
    x.pointer == "/🎉key" for x in clamp.validate(
        {"🎉key": 1}, {"type": "object", "properties": {"🎉key": {"type": "string"}}})))

check("R14 array-of-arrays nested pointer", any(
    x.pointer == "/0/1" for x in clamp.validate(
        [[1, "x"]], {"type": "array", "items": {
            "type": "array", "items": {"type": "integer"}}})))

check("R15 CLI validate on directory path exits non-zero", _cli(
    ["validate", tempfile.mkdtemp(), "--schema", _tmp(SCHEMA_USER)])[0] != 0)

if __name__ == "__main__":
    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    for n, ok in RESULTS:
        if not ok:
            print("FAIL:", n)
    print("SUMMARY: PASS %d/%d" % (passed, total))
    sys.exit(0 if passed == total else 1)
