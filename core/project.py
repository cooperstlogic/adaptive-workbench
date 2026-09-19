"""Template instantiation and project-state accessors.

A project is a directory. That is the whole persistence layer -- no database,
no server -- which is what lets the skill scripts, the MCP servers and the
browser read the same bytes.
"""

import datetime
import os

from . import candidates, encode, schema, scoring


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def create(root, template, lead_name=None, target=None, team=None, batch_size=None, created=None):
    """Instantiate a project directory from a template.

    The scientist supplies three facts; everything else -- the objectives
    schema, the constraint ruleset, the permitted recipes and diagnostics, the
    batch policy -- comes from the template rather than from how well someone
    phrased a request.
    """
    paths = schema.ensure_project_dirs(root)
    ts = created or _now()

    batch = dict(template["batch"])
    if batch_size is not None:
        batch["size"] = int(batch_size)

    project = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "id": os.path.basename(os.path.normpath(root)),
        "created": ts,
        "template": {"id": template["id"], "version": template["version"]},
        "lead": {
            "name": lead_name or template["lead"]["name"],
            "chain": template["lead"]["chain"],
            "sequence": template["lead"]["sequence"],
            "known_liabilities": template["lead"].get("known_liabilities", []),
        },
        "target": target or "HER2",
        "team": team or [],
        "sources": {
            "registry": {"kind": "mock-lims", "server": "registry_server"},
            "bioprovider": {"kind": "tamarind-shaped", "server": "bioprovider_server", "backend": "local"},
        },
        "feature_block": "onehot",
    })

    objectives = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "version": 1,
        "created": ts,
        "unit": schema.UNIT,
        "editable_region": list(template["lead"]["editable_region"]),
        "objectives": template["objectives"],
        "constraints": template["constraints"],
        "batch": batch,
        "model_recipes": template["model_recipes"],
        "diagnostics": template["diagnostics"],
        "anomaly_flag": template["anomaly_flag"],
    })

    rounds = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "project": project["id"],
        "rounds": [],
    })

    designs = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "parent": template["lead"]["sequence"],
        "designs": [],
        "external_refs": [],
    })

    schema.write_json(paths["project"], project)
    schema.write_json(paths["objectives"], objectives)
    schema.write_json(paths["rounds"], rounds)
    schema.write_json(paths["designs"], designs)
    return paths


def load(root):
    p = schema.project_paths(root)
    return {
        "paths": p,
        "project": schema.read_json(p["project"]),
        "objectives": schema.read_json(p["objectives"]),
        "designs": schema.read_json(p["designs"]),
        "rounds": schema.read_json(p["rounds"]),
    }


def design_record(sequence, parent, editable_region, origin, round_id):
    sc = scoring.score(sequence, parent, editable_region)
    return {
        "design_id": encode.sequence_id(sequence),
        "sequence": sequence,
        "parent": encode.sequence_id(parent),
        "mutations": encode.mutation_labels(parent, sequence, editable_region),
        "n_mutations": encode.n_mutations(parent, sequence, editable_region),
        "computed": {
            "hydrophobicity": sc["hydrophobicity"],
            "net_charge": sc["net_charge"],
            "liability_count": sc["liability_count"],
        },
        "origin": origin,
        "first_round": int(round_id),
        "registry_id": None,
    }


def add_designs(state, sequences, origin, round_id):
    """Append designs, skipping any already present. Returns the new records."""
    parent = state["designs"]["parent"]
    region = state["objectives"]["editable_region"]
    known = {d["design_id"] for d in state["designs"]["designs"]}
    added = []
    for s in sequences:
        rec = design_record(s, parent, region, origin, round_id)
        if rec["design_id"] in known:
            continue
        known.add(rec["design_id"])
        state["designs"]["designs"].append(rec)
        added.append(rec)
    state["designs"] = schema.stamp({k: v for k, v in state["designs"].items() if k != "hash"})
    schema.write_json(state["paths"]["designs"], state["designs"])
    return added


def feasible_pool(state):
    """Enumerate, then enforce every declared constraint in code.

    -> (kept, removed, summary). Both arms of the comparison draw from `kept`.
    """
    parent = state["designs"]["parent"]
    obj = state["objectives"]
    pool = candidates.enumerate_variants(parent, obj["editable_region"], obj["constraints"]["max_mutations"])
    kept, removed = candidates.constraint_report(
        pool, parent, obj["editable_region"], obj["objectives"], obj["constraints"]
    )
    return kept, removed, candidates.removal_summary(removed)
