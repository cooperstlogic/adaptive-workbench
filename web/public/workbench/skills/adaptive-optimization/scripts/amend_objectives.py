#!/usr/bin/env python3
"""Apply the amendment a ruling authorized, and record what it superseded.

    python amend_objectives.py --project projects/demo-trastuzumab \
        --authority decision_005

Reads decisions/decision_NNN.json, writes objectives.json -- version bumped,
the superseded value kept in an ``amendments`` entry naming the ruling that
moved it.

**It takes no field and no value of its own.** Both come out of the decision
record: the agent proposed them, `record_decision.py` bounded them against
`core/amend.py` before writing them down, and a named person ruled. This
script re-validates against the project as it stands now and refuses if
anything has moved underneath the ruling, which is the same check
`import_round.py --authority` makes and for the same reason: **a change may
not cite a ruling that said something else.**

The authority has to exist, be ruled, be ruled `accepted` or
`accepted_with_modification`, and carry an amendment. An `accepted` ruling
applies the number the agent proposed; `accepted_with_modification` applies
the number the person typed, and the record keeps both.

What it does *not* do is re-enumerate or refit. An amendment to the editable
region moves the candidate pool, and a model run holds one prediction per
pool member in pool order, so the next batch cannot be selected until the
pool is regenerated and the round refitted against it. This script prints
which commands that takes rather than running them, because the round loop is
a sequence of scripts each writing one artifact and this is one of them.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from core import amend, project, schema  # noqa: E402

TERMINAL = ("accepted", "accepted_with_modification")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def authorized(state, authority):
    """The amendment a ruling authorized.

    -> (proposal, to, ruling), where ``proposal`` is the amendment block the
    record carries and ``to`` is the value to apply: the proposed one under
    `accepted`, the person's own under `accepted_with_modification`. Refuses
    anything the ruling did not say.
    """
    if not authority:
        raise amend.Refused("an amendment is applied under a ruling, so --authority names "
                            "the decision record that authorized it")
    dec = project.decision_by_id(state, authority)
    if dec is None:
        raise amend.Refused("no decision record %r in this project" % authority)
    if dec.get("status") != "ruled":
        raise amend.Refused("%s is %r. No action is taken on an unruled record"
                            % (authority, dec.get("status")))
    ruling = dec["ruling"]
    if ruling["verdict"] not in TERMINAL:
        raise amend.Refused("%s was ruled %r, which authorizes no amendment"
                            % (authority, ruling["verdict"]))
    proposed = (dec["recommendation"] or {}).get("amendment")
    if not proposed:
        raise amend.Refused("%s carries no amendment, so there is nothing here to apply. "
                            "Its recommendation is %r"
                            % (authority, dec["recommendation"].get("action")))
    modified = (ruling.get("modified") or {})
    if modified:
        if modified.get("field") != proposed["field"]:
            raise amend.Refused("%s proposed %s and its ruling modified %s. A ruling moves "
                                "the number, not the field"
                                % (authority, proposed["field"], modified.get("field")))
        return proposed, modified["to"], ruling
    return proposed, proposed["to"], ruling


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--authority", required=True, metavar="decision_NNN",
                    help="the ruled decision record that authorized the amendment")
    args = ap.parse_args(argv)

    state = project.load(args.project)
    at = _now()

    try:
        proposal, to, ruling = authorized(state, args.authority)
        field = proposal["field"]
        record, entry = amend.record(
            state, field, to, authority=args.authority, ruled_by=ruling["by"],
            why=proposal.get("why") or "", at=at, proposed=proposal["to"])
    except amend.Refused as why:
        print("refused: %s" % why, file=sys.stderr)
        return 2

    schema.write_json(state["paths"]["objectives"], record)

    rescored = 0
    if entry["effects"]["pool_changes"]:
        # The window moved, and a developability score is taken over the
        # window. Re-deriving the stored scores is exact arithmetic over
        # sequences the project already holds, not a re-measurement.
        state["objectives"] = record
        designs, rescored = amend.rescore_designs(state, at=at)
        schema.write_json(state["paths"]["designs"], designs)

    print("amended         %s" % amend.describe(field, entry["from"], entry["to"]))
    if entry.get("modified_by_ruling"):
        print("               the agent proposed %s; %s ruled %s"
              % (entry["proposed"], ruling["by"], entry["to"]))
    print("authority       %s, ruled %s by %s" % (args.authority, ruling["verdict"],
                                                  ruling["by"]))
    print("version         %d -> %d" % (entry["superseded_version"], record["version"]))
    print("superseded      %s = %s, kept in amendments[%d]"
          % (field, entry["from"], len(record["amendments"]) - 1))
    eff = entry["effects"]
    print("wells           %d of %d for fresh designs" % (eff["fresh_picks"],
                                                          record["batch"]["size"]))
    if eff["pool_changes"]:
        print("pool            %d feasible -> %d feasible"
              % (eff["feasible_before"], eff["feasible_after"]))
        print("rescored        %d designs under the amended window" % rescored)
        print("next            the pool moved, so the next batch needs, in order:")
        print("                  generate_candidates.py --round N+1")
        print("                  fit_surrogates.py --round N --pool N+1")
        print("                  select_batch.py --round N+1")
    else:
        print("pool            unchanged; the amendment spends the wells differently")
    print("wrote           %s" % os.path.relpath(state["paths"]["objectives"], args.project))
    return 0


if __name__ == "__main__":
    sys.exit(main())
