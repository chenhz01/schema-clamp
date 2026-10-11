#!/usr/bin/env python3
"""schema-clamp: clamp LLM JSON output to a JSON Schema subset.

Validates a JSON document against a schema subset (type, required,
properties, items, enum, minimum, maximum, exclusiveMinimum,
exclusiveMaximum, pattern, minLength, maxLength, minItems, maxItems,
additionalProperties), locates each violation with an RFC 6901 JSON
Pointer, and proposes a concrete repair for common failure modes.

Pure standard library. Python >= 3.8.
"""

import argparse
import difflib
import json
import re
import sys

VERSION = "0.1.1"

SUPPORTED_TYPES = ("object", "array", "string", "number", "integer", "boolean", "null")

SUPPORTED_KEYWORDS = (
    "type", "required", "properties", "items", "enum",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "pattern", "minLength", "maxLength", "minItems", "maxItems",
    "additionalProperties", "default", "$schema", "title", "description",
)


class Violation:
    """One schema violation, located by RFC 6901 JSON Pointer."""

    __slots__ = ("pointer", "schema_path", "code", "message", "suggestion")

    def __init__(self, pointer, schema_path, code, message, suggestion=None):
        self.pointer = pointer
        self.schema_path = schema_path
        self.code = code          # type|missing|required|enum|min|max|pattern|len|items|props
        self.message = message
        self.suggestion = suggestion

    def to_dict(self):
        return {
            "pointer": self.pointer,
            "schema_path": self.schema_path,
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
        }

    def __repr__(self):
        s = " -> " + self.suggestion if self.suggestion else ""
        return "[%s] %s: %s%s" % (self.code, self.pointer or "/", self.message, s)


def escape_pointer_token(token):
    """RFC 6901: '~' -> '~0', '/' -> '~1'."""
    return str(token).replace("~", "~0").replace("/", "~1")


def join_pointer(pointer, token):
    return pointer + "/" + escape_pointer_token(token)


def type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):  # bool must be tested before int
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def type_matches(value, expected):
    """JSON-Schema type test. bool is NOT an integer/number in JSON."""
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def _nearest_enum(value, candidates):
    """Suggest the enum candidate closest to the offending value."""
    if isinstance(value, str):
        scored = sorted(
            ((difflib.SequenceMatcher(None, value.lower(), str(c).lower()).ratio(), c)
             for c in candidates),
            key=lambda pair: -pair[0],
        )
        if scored and scored[0][0] > 0.3:
            return scored[0][1]
    return candidates[0] if candidates else None


def _placeholder_for(schema):
    """A sane fill-in value for a missing required field."""
    if isinstance(schema, dict) and "default" in schema:
        return schema["default"], "from schema default"
    t = schema.get("type") if isinstance(schema, dict) else None
    if t == "string":
        return "", "empty string (trimmed by downstream models usually)"
    if t == "integer":
        return 0, "zero"
    if t == "number":
        return 0.0, "zero"
    if t == "boolean":
        return False, "false"
    if t == "array":
        return [], "empty list"
    if t == "object":
        return {}, "empty object"
    if t == "null":
        return None, "null"
    return None, "null (no type hint in schema)"


def _type_fix(value, expected):
    """Return (new_value, description) when a *safe* conversion exists."""
    if expected == "number" and isinstance(value, str):
        try:
            return float(value), "parse string %r to number %s" % (value, float(value))
        except ValueError:
            return None, None
    if expected == "integer" and isinstance(value, str):
        try:
            return int(value), "parse string %r to integer %d" % (value, int(value))
        except ValueError:
            return None, None
    if expected in ("number", "integer") and isinstance(value, bool):
        # bool -> 1/0 is legal Python but a classic JSON bug; suggest, don't convert
        return None, None
    if expected == "string" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value), "stringify number %s" % (value,)
    if expected == "integer" and isinstance(value, float) and value.is_integer():
        return int(value), "narrow float %s to integer %d" % (value, int(value))
    return None, None


def validate(data, schema, _pointer="", _spath="", _out=None):
    """Validate ``data`` against ``schema`` (subset). Returns list[Violation]."""
    if _out is None:
        _out = []
    if schema is True or schema == {}:
        return _out
    if schema is False:
        _out.append(Violation(_pointer, _spath, "type", "schema forbids any value here"))
        return _out
    if not isinstance(schema, dict):
        _out.append(Violation(_pointer, _spath, "schema",
                              "schema must be an object or boolean, got %s" % type_name(schema)))
        return _out

    # ---- type ----
    expected = schema.get("type")
    if expected is not None:
        if expected not in SUPPORTED_TYPES:
            _out.append(Violation(_pointer, _spath, "schema",
                                  "unsupported type %r (supported: %s)"
                                  % (expected, ", ".join(SUPPORTED_TYPES))))
            return _out
        if not type_matches(data, expected):
            fix_val, fix_desc = _type_fix(data, expected)
            suggestion = fix_desc or "re-generate: model returned %s, schema wants %s" % (
                type_name(data), expected)
            _out.append(Violation(_pointer, _spath, "type",
                                  "expected %s, got %s" % (expected, type_name(data)),
                                  suggestion))
            return _out  # deeper checks are meaningless on a wrong type

    # ---- enum ----
    if "enum" in schema:
        candidates = schema["enum"]
        if not isinstance(candidates, list) or not candidates:
            _out.append(Violation(_pointer, _spath, "schema", "enum must be a non-empty array"))
        elif not any(_json_equal(data, c) for c in candidates):
            near = _nearest_enum(data, candidates)
            suggestion = ("use %r (closest enum member)" % (near,)) if near is not None else None
            _out.append(Violation(_pointer, _spath, "enum",
                                  "value %r not in enum %s" % (
                                      _short(data), _short(candidates)), suggestion))

    # ---- numeric bounds ----
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and isinstance(schema["minimum"], (int, float)) \
                and data < schema["minimum"]:
            _out.append(Violation(_pointer, _spath, "min",
                                  "value %s < minimum %s" % (data, schema["minimum"]),
                                  "clamp to minimum %s" % (schema["minimum"],)))
        if "maximum" in schema and isinstance(schema["maximum"], (int, float)) \
                and data > schema["maximum"]:
            _out.append(Violation(_pointer, _spath, "max",
                                  "value %s > maximum %s" % (data, schema["maximum"]),
                                  "clamp to maximum %s" % (schema["maximum"],)))
        if "exclusiveMinimum" in schema and isinstance(schema["exclusiveMinimum"], (int, float)) \
                and data <= schema["exclusiveMinimum"]:
            _out.append(Violation(_pointer, _spath, "min",
                                  "value %s <= exclusiveMinimum %s" % (data, schema["exclusiveMinimum"]),
                                  "use a value > %s" % (schema["exclusiveMinimum"],)))
        if "exclusiveMaximum" in schema and isinstance(schema["exclusiveMaximum"], (int, float)) \
                and data >= schema["exclusiveMaximum"]:
            _out.append(Violation(_pointer, _spath, "max",
                                  "value %s >= exclusiveMaximum %s" % (data, schema["exclusiveMaximum"]),
                                  "use a value < %s" % (schema["exclusiveMaximum"],)))

    # ---- string ----
    if isinstance(data, str):
        if "pattern" in schema:
            pat = schema["pattern"]
            if not isinstance(pat, str):
                _out.append(Violation(_pointer, _spath, "schema", "pattern must be a string"))
            else:
                try:
                    ok = re.search(pat, data) is not None
                except re.error as exc:
                    _out.append(Violation(_pointer, _spath, "schema",
                                          "invalid regex %r: %s" % (pat, exc)))
                else:
                    if not ok:
                        _out.append(Violation(_pointer, _spath, "pattern",
                                              "string %r does not match pattern %r" % (
                                                  _short(data), pat)))
        for key, op in (("minLength", "<"), ("maxLength", ">")):
            if key in schema and isinstance(schema[key], int) and not isinstance(schema[key], bool):
                n = len(data)
                if (op == "<" and n < schema[key]) or (op == ">" and n > schema[key]):
                    _out.append(Violation(_pointer, _spath, "len",
                                          "length %d %s %s %d" % (n, op, key, schema[key])))

    # ---- array ----
    if isinstance(data, list):
        if "minItems" in schema and isinstance(schema["minItems"], int) \
                and not isinstance(schema["minItems"], bool) and len(data) < schema["minItems"]:
            _out.append(Violation(_pointer, _spath, "items",
                                  "array has %d items, minItems %d" % (len(data), schema["minItems"])))
        if "maxItems" in schema and isinstance(schema["maxItems"], int) \
                and not isinstance(schema["maxItems"], bool) and len(data) > schema["maxItems"]:
            _out.append(Violation(_pointer, _spath, "items",
                                  "array has %d items, maxItems %d" % (len(data), schema["maxItems"]),
                                  "truncate to first %d" % schema["maxItems"]))
        items = schema.get("items")
        if isinstance(items, dict):
            for i, element in enumerate(data):
                validate(element, items, join_pointer(_pointer, i),
                         _spath + "/items", _out)
        elif isinstance(items, list):  # positional (draft-07 style)
            for i, element in enumerate(data):
                if i < len(items):
                    validate(element, items[i], join_pointer(_pointer, i),
                             _spath + "/items/%d" % i, _out)

    # ---- object ----
    if isinstance(data, dict):
        required = schema.get("required", [])
        if not isinstance(required, list):
            _out.append(Violation(_pointer, _spath, "schema", "required must be an array"))
            required = []
        props = schema.get("properties", {})
        if not isinstance(props, dict):
            _out.append(Violation(_pointer, _spath, "schema", "properties must be an object"))
            props = {}
        for key in required:
            if key not in data:
                sub = props.get(key, {})
                fill, why = _placeholder_for(sub)
                _out.append(Violation(join_pointer(_pointer, key), _spath, "required",
                                      "missing required property %r" % key,
                                      "fill with %r (%s)" % (fill, why)))
        if schema.get("additionalProperties") is False:
            for key in data:
                if key not in props and key not in required:
                    _out.append(Violation(join_pointer(_pointer, key), _spath,
                                          "props",
                                          "additional property %r not allowed" % key,
                                          "drop the key or extend schema.properties"))
        for key, value in data.items():
            if key in props:
                validate(value, props[key], join_pointer(_pointer, key),
                         _spath + "/properties/" + escape_pointer_token(key), _out)

    return _out


def _json_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b


def _short(value, limit=60):
    text = repr(value)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def apply_safe_fixes(data, schema):
    """Apply only deterministic repairs: required defaults + safe type coercion.

    Returns (new_data, applied:list[str], remaining:list[Violation]).
    Never invents content: unknown required fields get schema defaults or
    neutral empties, and are reported so a human (or a re-prompt) can review.
    """
    applied = []

    def fix_node(node, sch, spath):
        if not isinstance(sch, dict):
            return node
        # type coercion first (only when node itself is wrong-typed scalar)
        expected = sch.get("type")
        if expected in SUPPORTED_TYPES and not type_matches(node, expected):
            fix_val, fix_desc = _type_fix(node, expected)
            if fix_val is not None:
                applied.append("%s: %s" % (spath or "/", fix_desc))
                node = fix_val
        if expected == "object" and isinstance(node, dict):
            required = sch.get("required", []) if isinstance(sch.get("required"), list) else []
            props = sch.get("properties", {}) if isinstance(sch.get("properties"), dict) else {}
            for key in required:
                if key not in node:
                    fill, _why = _placeholder_for(props.get(key, {}))
                    node[key] = fill
                    applied.append("%s/properties/%s: filled missing required with %r"
                                   % (spath, escape_pointer_token(key), fill))
            for key in list(node.keys()):
                if key in props:
                    node[key] = fix_node(node[key], props[key],
                                         spath + "/properties/" + escape_pointer_token(key))
        if expected == "array" and isinstance(node, list) and isinstance(sch.get("items"), dict):
            node = [fix_node(el, sch["items"], spath + "/items/%d" % i)
                    for i, el in enumerate(node)]
        return node

    fixed = fix_node(json.loads(json.dumps(data)), schema, "")
    remaining = validate(fixed, schema)
    return fixed, applied, remaining


def _load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        raise SystemExit("clamp: cannot read %s file %r: %s" % (what, path, exc))
    except json.JSONDecodeError as exc:
        raise SystemExit("clamp: %s file %r is not valid JSON: %s" % (what, path, exc))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="clamp",
        description="Validate LLM JSON output against a JSON Schema subset, "
                    "locate violations by JSON Pointer, propose repairs.")
    parser.add_argument("--version", action="version", version="schema-clamp " + VERSION)
    sub = parser.add_subparsers(dest="cmd")

    p_val = sub.add_parser("validate", help="validate a JSON file against a schema")
    p_val.add_argument("instance", help="path to the JSON output to check")
    p_val.add_argument("--schema", required=True, help="path to the JSON Schema file")
    p_val.add_argument("--max-errors", type=int, default=50,
                       help="stop after N violations (default 50)")
    p_val.add_argument("--json", action="store_true", help="machine-readable report")

    p_fix = sub.add_parser("fix", help="apply safe repairs (defaults + coercions), re-validate")
    p_fix.add_argument("instance", help="path to the JSON output to repair")
    p_fix.add_argument("--schema", required=True, help="path to the JSON Schema file")
    p_fix.add_argument("-o", "--out", help="write repaired JSON here (default: stdout)")
    p_fix.add_argument("--check", action="store_true",
                       help="dry-run: report fixes, do not write")

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help(sys.stderr)
        return 2

    schema = _load_json(args.schema, "schema")
    data = _load_json(args.instance, "instance")

    if args.cmd == "validate":
        violations = validate(data, schema)[: max(args.max_errors, 0)]
        if args.json:
            print(json.dumps({"file": args.instance, "valid": not violations,
                              "violations": [v.to_dict() for v in violations]},
                             ensure_ascii=False, indent=2))
        else:
            if not violations:
                print("OK: %s conforms to schema" % args.instance)
            for v in violations:
                print(repr(v))
        return 0 if not violations else 1

    if args.cmd == "fix":
        fixed, applied, remaining = apply_safe_fixes(data, schema)
        for line in applied:
            print("FIXED " + line, file=sys.stderr)
        for v in remaining:
            print("STILL " + repr(v), file=sys.stderr)
        if not args.check:
            text = json.dumps(fixed, ensure_ascii=False, indent=2) + "\n"
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(text)
                print("wrote %s" % args.out, file=sys.stderr)
            else:
                sys.stdout.write(text)
        return 0 if not remaining else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
