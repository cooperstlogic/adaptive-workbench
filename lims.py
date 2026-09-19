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

Phase 5 wraps these same functions in a FastMCP stdio server. The logic lives
in a plain module so that wrapping is a change of transport and not a second
implementation -- the fork CLAUDE.md's non-negotiable 2 forbids.

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
        reg = Registry(store_path_for(args.project or "", args.store))
        rows = reg.pull_assay_results(args.round)
        text = rows_to_csv(rows)
        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
            statuses = {}
            for r in rows:
                statuses[r["status"]] = statuses.get(r["status"], 0) + 1
            print("pulled %d rows for %s, assay version %s"
                  % (len(rows), args.round, rows[0]["assay_version"] if rows else "?"))
            print("status  %s" % ", ".join("%s %d" % kv for kv in sorted(statuses.items())))
            print("wrote   %s" % args.out)
        else:
            sys.stdout.write(text)
        return 0

    from core import project as project_mod

    if args.cmd == "attach":
        reg = Registry(store_path_for(args.project, args.store))
        rec = reg.attach_recommendation(args.batch_id, args.url)
        print("attached %s -> %s" % (rec["batch_id"], rec["report_url"]))
        return 0

    # submit
    state = project_mod.load(args.project)
    batch = project_mod.read_artifact(state, "batches", args.round)
    if batch is None:
        print("no batch for round %d; run select_batch.py first" % args.round, file=sys.stderr)
        return 2
    if batch["approval"]["status"] == "unreviewed":
        print("note: batch_%03d is unreviewed -- submitting what the optimizer recommended"
              % args.round, file=sys.stderr)
    by_id = project_mod.designs_by_id(state)
    designs = [{"design_id": d, "sequence": by_id[d]["sequence"]} for d in batch["approved"]]

    reg = Registry(store_path_for(args.project, args.store), run_seed=args.run_seed)
    result = reg.submit_batch(state["project"]["id"], args.round, designs)
    project_mod.register_external_refs(state, result["external_refs"])
    project_mod.link_round(state, args.round, submission={
        "round_id": result["round_id"], "assay_version": result["assay_version"],
        "n_samples": result["n_samples"], "registry": "mock-lims",
    })

    print("submitted   %d designs as %s, assay version %s"
          % (len(designs), result["round_id"], result["assay_version"]))
    print("minted      %d sample ids, %d constructs total"
          % (result["n_samples"], len(reg.store["constructs"])))
    print("plates      %s" % ", ".join(sorted({r["plate"] for r in result["external_refs"]})))
    print("store       %s" % os.path.relpath(reg.store_path, REPO))
    print("refs        written into designs.json; the workbench owns the link and nothing else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
