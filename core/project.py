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
        "diagnostics_policy": template["diagnostics_policy"],
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


# --- the round graph -------------------------------------------------------
#
# rounds.json is the artifact that matters: the thin longitudinal link from
# recommendation to tested constructs to returned evidence to diagnosis to
# updated model to next batch. Everything else in a project could be
# regenerated from the snapshots; this could not.


def pool_fingerprint(sequences):
    """A content hash over the ordered feasible pool.

    Every later record indexes into this order -- a model run stores one
    prediction per pool member and nothing else -- so the order is part of the
    lineage and is hashed rather than assumed. Enumeration is deterministic,
    so storing the hash costs nine hundred bytes where storing the pool costs
    most of a megabyte, and a mismatch is caught instead of silently
    misaligning every prediction by one.
    """
    return schema.content_hash({"pool": list(sequences)})


def artifact_ref(root, path, record):
    """A round-graph pointer: where the record is, and what it hashed to."""
    return {"file": os.path.relpath(path, root).replace(os.sep, "/"),
            "hash": record["hash"]}


def link_round(state, round_id, **artifacts):
    """Attach artifacts to a round and rewrite rounds.json.

    Called by every pipeline script at the end of its run, which is what keeps
    the graph complete without any script knowing about the others.
    """
    rounds = state["rounds"].setdefault("rounds", [])
    entry = next((r for r in rounds if int(r["round"]) == int(round_id)), None)
    if entry is None:
        entry = {"round": int(round_id)}
        rounds.append(entry)
        rounds.sort(key=lambda r: int(r["round"]))
    entry.update(artifacts)
    entry["updated"] = _now()
    state["rounds"] = schema.stamp({k: v for k, v in state["rounds"].items() if k != "hash"})
    schema.write_json(state["paths"]["rounds"], state["rounds"])
    return entry


def round_entry(state, round_id):
    for r in state["rounds"].get("rounds", []):
        if int(r["round"]) == int(round_id):
            return r
    return None


def artifact_path(state, kind, round_id, suffix=""):
    return os.path.join(state["paths"][kind],
                        schema.numbered(_STEM[kind], int(round_id)) + suffix + ".json")


_STEM = {"candidates": "pool", "batches": "batch", "evidence": "snapshot",
         "models": "run", "decisions": "decision"}


def read_artifact(state, kind, round_id, suffix=""):
    """Load a numbered artifact, or None when that round has not reached it."""
    path = artifact_path(state, kind, round_id, suffix)
    return schema.read_json(path) if os.path.exists(path) else None


def snapshots(state, through=None):
    """Every evidence snapshot the project holds, in round order."""
    out = []
    for name in sorted(os.listdir(state["paths"]["evidence"])):
        if not (name.startswith("snapshot_") and name.endswith(".json")):
            continue
        rec = schema.read_json(os.path.join(state["paths"]["evidence"], name))
        if through is not None and int(rec["round"]) > int(through):
            continue
        out.append(rec)
    return sorted(out, key=lambda r: int(r["round"]))


def measurement_records(state, through=None):
    """Flatten every snapshot into the record shape ``reconcile.pool`` eats.

    One implementation of "what does this project believe it has measured",
    shared by the fitting script, the selection script and the browser.
    """
    records = []
    for snap in snapshots(state, through=through):
        for m in snap["measurements"]:
            rec = dict(m)
            rec["round"] = int(snap["round"])
            records.append(rec)
    return records


def known_version_offsets(state, through=None):
    """What the project has already established about each assay version.

    A version first seen in round N is by definition uncharacterized when
    round N lands -- which is exactly why that round is the one that needs a
    ruling, and why the rounds after it do not: they are compared against a
    fact the project has since recorded. Derived from the snapshots rather
    than stored, so there is no second place for it to go stale.
    """
    known = {}
    for snap in snapshots(state, through=through):
        version = snap["assay_version"]
        if version not in known:
            known[version] = float(snap["frame"]["offset_applied"])
    return known


DECISION_ID = "decision_%03d"


def decision_id(round_id):
    return DECISION_ID % int(round_id)


def names_decision(authority):
    """Does this authority name a decision record, or a standing policy?

    Both are legitimate things to correct a round under -- a policy covers the
    rounds nobody had to think about -- but only one of them is a ruling, and
    the difference decides whether a flagged round is still waiting on a
    human. Kept here so the import script and the fitting script cannot answer
    it differently.
    """
    if not isinstance(authority, str):
        return None
    name = authority.strip()
    if len(name) == len("decision_000") and name.startswith("decision_") and name[9:].isdigit():
        return name
    return None


def read_decision(state, round_id):
    """The decision record for a round, or None if nobody has written one."""
    return read_artifact(state, "decisions", round_id)


def is_ruled(state, round_id):
    """Has a human ruled on this round?

    Ruled-ness is a property of the decision record and not of the snapshot,
    because the commonest correct ruling on a flagged round -- refit and touch
    nothing -- changes no measurement and therefore moves no frame. A snapshot
    whose frame says ``unruled`` after such a ruling is telling the truth
    about the frame; this is what tells the truth about the round.
    """
    rec = read_decision(state, round_id)
    return bool(rec and rec.get("status") == "ruled")


def unruled_flagged_rounds(state, through=None):
    """Flagged rounds still waiting on a human, in round order.

    The list the fitting script prints and the scheduler stops on.
    """
    return [int(s["round"]) for s in snapshots(state, through=through)
            if s["flagged"] and not is_ruled(state, s["round"])]


def designs_by_id(state):
    return {d["design_id"]: d for d in state["designs"]["designs"]}


def register_external_refs(state, refs):
    """Store the registry's identifiers for designs we submitted.

    The workbench owns the link and nothing about the samples themselves. This
    table is the only way back from a returned row to a design, which is what
    makes reconciliation real work rather than a lookup by sequence.
    """
    table = state["designs"].setdefault("external_refs", [])
    seen = {(r["sample_id"]) for r in table}
    added = []
    for ref in refs:
        if ref["sample_id"] in seen:
            continue
        seen.add(ref["sample_id"])
        table.append(dict(ref))
        added.append(ref)
    by_id = designs_by_id(state)
    for ref in refs:
        d = by_id.get(ref["design_id"])
        if d is not None and not d.get("registry_id"):
            d["registry_id"] = ref["construct_id"]
    state["designs"] = schema.stamp({k: v for k, v in state["designs"].items() if k != "hash"})
    schema.write_json(state["paths"]["designs"], state["designs"])
    return added


def sequence_by_sample(state):
    """sample_id -> sequence, through the external reference table only."""
    by_id = designs_by_id(state)
    out = {}
    for ref in state["designs"].get("external_refs", []):
        d = by_id.get(ref["design_id"])
        if d is not None:
            out[ref["sample_id"]] = d["sequence"]
    return out
