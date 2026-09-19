#!/usr/bin/env python3
"""The mock LIMS: the boundary between the workbench and the laboratory.

The simulated lab lives here, not inside the workbench. ``core/`` never
imports the oracle, so the workbench sees only what a lab reported and never
ground truth. That boundary is the point of this file, and it is why the
registry owns three things the workbench does not: the construct and sample
identifiers, the plate layout, and the measurements themselves.

The write path is deliberately crippled. It mints identifiers for designs
someone submitted and it can attach a recommendation link to an existing
record. It cannot create samples out of nothing, edit assay data, or drive a
workflow. When someone asks in the demo whether this replaces Benchling, the
answer is the tool list.

``connectors/registry_server.py`` wraps these same functions in an MCP stdio
server. The logic lives in this plain module so that wrapping is a change of
transport and not a second implementation -- the fork CLAUDE.md's
non-negotiable 2 forbids. The two orchestrating calls a submission needs,
``submit_project_batch`` and ``pull_to_csv``, are module functions for that
reason: ``main`` prints what they return, the connector serializes it, and
neither one reimplements the other.

    python lims.py submit --project projects/demo-trastuzumab --round 1
    python lims.py pull   --round R1 --out /tmp/round1.csv
    python lims.py tools

Results are generated once, at submission, and stored. Pulling is a read, the
way it is in a real lab, so a round replays identically however often you ask
for it.
"""

import argparse
import csv
import datetime
import io
import os
import sys

from core import acquisition, schema
from data import oracle as oracle_mod
from data import synthetic

REPO = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(REPO, "data", "landscape_manifest.json")
STORE_DIR = os.path.join(REPO, "lims_store")

# The shape a real export has, not the shape the model would prefer. The
# sample id is the registry's identifier and never the design id, which is
# what gives import_round genuine reconciliation work.
COLUMNS = ("sample_id", "plate", "well", "assay_version", "replicate", "value", "unit", "status")

WELL_ROWS = "ABCDEFGH"
WELL_COLS = 12


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def well_label(index):
    """Row-major within a plate: A1..A12, B1..B12, ..."""
    return "%s%d" % (WELL_ROWS[(index // WELL_COLS) % len(WELL_ROWS)], index % WELL_COLS + 1)


class Registry:
    """The LIMS stand-in. Owns identifiers, plates, and the simulated assay."""

    def __init__(self, store_path, run_seed=0, manifest=None):
        self.store_path = store_path
        self.manifest = manifest or schema.read_json(MANIFEST)
        self.store = (schema.read_json(store_path) if os.path.exists(store_path) else {
            "schema_version": schema.SCHEMA_VERSION,
            "kind": "mock_lims_store",
            "run_seed": int(run_seed),
            "landscape_build_hash": self.manifest["build_hash"],
            "constructs": {},
            "next_construct": 1,
            "rounds": {},
            "recommendations": [],
        })
        self._oracle = None

    # -- the simulated lab, built lazily so `tools` and `pull` stay instant --

    @property
    def oracle(self):
        if self._oracle is None:
            man = self.manifest
            land = synthetic.Landscape(man["parent"], man["editable_region"], man["params"])
            land.beta = man["derived"]["beta"]
            self._oracle = oracle_mod.Oracle(
                land, man["derived"]["detection_limit_pkd"],
                params=man["params"], run_seed=int(self.store["run_seed"]))
        return self._oracle

    def save(self):
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        schema.write_json(self.store_path, self.store)
        return self.store_path

    # -- tools ------------------------------------------------------------

    def submit_batch(self, project_id, round_id, designs):
        """Mint construct and sample identifiers, record the round in flight.

        Returns only the external references. The workbench stores those links
        in designs.json and owns nothing about the samples themselves.
        """
        key = "R%d" % int(round_id)
        if key in self.store["rounds"]:
            raise ValueError("round %s has already been submitted; the registry does not "
                             "overwrite assay data" % key)
        sequences = [d["sequence"] for d in designs]
        plates = acquisition.assign_plates(sequences, int(round_id))
        version = oracle_mod.assay_version(int(round_id))

        refs, samples = [], []
        for i, d in enumerate(designs):
            cst = self.store["constructs"].get(d["design_id"])
            if cst is None:
                cst = {"construct_id": "CST%05d" % self.store["next_construct"],
                       "design_id": d["design_id"], "sequence": d["sequence"],
                       "registered": _now()}
                self.store["constructs"][d["design_id"]] = cst
                self.store["next_construct"] += 1
            sample_id = "SMP-%s-%03d" % (key, i + 1)
            ref = {"design_id": d["design_id"], "construct_id": cst["construct_id"],
                   "sample_id": sample_id, "plate": plates[i], "round": int(round_id)}
            refs.append(ref)
            samples.append(dict(ref))

        rows = self._measure(sequences, int(round_id), plates, samples)
        self.store["rounds"][key] = {
            "round_id": key, "round": int(round_id), "project": project_id,
            "assay_version": version, "submitted": _now(), "status": "complete",
            "n_samples": len(samples), "n_rows": len(rows),
            "samples": samples, "rows": rows,
        }
        self.save()
        return {"round_id": key, "assay_version": version, "status": "complete",
                "n_samples": len(samples), "external_refs": refs}

    def _measure(self, sequences, round_id, plates, samples):
        """Call the oracle once and lay its reads out into wells.

        Replicates come back as separate rows in separate wells, never
        pre-averaged, and a failed construct takes out every read for its
        design.
        """
        reads = self.oracle.measure(sequences, round_id, plates)
        by_plate_well = {}
        by_sequence = {}
        for r in reads:
            by_sequence.setdefault(r["sequence"], []).append(r)
        rows = []
        for sample, seq in zip(samples, sequences):
            for read in by_sequence[seq]:
                plate = read["plate"]
                idx = by_plate_well.get(plate, 0)
                by_plate_well[plate] = idx + 1
                rows.append({
                    "sample_id": sample["sample_id"],
                    "plate": plate,
                    "well": well_label(idx),
                    "assay_version": read["assay_version"],
                    "replicate": int(read["replicate"]),
                    "value": read["value"],
                    "unit": read["unit"],
                    "status": read["status"],
                })
            by_sequence[seq] = []
        return rows

    def pull_assay_results(self, round_id):
        """Rows keyed by sample id. No design id, no sequence, no ground truth."""
        key = round_id if str(round_id).startswith("R") else "R%d" % int(round_id)
        rec = self.store["rounds"].get(key)
        if rec is None:
            raise KeyError("no such round in the registry: %s" % key)
        return [dict(r) for r in rec["rows"]]

    def list_designs(self):
        return [{"design_id": c["design_id"], "construct_id": c["construct_id"],
                 "registered": c["registered"]}
                for c in sorted(self.store["constructs"].values(),
                                key=lambda c: c["construct_id"])]

    def get_construct(self, construct_id):
        for c in self.store["constructs"].values():
            if c["construct_id"] == construct_id:
                return dict(c)
        raise KeyError("no such construct: %s" % construct_id)

    def attach_recommendation(self, batch_id, report_url):
        """The entire write path, and it is deliberately this small."""
        rec = {"batch_id": batch_id, "report_url": report_url, "at": _now()}
        self.store["recommendations"].append(rec)
        self.save()
        return rec


TOOLS = [
    ("submit_batch", "Mint construct and sample ids for approved designs; records the round"),
    ("list_designs", "Designs the registry holds, with their construct ids"),
    ("pull_assay_results", "Assay rows for a round, keyed by sample id"),
    ("get_construct", "One construct record"),
    ("attach_recommendation", "Attach a recommendation id and a link to an existing record"),
]


def rows_to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(COLUMNS), lineterminator="\n")
    w.writeheader()
    for r in rows:
        out = {k: r.get(k) for k in COLUMNS}
        out["value"] = "" if r.get("value") is None else "%.6f" % float(r["value"])
        w.writerow(out)
    return buf.getvalue()


def read_csv(path):
    """-> rows with value back to float or None. The inverse of rows_to_csv."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        out = []
        for raw in csv.DictReader(fh):
            row = dict(raw)
            row["replicate"] = int(row["replicate"])
            row["value"] = None if row["value"] in ("", None) else float(row["value"])
            out.append(row)
    return out


def store_path_for(project_root, store=None):
    if store:
        return store
    return os.path.join(STORE_DIR, "%s.json" % os.path.basename(os.path.normpath(project_root)))


EXPORT_DIR = os.path.join(STORE_DIR, "exports")


def export_path_for(project_root, round_id):
    """Where a round's assay export lands by default.

    ``run_rounds.py`` and the registry connector agree on this path so that
    the command after a pull is always the same command.
    """
    name = os.path.basename(os.path.normpath(project_root))
    n = int(str(round_id).lstrip("Rr")) if str(round_id).lstrip("Rr").isdigit() else round_id
    return os.path.join(EXPORT_DIR, "%s_round%s.csv" % (name, n))


def submit_project_batch(project_root, round_id, store=None, run_seed=0):
    """Submit a project's approved batch and record the links it gets back.

    The registry mints the identifiers and owns the samples; the workbench
    keeps the external references and nothing else. Returns a record rather
    than printing one, because two surfaces call this.
    """
    from core import project as project_mod

    state = project_mod.load(project_root)
    batch = project_mod.read_artifact(state, "batches", int(round_id))
    if batch is None:
        raise ValueError("no batch for round %d; run select_batch.py first" % int(round_id))
    by_id = project_mod.designs_by_id(state)
    designs = [{"design_id": d, "sequence": by_id[d]["sequence"]} for d in batch["approved"]]

    reg = Registry(store_path_for(project_root, store), run_seed=run_seed)
    result = reg.submit_batch(state["project"]["id"], int(round_id), designs)
    project_mod.register_external_refs(state, result["external_refs"])
    project_mod.link_round(state, int(round_id), submission={
        "round_id": result["round_id"], "assay_version": result["assay_version"],
        "n_samples": result["n_samples"], "registry": "mock-lims",
    })
    result["n_designs"] = len(designs)
    result["n_constructs"] = len(reg.store["constructs"])
    result["plates"] = sorted({r["plate"] for r in result["external_refs"]})
    result["store"] = reg.store_path
    result["approval_status"] = batch["approval"]["status"]
    return result


def pull_to_csv(round_id, project_root=None, store=None, out=None):
    """Read a round's rows and write the export a real pull would produce.

    Pulling is a read: the values were generated once, at submission, so a
    round replays identically however often it is asked for.
    """
    reg = Registry(store_path_for(project_root or "", store))
    rows = reg.pull_assay_results(round_id)
    text = rows_to_csv(rows)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    statuses = {}
    for r in rows:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    key = round_id if str(round_id).startswith("R") else "R%d" % int(round_id)
    return {"round_id": key,
            "n_rows": len(rows), "assay_version": rows[0]["assay_version"] if rows else None,
            "status_counts": statuses, "path": out, "csv": text, "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="submit a project's approved batch for a round")
    s.add_argument("--project", required=True)
    s.add_argument("--round", type=int, required=True)
    s.add_argument("--store", default=None)
    s.add_argument("--run-seed", type=int, default=0)

    p = sub.add_parser("pull", help="export a round's assay results as CSV")
    p.add_argument("--round", required=True)
    p.add_argument("--project", default=None)
    p.add_argument("--store", default=None)
    p.add_argument("--out", default=None)

    t = sub.add_parser("tools", help="print the tool list, which is the boundary claim")
    t.add_argument("--store", default=None)

    a = sub.add_parser("attach", help="attach a recommendation link to a batch record")
    a.add_argument("--project", required=True)
    a.add_argument("--batch-id", required=True)
    a.add_argument("--url", required=True)
    a.add_argument("--store", default=None)

    args = ap.parse_args(argv)

    if args.cmd == "tools":
        print("registry_server tools (the LIMS stand-in):")
        for name, doc in TOOLS:
            print("  %-22s %s" % (name, doc))
        print("\nnot available, deliberately: create_sample, edit_assay_result,")
        print("start_workflow, delete_record. The write path attaches a link and nothing more.")
        return 0

    if args.cmd == "pull":
        if not (args.store or args.project):
            print("pull needs --store or --project", file=sys.stderr)
            return 2
        res = pull_to_csv(args.round, args.project, args.store, args.out)
        if args.out:
            print("pulled %d rows for %s, assay version %s"
                  % (res["n_rows"], args.round, res["assay_version"] or "?"))
            print("status  %s" % ", ".join("%s %d" % kv
                                           for kv in sorted(res["status_counts"].items())))
            print("wrote   %s" % args.out)
        else:
            sys.stdout.write(res["csv"])
        return 0

    if args.cmd == "attach":
        reg = Registry(store_path_for(args.project, args.store))
        rec = reg.attach_recommendation(args.batch_id, args.url)
        print("attached %s -> %s" % (rec["batch_id"], rec["report_url"]))
        return 0

    # submit
    try:
        result = submit_project_batch(args.project, args.round, args.store, args.run_seed)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if result["approval_status"] == "unreviewed":
        print("note: batch_%03d is unreviewed -- submitting what the optimizer recommended"
              % args.round, file=sys.stderr)

    print("submitted   %d designs as %s, assay version %s"
          % (result["n_designs"], result["round_id"], result["assay_version"]))
    print("minted      %d sample ids, %d constructs total"
          % (result["n_samples"], result["n_constructs"]))
    print("plates      %s" % ", ".join(result["plates"]))
    print("store       %s" % os.path.relpath(result["store"], REPO))
    print("refs        written into designs.json; the workbench owns the link and nothing else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
