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

**A round can be held in flight.** ``submit_batch(stagger=True)`` writes the
round ``running`` rather than ``complete``, and ``check_run_status`` is the
only thing that releases it. That exists because approving a batch and reading
its data in the same second is the least believable moment in the demo, and an
audience of people who have run assays notices. Off -- the default, and what
every CLI path uses -- the record written is byte for byte the one this file
has always written, so no existing store, no existing round and no existing
campaign changes. The release schedule is a demo device and it reads as one
here, which is the right place for it to be obvious.

``release_run`` is the other half of that device: it says the assay has
finished, now, so that a person being shown this does not have to guess that
asking twice is what moves the clock. It writes ``released_by`` beside the
status and changes nothing else -- the values were measured at submission
either way. It is deliberately absent from ``TOOLS``, because a registry does
not have a button that finishes an assay, and that tool list is the answer to
"does this replace the LIMS".
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

# The order the lab receives. It is the inverse of COLUMNS in one respect that
# matters: it carries the sequence and the design id, because the lab needs to
# know what to make, and it carries no value, because an order is not a result.
ORDER_COLUMNS = ("construct_id", "sample_id", "design_id", "round", "plate", "sequence",
                 "assay_version")

# How long the simulated lab takes. Only ever reported, never waited on: it is
# what check_run_status names as the expected date, and it is chosen to agree
# with the spacing of the shipped campaign's rounds.
TURNAROUND_DAYS = 8

WELL_ROWS = "ABCDEFGH"
WELL_COLS = 12


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _plus_days(iso, days):
    """A date the registry can name as expected. Display only.

    Nothing in the round loop reads this and no project artifact records it.
    It exists so a refusal can say *when*, because "not yet" without a date is
    a broken button and "not yet, expected the 27th" is a laboratory.
    """
    when = datetime.datetime.fromisoformat(iso) + datetime.timedelta(days=int(days))
    return when.replace(microsecond=0).isoformat()


def well_label(index):
    """Row-major within a plate: A1..A12, B1..B12, ..."""
    return "%s%d" % (WELL_ROWS[(index // WELL_COLS) % len(WELL_ROWS)], index % WELL_COLS + 1)


class RunningError(ValueError):
    """A pull asked for before the run reported.

    Its own class rather than a bare ValueError so the connector can hand the
    message to the caller intact, and so the refusal is a fact about the
    registry rather than a string somebody matched on.
    """


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

    def submit_batch(self, project_id, round_id, designs, stagger=False):
        """Mint construct and sample identifiers, record the round in flight.

        Returns only the external references. The workbench stores those links
        in designs.json and owns nothing about the samples themselves.

        ``stagger`` holds the round open. Off, the record written is byte for
        byte the one this method has always written -- ``status: "complete"``,
        no extra keys -- which is why every store on disk, every round already
        in one, and check.py's six-round CLI campaign are untouched by this
        argument existing. On, the round is written ``running`` with an
        explicit ``release_on_check`` count, and ``check_run_status`` is the
        only thing that can move it. The values are measured either way, at
        submission, exactly as before; what staggering changes is whether the
        registry will hand them over yet.
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
        submitted = _now()
        record = {
            "round_id": key, "round": int(round_id), "project": project_id,
            "assay_version": version, "submitted": submitted,
            "status": "running" if stagger else "complete",
            "n_samples": len(samples), "n_rows": len(rows),
            "samples": samples, "rows": rows,
        }
        if stagger:
            # How many times someone may ask before the run is released. A
            # record without this key is complete, which is what makes every
            # store written before staggering existed still correct.
            record["release_on_check"] = 1
            record["checks"] = 0
            record["expected"] = _plus_days(submitted, TURNAROUND_DAYS)
        self.store["rounds"][key] = record
        self.save()
        out = {"round_id": key, "assay_version": version, "status": record["status"],
               "n_samples": len(samples), "external_refs": refs}
        if stagger:
            out["expected"] = record["expected"]
        return out

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

    def _round(self, round_id):
        key = round_id if str(round_id).startswith("R") else "R%d" % int(round_id)
        rec = self.store["rounds"].get(key)
        if rec is None:
            raise KeyError("no such round in the registry: %s" % key)
        return key, rec

    def export_submission(self, round_id):
        """The order file the laboratory receives. An order, never a result.

        What a lab needs in order to make something and run it: which
        construct, which sample, which plate, and the sequence itself. What it
        deliberately does not carry is a measured value, because at the moment
        this is written there is nothing to measure yet -- and because a file
        that carried both would let the workbench read its own answers out of
        its own request.

        One row per sample, in submission order, so the export is the
        submission and not a view over it.
        """
        key, rec = self._round(round_id)
        by_design = {c["design_id"]: c for c in self.store["constructs"].values()}
        rows = []
        for sample in rec["samples"]:
            cst = by_design.get(sample["design_id"])
            rows.append({
                "construct_id": sample["construct_id"],
                "sample_id": sample["sample_id"],
                "design_id": sample["design_id"],
                "round": int(sample["round"]),
                "plate": sample["plate"],
                "sequence": cst["sequence"] if cst else "",
                "assay_version": rec["assay_version"],
            })
        return {"round_id": key, "assay_version": rec["assay_version"],
                "submitted": rec["submitted"], "n_rows": len(rows),
                "plates": sorted({r["plate"] for r in rows}), "rows": rows}

    def check_run_status(self, round_id):
        """Has the run finished? Binary, and asking is what moves it.

        A round with no ``release_on_check`` key is complete, which covers
        every store written before staggering existed. A staggered one counts
        the asks and releases itself once the count is passed -- so the first
        ask comes back running with a date, and the next comes back ready.
        That schedule is a demo device rather than a model of a laboratory,
        and it is written here in the open rather than dressed up as a timer.
        """
        key, rec = self._round(round_id)
        if rec.get("status") != "running":
            return {"round_id": key, "status": "complete",
                    "assay_version": rec["assay_version"], "submitted": rec["submitted"],
                    "expected": rec.get("expected"), "n_rows": rec["n_rows"],
                    "n_samples": rec["n_samples"], "released_now": False}
        asks = int(rec.get("checks", 0)) + 1
        rec["checks"] = asks
        released = asks > int(rec.get("release_on_check", 0))
        if released:
            rec["status"] = "complete"
        self.save()
        return {"round_id": key, "status": rec["status"],
                "assay_version": rec["assay_version"], "submitted": rec["submitted"],
                "expected": rec.get("expected"),
                "n_rows": rec["n_rows"] if released else 0,
                "n_samples": rec["n_samples"], "released_now": released,
                "checks": asks}

    def release_run(self, round_id, reason="demo control"):
        """Say the assay has finished, now. The demo device, named as one.

        ``check_run_status`` releases a held round on the ask after the first,
        which is the schedule ``submit_batch`` wrote and which is fine for a
        harness. In front of a person it is a rule nobody can see: the first
        ask names a date eight days out, and there is nothing on the screen
        that says time can be moved. This is the other way to the same place,
        and it is not a schedule -- it is the laboratory reporting, triggered
        by hand, because the laboratory here is simulated and the only clock
        it has is this one.

        It changes when the rows are handed over and nothing about what they
        are: the values were measured at submission, by the oracle, before
        anyone asked. A round that is not being held is left exactly as it is.
        It is deliberately not in ``TOOLS`` -- a registry does not have a
        button that finishes an assay, and putting one on the connector's list
        would widen the claim this file exists to make.
        """
        key, rec = self._round(round_id)
        if rec.get("status") != "running":
            return {"round_id": key, "status": rec.get("status", "complete"),
                    "released_now": False, "assay_version": rec["assay_version"],
                    "submitted": rec["submitted"], "n_rows": rec["n_rows"],
                    "n_samples": rec["n_samples"],
                    "note": "the run was not being held"}
        rec["status"] = "complete"
        rec["released_by"] = reason
        rec["released_at"] = _now()
        self.save()
        return {"round_id": key, "status": "complete", "released_now": True,
                "assay_version": rec["assay_version"], "submitted": rec["submitted"],
                "expected": rec.get("expected"), "n_rows": rec["n_rows"],
                "n_samples": rec["n_samples"], "released_by": reason,
                "note": "simulated: the assay reported early because someone said so"}

    def pull_assay_results(self, round_id):
        """Rows keyed by sample id. No design id, no sequence, no ground truth."""
        key, rec = self._round(round_id)
        if rec.get("status") == "running":
            raise RunningError(
                "%s is still running: 0 of %d rows released across %s. The registry does "
                "not hand over a run before the assay reports. Expected %s -- ask "
                "check_run_status(round_id=%r)."
                % (key, rec["n_rows"], ", ".join(sorted({s["plate"] for s in rec["samples"]})),
                   (rec.get("expected") or "?")[:10], key))
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
    ("export_submission", "The order file for a submitted round: what the lab receives"),
    ("check_run_status", "Whether a round's assay has reported yet, and when it is expected"),
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


def orders_to_csv(rows):
    """The order file, in the column order a lab would expect to receive it."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(ORDER_COLUMNS), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k) for k in ORDER_COLUMNS})
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


def submit_project_batch(project_root, round_id, store=None, run_seed=0, stagger=False):
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
    result = reg.submit_batch(state["project"]["id"], int(round_id), designs, stagger=stagger)
    project_mod.register_external_refs(state, result["external_refs"])
    # The submission link the project keeps says nothing about whether the run
    # has reported. Where a round is at the lab is the registry's fact, asked
    # for rather than mirrored, which is why it is not written here.
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


def export_order(round_id, project_root=None, store=None, out=None):
    """Write the order file a round's submission produces.

    The counterpart to ``pull_to_csv``: same shape of call, opposite
    direction. One goes to the lab and carries no measurement; the other comes
    back and is nothing but measurement.
    """
    reg = Registry(store_path_for(project_root or "", store))
    res = reg.export_submission(round_id)
    text = orders_to_csv(res["rows"])
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    return dict(res, csv=text, path=out, columns=list(ORDER_COLUMNS))


def order_path_for(project_root, round_id):
    """Where a round's order file lands by default, beside its results export."""
    name = os.path.basename(os.path.normpath(project_root))
    n = int(str(round_id).lstrip("Rr")) if str(round_id).lstrip("Rr").isdigit() else round_id
    return os.path.join(EXPORT_DIR, "%s_round%s_order.csv" % (name, n))


def run_status(round_id, project_root=None, store=None):
    """Ask the registry whether a round has reported. Asking moves a staggered one."""
    reg = Registry(store_path_for(project_root or "", store))
    return reg.check_run_status(round_id)


def release_run(round_id, project_root=None, store=None, reason="demo control"):
    """Have the simulated laboratory report a held run now. A demo device."""
    reg = Registry(store_path_for(project_root or "", store))
    return reg.release_run(round_id, reason)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="submit a project's approved batch for a round")
    s.add_argument("--project", required=True)
    s.add_argument("--round", type=int, required=True)
    s.add_argument("--store", default=None)
    s.add_argument("--run-seed", type=int, default=0)
    s.add_argument("--stagger", action="store_true",
                   help="hold the round running until check_run_status releases it")

    p = sub.add_parser("pull", help="export a round's assay results as CSV")
    p.add_argument("--round", required=True)
    p.add_argument("--project", default=None)
    p.add_argument("--store", default=None)
    p.add_argument("--out", default=None)

    e = sub.add_parser("export", help="write the order file a submitted round produces")
    e.add_argument("--round", required=True)
    e.add_argument("--project", default=None)
    e.add_argument("--store", default=None)
    e.add_argument("--out", default=None)

    st = sub.add_parser("status", help="ask whether a round's assay has reported")
    st.add_argument("--round", required=True)
    st.add_argument("--project", default=None)
    st.add_argument("--store", default=None)

    rl = sub.add_parser("release", help="simulated: have the lab report a held run now")
    rl.add_argument("--round", required=True)
    rl.add_argument("--project", default=None)
    rl.add_argument("--store", default=None)
    rl.add_argument("--reason", default="demo control")

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
        print("export_submission and check_run_status are reads a real LIMS unambiguously")
        print("owns; adding them widens the tool list without widening the write path.")
        return 0

    if args.cmd == "export":
        if not (args.store or args.project):
            print("export needs --store or --project", file=sys.stderr)
            return 2
        out = args.out or (order_path_for(args.project, args.round) if args.project else None)
        try:
            res = export_order(args.round, args.project, args.store, out)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if out:
            print("order       %d rows for %s, assay version %s"
                  % (res["n_rows"], res["round_id"], res["assay_version"]))
            print("plates      %s" % ", ".join(res["plates"]))
            print("columns     %s" % ", ".join(res["columns"]))
            print("wrote       %s" % out)
            print("no value column: this is what goes to the lab, not what comes back")
        else:
            sys.stdout.write(res["csv"])
        return 0

    if args.cmd == "status":
        if not (args.store or args.project):
            print("status needs --store or --project", file=sys.stderr)
            return 2
        try:
            res = run_status(args.round, args.project, args.store)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print("round       %s" % res["round_id"])
        print("status      %s" % res["status"])
        print("assay       %s, submitted %s" % (res["assay_version"], res["submitted"][:10]))
        if res["status"] == "running":
            print("expected    %s -- nothing to pull yet" % (res["expected"] or "?")[:10])
        else:
            print("rows        %d across %d samples" % (res["n_rows"], res["n_samples"]))
        return 0

    if args.cmd == "release":
        if not (args.store or args.project):
            print("release needs --store or --project", file=sys.stderr)
            return 2
        try:
            res = release_run(args.round, args.project, args.store, args.reason)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print("round       %s" % res["round_id"])
        if res["released_now"]:
            print("status      complete -- the assay reported (simulated, by %s)"
                  % res["released_by"])
            print("expected    %s, which is when it would have"
                  % (res.get("expected") or "?")[:10])
        else:
            print("status      %s -- %s" % (res["status"], res["note"]))
        print("rows        %d across %d samples, measured at submission either way"
              % (res["n_rows"], res["n_samples"]))
        return 0

    if args.cmd == "pull":
        if not (args.store or args.project):
            print("pull needs --store or --project", file=sys.stderr)
            return 2
        try:
            res = pull_to_csv(args.round, args.project, args.store, args.out)
        except RunningError as exc:
            print(str(exc), file=sys.stderr)
            return 2
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
        result = submit_project_batch(args.project, args.round, args.store, args.run_seed,
                                      stagger=args.stagger)
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
    if result["status"] == "running":
        print("status      running -- expected %s. Nothing to pull until check_run_status "
              "releases it" % (result.get("expected") or "?")[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
