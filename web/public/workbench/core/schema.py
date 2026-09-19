"""Canonical JSON, content hashing, and project-directory layout.

Hashes are taken over canonical JSON -- sorted keys, no insignificant
whitespace, floats at fixed precision. Without that rule two surfaces produce
two hashes for one decision and the lineage claim stops being checkable. Fixed
precision is also what keeps a hash stable across numpy under WebAssembly and
numpy on a laptop, which will not agree in the last bits.
"""

import hashlib
import json
import os

FLOAT_PRECISION = 6
UNIT = "pKD"

SCHEMA_VERSION = 1


def canonicalize(obj):
    """Recursively coerce to JSON-safe values with floats at fixed precision."""
    if isinstance(obj, dict):
        return {str(k): canonicalize(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [canonicalize(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return round(obj + 0.0, FLOAT_PRECISION)
    if obj is None or isinstance(obj, str):
        return obj
    # numpy scalars and arrays, without importing numpy at module level
    if hasattr(obj, "tolist"):
        return canonicalize(obj.tolist())
    if hasattr(obj, "item"):
        return canonicalize(obj.item())
    raise TypeError("not canonicalizable: %r" % type(obj))


def canonical_json(obj):
    return json.dumps(canonicalize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(obj):
    return "sha256:" + hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def short_hash(h):
    return h.split(":", 1)[-1][:12]


def stamp(record, inputs=None):
    """Attach an input-hash table and a self-hash to a record.

    The self-hash is computed over the record *without* its own ``hash`` field,
    so it is stable and recomputable by any surface.
    """
    body = {k: v for k, v in record.items() if k != "hash"}
    if inputs is not None:
        body["inputs"] = inputs
    body["hash"] = content_hash({k: v for k, v in body.items() if k != "hash"})
    return body


def verify(record):
    body = {k: v for k, v in record.items() if k != "hash"}
    return record.get("hash") == content_hash(body)


# --- project directory -----------------------------------------------------

SUBDIRS = ("evidence", "models", "candidates", "batches", "decisions")


def project_paths(root):
    p = {
        "root": root,
        "project": os.path.join(root, "project.json"),
        "objectives": os.path.join(root, "objectives.json"),
        "designs": os.path.join(root, "designs.json"),
        "rounds": os.path.join(root, "rounds.json"),
    }
    for d in SUBDIRS:
        p[d] = os.path.join(root, d)
    return p


def ensure_project_dirs(root):
    os.makedirs(root, exist_ok=True)
    for d in SUBDIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    return project_paths(root)


def write_json(path, obj):
    text = json.dumps(canonicalize(obj), sort_keys=True, indent=2, ensure_ascii=False)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return path


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def numbered(kind, n):
    return "%s_%03d" % (kind, n)


def assert_unit(unit, where="value"):
    """Fail loudly on a unit mismatch rather than trusting the convention.

    A sign error here points the entire proof chart downward, so the loader
    asserts pKD instead of assuming it.
    """
    if unit != UNIT:
        raise ValueError("%s must be in %s, got %r" % (where, UNIT, unit))
    return True


def kd_molar_to_pkd(kd_molar):
    import math

    if kd_molar <= 0:
        raise ValueError("KD must be positive")
    return -math.log10(kd_molar)
