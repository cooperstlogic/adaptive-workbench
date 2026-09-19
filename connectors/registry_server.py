#!/usr/bin/env python3
"""registry_server -- the LIMS stand-in, over MCP stdio.

Every tool here is one call into ``lims.py``. That is the whole file: this is
a change of transport, not a second implementation, which is CLAUDE.md's
non-negotiable 2 applied to the connector layer. If a number differs between
the CLI and this server, one of them is wrong, and there is only one place to
look.

**The write path is deliberately crippled, and that is the claim.** This
server can mint identifiers for designs somebody submitted, and it can attach
a recommendation link to a record that already exists. It cannot create a
sample, edit an assay result, start a workflow or delete anything. When
someone asks in the demo whether this replaces the LIMS, the answer is to read
the tool list.

**The simulated laboratory lives behind this boundary.** ``core/`` never
imports the oracle. The workbench sees what the registry reported and never
ground truth -- which is why a run offset is something the loop has to
estimate rather than look up.

    .venv/bin/python connectors/registry_server.py          # speaks MCP on stdio
    .venv/bin/python connectors/registry_server.py --tools  # print the boundary claim
"""

import os
import sys

# The repo root is not on sys.path when this file is run as a script, because
# sys.path[0] is connectors/. Insert it so ``lims`` and ``core`` resolve. The
# directory is called connectors/ and not mcp/ for the reason in CLAUDE.md's
# non-negotiable 4: a bare mcp/ shadows the SDK this server imports.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# The SDK renamed FastMCP to MCPServer at 2.0 and dropped the ``version=``
# argument on the way. This repo's .venv carries 2.x; the interpreter Claude
# Science resolves a bare ``python`` connector command to carries 1.x. One
# server serves both, which is CLAUDE.md's non-negotiable 2 applied to the
# transport layer -- decision 101.
try:
    from mcp.server.mcpserver import MCPServer  # noqa: E402
    from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
    SERVER_KWARGS = {"version": "1.0.0"}
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # noqa: E402
    from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402
    SERVER_KWARGS = {}

import lims  # noqa: E402

INSTRUCTIONS = """The registry for an adaptive optimization project: the mock
LIMS that owns construct and sample identifiers, the plate layout, and the
assay results.

Submit an approved batch with submit_batch, then pull_assay_results to get the
export, then hand that CSV to import_round.py. Results are generated once, at
submission, so pulling is a read and a round replays identically.

This connector cannot create a sample, edit an assay result, start a workflow
or delete a record. Those are the laboratory's to do, not the workbench's. If
you need one of them, say so rather than working around it.

Everything laboratory here is simulated: the landscape is synthetic and the
assay is an oracle replaying generated values with noise."""

# Named so the refusal is a fact about the server rather than a sentence in a
# README. ``--tools`` prints it and check.py asserts none of them is exposed.
WITHHELD = ["create_sample", "edit_assay_result", "start_workflow", "delete_record"]

server = MCPServer("adaptive-registry", instructions=INSTRUCTIONS, **SERVER_KWARGS)


def _refuse(exc):
    """Hand the registry's own refusal to the caller, message intact.

    ``ToolError`` is the SDK's "a failure you anticipated" class: its text
    reaches the client, where a bare exception reaches it as "error executing
    tool". Every refusal in this file is deliberate -- a round already
    submitted, a construct that does not exist -- so every one of them says
    what it refused and why.
    """
    return ToolError(str(exc))


@server.tool()
def submit_batch(project: str, round: int) -> dict:
    """Submit a project's approved batch for a round and mint its identifiers.

    The registry mints a construct id per design and a sample id per well, lays
    them out on plates, and records the round. It returns only the external
    references; the workbench stores those links in designs.json and owns
    nothing about the samples themselves.

    A round cannot be submitted twice -- the registry does not overwrite assay
    data.

    Args:
        project: path to the project directory, e.g. projects/demo-trastuzumab
        round: the round number
    """
    try:
        r = lims.submit_project_batch(project, int(round))
    except (ValueError, KeyError) as exc:
        raise _refuse(exc) from exc
    return {
        "round_id": r["round_id"],
        "assay_version": r["assay_version"],
        "status": r["status"],
        "n_designs": r["n_designs"],
        "n_samples": r["n_samples"],
        "n_constructs_total": r["n_constructs"],
        "plates": r["plates"],
        "batch_approval": r["approval_status"],
        "external_refs_written_to": os.path.join(project, "designs.json"),
        "next": "pull_assay_results(project=%r, round_id=%r)" % (project, r["round_id"]),
        "note": "simulated assay; the values are generated, not measured",
    }


@server.tool()
def pull_assay_results(project: str, round_id: str, out: str = "") -> dict:
    """Export a round's assay rows and write them where import_round reads them.

    Rows come back the shape a real export has, not the shape the model would
    prefer: keyed by the registry's sample id and never the design id, with
    plate, well, assay version, replicate, unit and status as separate columns.
    Replicates are separate rows rather than pre-averaged, about 3% come back
    failed, and values below the detection limit come back censored rather than
    dropped. Reconciling that against the project's designs is import_round's
    job and it is deliberately real work.

    The CSV is written to a file rather than returned inline, because 96 rows
    of it is not something to read -- the summary is.

    Args:
        project: path to the project directory
        round_id: R4, or 4
        out: where to write the CSV; defaults to lims_store/exports/
    """
    path = out or lims.export_path_for(project, round_id)
    try:
        r = lims.pull_to_csv(round_id, project, out=path)
    except (KeyError, ValueError) as exc:
        raise _refuse(exc) from exc
    n = int(str(r["round_id"]).lstrip("R"))
    return {
        "round_id": r["round_id"],
        "assay_version": r["assay_version"],
        "n_rows": r["n_rows"],
        "status_counts": r["status_counts"],
        "columns": list(lims.COLUMNS),
        "path": os.path.relpath(path, REPO),
        "next": ("import_round.py --project %s --round %d --results %s"
                 % (project, n, os.path.relpath(path, REPO))),
    }


@server.tool()
def list_designs(project: str, limit: int = 25) -> dict:
    """Designs the registry holds, with the construct id it minted for each.

    Capped by default: the registry accumulates every design across every
    round, and the count is the useful part of the answer.

    Args:
        project: path to the project directory
        limit: how many records to return; 0 for all
    """
    rows = lims.Registry(lims.store_path_for(project)).list_designs()
    shown = rows if int(limit) <= 0 else rows[: int(limit)]
    return {"n_total": len(rows), "n_shown": len(shown), "designs": shown}


@server.tool()
def get_construct(project: str, construct_id: str) -> dict:
    """One construct record: its design id, sequence and registration time.

    Args:
        project: path to the project directory
        construct_id: e.g. CST00001
    """
    try:
        return lims.Registry(lims.store_path_for(project)).get_construct(construct_id)
    except KeyError as exc:
        raise _refuse(exc) from exc


@server.tool()
def attach_recommendation(project: str, batch_id: str, report_url: str) -> dict:
    """Attach a recommendation id and a link to an existing batch record.

    This is the entire write path and it is deliberately this small: a link on
    a record somebody else created. It creates nothing and edits no data.

    Args:
        project: path to the project directory
        batch_id: the batch the recommendation is about, e.g. batch_004
        report_url: a link to the decision record or report
    """
    reg = lims.Registry(lims.store_path_for(project))
    rec = reg.attach_recommendation(batch_id, report_url)
    return dict(rec, wrote=os.path.relpath(reg.store_path, REPO),
                note="a link on an existing record is the whole write path")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--tools" in argv:
        print("registry_server tools (the LIMS stand-in):")
        for name, doc in lims.TOOLS:
            print("  %-22s %s" % (name, doc))
        print("\nnot available, deliberately: %s." % ", ".join(WITHHELD))
        print("The write path attaches a link and nothing more.")
        return 0
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
