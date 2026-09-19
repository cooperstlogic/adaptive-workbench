#!/usr/bin/env python3
"""bioprovider_server -- the computational-provider stand-in, over MCP stdio.

The shape a hosted provider has: you hand it sequences and a model name, and
it hands back features, scores or structures. The interface is real and every
tool here is one call into ``core/``, so a number this server returns is the
same number the CLI and the browser compute -- CLAUDE.md's non-negotiable 2.

**The backend is a config field, not an argument.** ``project.json`` declares
``sources.bioprovider.backend`` and only ``local`` is built. Asking for the
``esm_live`` backend returns a clear error naming what is missing; it never
silently falls back to one-hot and calls it an embedding. A silent fallback is
failure mode 1 -- a mock dressed as the real thing -- inside the one layer of
this build whose whole job is to be swappable.

**What is real here and what is not**, because this is the file where the
distinction is easiest to blur:

  embed_sequences    real, and it is one-hot. There are no learned embeddings
                     in this build
  score_properties   real. Deterministic arithmetic from core/scoring.py, the
                     same scores the constraint filter enforces
  predict_structures stubbed. It predicts nothing and says so; no structure
                     model runs anywhere in this build

    .venv/bin/python connectors/bioprovider_server.py          # MCP on stdio
    .venv/bin/python connectors/bioprovider_server.py --tools  # the tool list
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from core import encode, project as project_mod, schema, scoring  # noqa: E402

INSTRUCTIONS = """A computational provider for protein design: featurization,
deterministic property scoring, and structure prediction.

The backend is whatever project.json declares. Only the `local` backend is
built in this deployment: embed_sequences returns the one-hot block the models
are actually fit on, score_properties computes developability exactly, and
predict_structures is a stub that predicts nothing and says so.

Nothing here decides anything. These are inputs to a model or evidence a human
reads, and the scores are exact calculations rather than predictions."""

# Declared and unwired. Selecting it is an error rather than a fallback.
BACKENDS = {
    "local": "built. One-hot features, exact developability, structure stubbed",
    "esm_live": "declared and NOT wired in this build. Selecting it is an error",
}

MODELS = {
    "onehot": "local",
    "esm2_t12_35M_UR50D": "esm_live",
}

TOOL_SETS = {
    "developability": ("hydrophobicity", "net_charge", "liability_count",
                       "introduced_liabilities"),
}

TOOLS = [
    ("embed_sequences", "Featurize sequences with the project's declared backend"),
    ("score_properties", "Deterministic developability scores from core/scoring.py"),
    ("predict_structures", "Stubbed. Predicts nothing in this build and says so"),
]

server = MCPServer("adaptive-bioprovider", version="1.0.0", instructions=INSTRUCTIONS)


class BackendError(ToolError):
    """Raised instead of falling back, which is the whole point of the class.

    It subclasses the SDK's ToolError so the *message* reaches the caller. A
    refusal whose reason the agent cannot read is indistinguishable from a
    crash, and this server's refusals are the deliverable.
    """


def _state(project):
    return project_mod.load(project)


def _backend(state):
    return state["project"].get("sources", {}).get("bioprovider", {}).get("backend", "local")


def _require_local(state, what):
    backend = _backend(state)
    if backend == "local":
        return backend
    if backend in BACKENDS:
        raise BackendError(
            "the project declares the %r backend, which is %s. %s is not available. "
            "Change sources.bioprovider.backend in project.json to 'local', or wire the "
            "backend -- this build will not quietly substitute one for the other."
            % (backend, BACKENDS[backend], what))
    raise BackendError("unknown backend %r; this build knows %s"
                       % (backend, ", ".join(sorted(BACKENDS))))


def _resolve(state, candidates):
    """Accept full sequences or design ids, and say which were not found."""
    by_id = project_mod.designs_by_id(state)
    parent = state["designs"]["parent"]
    out, unknown = [], []
    for c in candidates:
        if c in by_id:
            out.append((c, by_id[c]["sequence"]))
        elif len(c) == len(parent) and c.isalpha():
            out.append((encode.sequence_id(c), c))
        else:
            unknown.append(c)
    if unknown:
        raise BackendError("not a design id in this project and not a full-length "
                           "sequence: %s" % ", ".join(unknown[:5]))
    return out


@server.tool()
def embed_sequences(project: str, model: str, sequences: list[str], out: str = "") -> dict:
    """Featurize sequences with the backend the project declares.

    On the `local` backend the one model is `onehot`: 8 editable positions x 20
    amino acids = 160 columns, exactly 8 of them set per row. That is the block
    core/surrogate.py fits on, so this returns the real features and not a
    demonstration of them.

    The matrix is summarized rather than returned: 48 x 160 floats is not
    something to read, and the content hash is the part that carries the claim
    that every surface featurizes identically. Pass `out` to write the full
    block as .npy.

    Args:
        project: path to the project directory
        model: onehot (local). esm2_t12_35M_UR50D needs the unwired esm_live backend
        sequences: full sequences or design ids from this project
        out: optional path to write the (n, 160) float32 matrix as .npy
    """
    state = _state(project)
    needs = MODELS.get(model)
    if needs is None:
        raise BackendError("unknown model %r; this build knows %s"
                           % (model, ", ".join(sorted(MODELS))))
    if needs != "local":
        raise BackendError(
            "model %r runs on the %r backend, which is declared and not wired in this "
            "build. There are no learned embeddings here. The one-hot block is the only "
            "feature set, and substituting it silently would be a lie about what was "
            "computed." % (model, needs))
    _require_local(state, "featurization with a learned model")

    resolved = _resolve(state, sequences)
    seqs = [s for _, s in resolved]
    region = state["objectives"]["editable_region"]
    X = encode.one_hot(seqs, region)
    record = {
        "model": model, "backend": "local", "feature_block": "onehot",
        "shape": list(X.shape), "dtype": str(X.dtype),
        "ones_per_row": int(X[0].sum()) if len(X) else 0,
        "columns": "%d positions x 20 amino acids, row-major" % encode.region_length(region),
        "hash": schema.content_hash({"onehot": [[float(v) for v in row] for row in X]}),
        "ids": [i for i, _ in resolved],
    }
    if out:
        import numpy as np
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        np.save(out, X)
        record["path"] = os.path.relpath(os.path.abspath(out), REPO)
    record["note"] = ("one-hot, not a learned embedding. Two sequences one substitution "
                      "apart differ in exactly two columns")
    return record


@server.tool()
def score_properties(project: str, tool_set: str, candidates: list[str]) -> dict:
    """Compute the deterministic properties a design is filtered on.

    These are exact calculations, not predictions: normalized Kyte-Doolittle
    hydrophobicity over the editable window, net charge, and the liability
    motifs a variant *introduces* relative to the parent. The parent's own DG
    is inherited and is not counted against a design.

    The same function backs the constraint filter, so `passes` here is the same
    verdict that removed 2,967 of 10,261 designs from the pool -- a filter
    enforced in code before any model runs, never a preference handed to one.

    Args:
        project: path to the project directory
        tool_set: developability
        candidates: full sequences or design ids from this project
    """
    state = _state(project)
    _require_local(state, "property scoring")
    if tool_set not in TOOL_SETS:
        raise BackendError("unknown tool_set %r; this build has %s"
                           % (tool_set, ", ".join(sorted(TOOL_SETS))))

    resolved = _resolve(state, candidates)
    obj = state["objectives"]
    parent, region = state["designs"]["parent"], obj["editable_region"]
    thresholds = {o["name"]: o.get("threshold") for o in obj["objectives"]
                  if o.get("source") == "computed"}

    rows, n_pass = [], 0
    for design_id, seq in resolved:
        sc = scoring.score(seq, parent, region)
        fails = [name for name, limit in thresholds.items()
                 if limit is not None and sc.get(name) is not None and sc[name] > limit]
        n_pass += not fails
        rows.append(dict(sc, design_id=design_id, passes=not fails, fails=fails,
                         mutations=encode.mutation_labels(parent, seq, region)))
    return {
        "tool_set": tool_set, "backend": "local", "source": "computed",
        "properties": list(TOOL_SETS[tool_set]), "thresholds": thresholds,
        "n": len(rows), "n_passing": n_pass, "results": rows,
        "note": ("exact calculations from core/scoring.py, hashed into every record that "
                 "uses them. Not predictions, and not a model's opinion"),
    }


@server.tool()
def predict_structures(project: str, model: str, complexes: list[str]) -> dict:
    """Stubbed. No structure prediction runs anywhere in this build.

    The tool exists so the provider interface is the shape a real one has, and
    it returns a cached placeholder rather than a plausible-looking number.
    Inventing per-complex confidences would be exactly the failure this build
    is most careful about: a mock dressed up as a result. There is nothing
    downstream of this tool -- no score, no filter, no record reads it.

    Args:
        project: path to the project directory
        model: any name; nothing is run
        complexes: design ids or sequences to have "predicted"
    """
    _state(project)
    return {
        "status": "stubbed",
        "computed": False,
        "model_requested": model,
        "n_requested": len(complexes),
        "results": [{"complex": c, "prediction": None, "confidence": None}
                    for c in complexes],
        "cached": {"kind": "placeholder", "structure": None,
                   "note": "a fixed placeholder, not a prediction and not a structure"},
        "note": ("structure prediction is NOT implemented in this build. This tool "
                 "predicts nothing, no structure model is installed, and no part of the "
                 "optimization loop consumes a structure. Say so if you cite it."),
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--tools" in argv:
        print("bioprovider_server tools (the provider stand-in):")
        for name, doc in TOOLS:
            print("  %-20s %s" % (name, doc))
        print("\nbackends:")
        for name, doc in sorted(BACKENDS.items()):
            print("  %-20s %s" % (name, doc))
        print("\nSelecting an unwired backend is an error, never a silent fallback.")
        return 0
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
