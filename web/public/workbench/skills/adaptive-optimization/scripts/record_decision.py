#!/usr/bin/env python3
"""Write a judgment call, its evidence and its ruling into the project.

    # the agent proposes
    python record_decision.py --project projects/demo-trastuzumab --round 4 \
        --propose diagnosis.json

    # a named human rules
    python record_decision.py --project projects/demo-trastuzumab --round 4 \
        --rule accepted --by d.webster --note "agreed"

    # or pushes the work back
    python record_decision.py --project projects/demo-trastuzumab --round 4 \
        --rule more_evidence_requested --by d.webster \
        --request calibration_by_region --note "show me the offset does not fix coverage"

    # or accepts the diagnosis and dials the number it asked for
    python record_decision.py --project projects/demo-trastuzumab --round 5 \
        --rule accepted_with_modification --by d.webster --amend-to 4 \
        --note "four exploration slots, not six; keep the fresh picks above forty"

Writes decisions/decision_NNN.json and links it into rounds.json.

**It adds no arithmetic of its own, and it accepts none.** A proposal names
which test supports which hypothesis; this script runs that test itself,
through `core.diagnostics.run`, and writes the numbers it got back. A payload
that carries its own ``result`` is refused rather than trusted, because there
is then no channel through which a number that no reviewer can reproduce can
reach a decision record. The one exception is the ``ad_hoc`` list, which is
model-written analysis, is stored with its source inlined, is labelled
one-off and unversioned, and is never an input to a code path.

A recommendation may also carry an **amendment**: one field of
``objectives.json`` the agent is asking to move, and the value it is asking
for. The field has to be one `core.amend` declares amendable and the value
has to sit inside the bounds declared beside it, both checked here before
anything is written. What the field is *now*, and what the change would cost
the candidate pool, are read off the project rather than taken from the
payload. Nothing is applied: `amend_objectives.py --authority` does that,
after a ruling, and an `accepted_with_modification` ruling may dial the number
with ``--amend-to``.

Five things it refuses outright, because each is a rule that is worth more
enforced than suggested:

* a hypothesis naming a test the template does not permit
* a recommendation to correct the frame with no concordant bridge behind it
* a recommendation with an empty ``if_wrong``
* a second pass that ignores the test the ruling asked for
* an amendment naming a field that is not amendable, a value outside its
  declared bounds, or one that would leave the batch too few fresh designs

The four ruling verbs are `accepted`, `accepted_with_modification`,
`rejected`, and `more_evidence_requested`, which names a test and hands the
work back. A record carries every pass it went through, so the push-back and
what it changed stay readable afterwards.
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from core import amend, diagnostics, project, schema  # noqa: E402

ACTIONS = ("apply_offset_correction", "drop_wells", "refit_only", "no_action")
CONFIDENCE = ("high", "medium", "low", "refuses")
VERDICTS = ("accepted", "accepted_with_modification", "rejected", "more_evidence_requested")
READINGS = ("supported", "partially supported", "not supported", "inconclusive")
TERMINAL = ("accepted", "accepted_with_modification", "rejected")


class Refused(Exception):
    """A payload the record will not carry. The message is the reason."""


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _text(payload, key, where):
    value = (payload.get(key) or "").strip()
    if not value:
        raise Refused("%s needs a non-empty %r" % (where, key))
    return value


def evidence(state, round_id, snap, batch, prior_run, hypotheses, permitted, policy):
    """Turn claims naming tests into claims carrying results.

    The agent's contribution is the claim, the choice of test and the reading.
    The numbers between them come from here.
    """
    designs = project.designs_by_id(state)
    out = []
    for i, h in enumerate(hypotheses):
        where = "hypothesis %d" % (i + 1)
        if "result" in h:
            raise Refused(
                "%s supplied its own %r. Results come from the diagnostic, not from the "
                "payload -- name the test and this script runs it" % (where, "result"))
        test = h.get("diagnostic")
        if test not in permitted:
            raise Refused("%s names %r, which this template does not permit. The permitted "
                          "tests are %s" % (where, test, ", ".join(permitted)))
        args = dict(h.get("args") or {})
        args["test"] = test
        result = diagnostics.run(test, snap, batch, designs, policy=policy, args=args)
        reading = _text(h, "reading", where)
        if reading not in READINGS:
            raise Refused("%s reads %r; a reading is one of %s"
                          % (where, reading, ", ".join(READINGS)))
        out.append({
            "id": h.get("id") or "h%d" % (i + 1),
            "claim": _text(h, "claim", where),
            "diagnostic": test,
            "args": {k: v for k, v in args.items() if k != "test"},
            "source": "core.diagnostics.%s" % test,
            "result": result,
            "reading": reading,
            "reasoning": (h.get("reasoning") or "").strip() or None,
            "inputs": {"snapshot": snap["hash"], "batch": batch["hash"],
                       "model_run": None if prior_run is None else prior_run["hash"]},
        })
    return out


def amendment(state, rec):
    """Validate a proposed amendment to the declaration, or return None.

    The payload names a field and a value and says why. Everything else in
    the stored block -- what the field is now, the bounds it was checked
    against, and what the change would cost the candidate pool -- is computed
    here by `core.amend`, off the project on disk. A payload carrying its own
    ``from`` or ``effects`` is refused for the same reason one carrying its
    own ``result`` is: there is no channel for a number nobody can reproduce.

    The value itself the agent does supply, and that is deliberate. It is a
    choice about what to do next rather than a measurement -- the same channel
    ``drop_wells`` names a plate in -- it is bounded here in code before it is
    written down, and it changes nothing until a named person rules on it.
    """
    block = rec.get("amendment")
    if not block:
        return None
    if not isinstance(block, dict):
        raise Refused("amendment is an object naming a field, a value and why")
    for key in ("from", "effects", "bounds"):
        if key in block:
            raise Refused("the amendment supplied its own %r. Name the field and the value "
                          "you want; this script reads what it is now off the project and "
                          "computes what the change would cost" % key)
    if rec.get("confidence") == "refuses":
        raise Refused("a refusal recommends no_action and amends nothing. An amendment is a "
                      "change you are asking for, not a change you are declining to make")
    field, to = block.get("field"), block.get("to")
    was, value, effects = amend.validate(state, field, to, where="the amendment")
    kind, low, high = amend.AMENDABLE[field]
    return {
        "field": field,
        "from": was,
        "to": value,
        "why": _text(block, "why", "the amendment"),
        "bounds": {"kind": kind, "low": low, "high": high},
        "effects": effects,
        "source": "core.amend.validate",
        "note": "a decision parameter, bounded in code and inert until a named person "
                "rules; applied by amend_objectives.py --authority, never from here",
    }


def recommendation(state, payload, hypotheses):
    """Validate the recommendation against the evidence just computed."""
    rec = payload.get("recommendation") or {}
    action = rec.get("action")
    if action not in ACTIONS:
        raise Refused("action is %r; the enumerated actions are %s"
                      % (action, ", ".join(ACTIONS)))
    confidence = rec.get("confidence")
    if confidence not in CONFIDENCE:
        raise Refused("confidence is %r; it is one of %s" % (confidence, ", ".join(CONFIDENCE)))
    if confidence == "refuses" and action != "no_action":
        raise Refused("a refusal recommends no_action, not %r" % action)

    if action == "apply_offset_correction":
        bridge = [h for h in hypotheses if h["diagnostic"] == "offset_from_controls"]
        if not bridge:
            raise Refused("correcting the frame means having run offset_from_controls, and "
                          "no hypothesis did")
        result = bridge[-1]["result"]
        if not result.get("n_bridge"):
            raise Refused("correcting the frame with no bridge is pooling across an assay "
                          "version on nothing. The correct output is no_action with "
                          "confidence 'refuses'")
        if result.get("concordant") is not True:
            raise Refused(
                "the bridge members do not agree (spread sd %s against a tolerance of %s), "
                "so there is no single number to correct by. The correct output is no_action "
                "with confidence 'refuses'"
                % (result.get("delta_sd"), result.get("concordance_tolerance")))

    out = {
        "action": action,
        "confidence": confidence,
        "parameters": rec.get("parameters") or {},
        "rationale": _text(rec, "rationale", "recommendation"),
        "alternative_considered": _text(rec, "alternative_considered", "recommendation"),
        "if_wrong": _text(rec, "if_wrong", "recommendation"),
    }
    # What to do with this round's data and how to spend the next round's
    # wells are independent decisions, so the amendment is a field beside the
    # action rather than a fifth value of it: a round can both take an offset
    # correction and widen exploration, and one ruling covers both.
    amended = amendment(state, rec)
    if amended is not None:
        out["amendment"] = amended
    return out


def ad_hoc(payload):
    """Model-written analysis, passed through and labelled as what it is."""
    out = []
    for i, item in enumerate(payload.get("ad_hoc") or []):
        where = "ad_hoc %d" % (i + 1)
        out.append({
            "question": _text(item, "question", where),
            "code": _text(item, "code", where),
            "stdout": (item.get("stdout") or "").strip(),
            "note": "one-off, unversioned; evidence a human reads, never an input to a "
                    "code path",
        })
    return out


def propose(state, round_id, payload, existing):
    """Add a pass: hypotheses with their results, and a recommendation."""
    obj = state["objectives"]
    snap = project.read_artifact(state, "evidence", round_id)
    batch = project.read_artifact(state, "batches", round_id)
    if snap is None or batch is None:
        raise Refused("round %d needs both a batch and a snapshot before it can be ruled on"
                      % round_id)
    prior_run = project.read_artifact(state, "models", round_id - 1)

    passes = list((existing or {}).get("passes", []))
    if passes and passes[-1].get("ruling") is None:
        raise Refused("pass %d of this record is already open and unruled. A second "
                      "recommendation before the first is ruled on would leave two live "
                      "answers to one question" % len(passes))
    if existing and existing.get("status") == "ruled":
        raise Refused("this round has been ruled %r and the record is closed"
                      % existing["ruling"]["verdict"])

    requested = None
    if passes:
        requested = (passes[-1]["ruling"].get("requested") or {}).get("diagnostic")

    hypotheses = evidence(state, round_id, snap, batch, prior_run,
                          payload.get("hypotheses") or [], obj["diagnostics"],
                          obj.get("diagnostics_policy"))
    if not hypotheses:
        raise Refused("a proposal states at least one hypothesis and the test it rests on")
    if requested and requested not in {h["diagnostic"] for h in hypotheses}:
        raise Refused("the ruling asked for %s and this pass does not run it. Answering a "
                      "push-back means running what was asked for" % requested)

    return {
        "pass": len(passes) + 1,
        "at": _now(),
        "answering": requested,
        "hypotheses": hypotheses,
        "ad_hoc": ad_hoc(payload),
        "recommendation": recommendation(state, payload, hypotheses),
        "ruling": None,
    }, snap, batch, prior_run


def rule(state, existing, verdict, by, note, request, permitted, amend_to=None):
    """Attach a ruling to the open pass."""
    if not existing or not existing.get("passes"):
        raise Refused("there is nothing to rule on: no recommendation has been recorded")
    pass_ = existing["passes"][-1]
    if pass_.get("ruling") is not None:
        raise Refused("pass %d was already ruled %r"
                      % (pass_["pass"], pass_["ruling"]["verdict"]))
    if verdict not in VERDICTS:
        raise Refused("verdict is %r; the four verbs are %s" % (verdict, ", ".join(VERDICTS)))
    if not (by or "").strip():
        raise Refused("a ruling carries the name of whoever made it")
    note = (note or "").strip()
    if verdict == "rejected" and not note:
        raise Refused("rejecting takes a reason; --note is what the agent works from next")
    if verdict == "accepted_with_modification" and not note:
        raise Refused("--note says what the modification is, or the record does not record "
                      "the decision that was actually taken")

    ruling = {"verdict": verdict, "by": by.strip(), "at": _now(), "note": note,
              "requested": None}

    # A recommendation that carries an amendment carries a number, and the
    # person ruling on it gets to move that number rather than only take it or
    # leave it. The modified value is re-validated here against the same
    # bounds the proposal was, so the human's hand does not reach past a check
    # the agent's did -- and both numbers stay in the record.
    proposed = (existing["recommendation"] or {}).get("amendment")
    if amend_to is not None:
        if verdict != "accepted_with_modification":
            raise Refused("--amend-to belongs to accepted_with_modification, not to %r. "
                          "Accepting takes the number the recommendation proposed" % verdict)
        if not proposed:
            raise Refused("--amend-to modifies an amendment and this recommendation does "
                          "not propose one")
        field = proposed["field"]
        was, value, effects = amend.validate(state, field, amend_to, where="--amend-to")
        if value == proposed["to"]:
            raise Refused("--amend-to is %s, which is what the recommendation already "
                          "proposes. Accept it instead" % value)
        ruling["modified"] = {"field": field, "from": was, "proposed": proposed["to"],
                              "to": value, "effects": effects,
                              "source": "core.amend.validate"}
    # No ``modified`` block means the number was not modified, whatever else
    # the note says changed, and that is what the applier reads. The absence
    # is the statement, so there is no third state to misread.

    if verdict == "more_evidence_requested":
        if request not in permitted:
            raise Refused("--request names a test the template permits: %s"
                          % ", ".join(permitted))
        ruling["requested"] = {"diagnostic": request, "reason": note or None}
    elif request:
        raise Refused("--request belongs to more_evidence_requested, not to %r" % verdict)
    return ruling


def assemble(state, round_id, trigger, passes):
    """The record: every pass it went through, with the latest surfaced."""
    latest = passes[-1]
    ruling = latest["ruling"]
    terminal = bool(ruling and ruling["verdict"] in TERMINAL)
    status = ("ruled" if terminal else
              "awaiting_evidence" if ruling else "open")
    inputs = latest["hypotheses"][0]["inputs"]
    return schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "id": project.decision_id(round_id),
        "round": int(round_id),
        "trigger": trigger,
        "status": status,
        "passes": passes,
        "n_passes": len(passes),
        "hypotheses": latest["hypotheses"],
        "ad_hoc": latest["ad_hoc"],
        "recommendation": latest["recommendation"],
        "ruling": ruling,
        "mirrors_note": "hypotheses, ad_hoc, recommendation and ruling mirror the last pass; "
                        "passes holds every one of them in order",
        "provenance_note": "every number under result came from the named core/ function, "
                           "re-run by record_decision.py against the hashed inputs below. "
                           "Nothing in ad_hoc did, and it is labelled accordingly",
    }, inputs=inputs)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--propose", metavar="PAYLOAD.json",
                    help="a diagnosis to record; '-' reads stdin")
    ap.add_argument("--rule", choices=VERDICTS, help="rule on the open recommendation")
    ap.add_argument("--by", default=None, help="who is ruling")
    ap.add_argument("--note", default="", help="the reason, the modification, or the ask")
    ap.add_argument("--request", default=None,
                    help="more_evidence_requested: the test to go and run")
    ap.add_argument("--amend-to", default=None, metavar="VALUE",
                    help="accepted_with_modification: the value to apply instead of the "
                         "one the recommendation's amendment proposed")
    args = ap.parse_args(argv)

    if bool(args.propose) == bool(args.rule):
        print("one of --propose or --rule, not both and not neither", file=sys.stderr)
        return 2

    state = project.load(args.project)
    obj = state["objectives"]
    existing = project.read_decision(state, args.round)

    try:
        if args.propose:
            raw = sys.stdin.read() if args.propose == "-" else open(args.propose).read()
            payload = json.loads(raw)
            new_pass, snap, _batch, _run = propose(state, args.round, payload, existing)
            passes = list((existing or {}).get("passes", [])) + [new_pass]
            trigger = ((existing or {}).get("trigger")
                       or (payload.get("trigger") or "").strip()
                       or default_trigger(snap))
        else:
            ruling = rule(state, existing, args.rule, args.by, args.note, args.request,
                          obj["diagnostics"], amend_to=args.amend_to)
            passes = list(existing["passes"])
            passes[-1] = dict(passes[-1], ruling=ruling)
            trigger = existing["trigger"]
    # `core.amend` has a refusal of its own, raised out of the bounds check on
    # an amendment. It means exactly what this one means and is reported the
    # same way: a reason on stderr, not a traceback the model has to read
    # around.
    except (Refused, amend.Refused) as why:
        print("refused: %s" % why, file=sys.stderr)
        return 2

    record = assemble(state, args.round, trigger, passes)
    path = project.artifact_path(state, "decisions", args.round)
    schema.write_json(path, record)
    project.link_round(state, args.round,
                       decision=project.artifact_ref(state["paths"]["root"], path, record),
                       decision_status=record["status"])

    report(record, args.round)
    print("wrote           %s" % os.path.relpath(path, args.project))
    return 0


def default_trigger(snap):
    flag = snap.get("anomaly") or {}
    if not flag:
        return "round %d was recorded for a decision" % snap["round"]
    return ("%d fresh designs came back a mean %+.3f %s from the model's prediction, against "
            "a trigger of %.2f" % (flag["n_compared"], flag["mean_signed_residual"],
                                   snap["unit"], flag["trigger_abs_pkd"]))


def report(record, round_id):
    latest = record["passes"][-1]
    print("decision        %s  round %d  pass %d of %d  status %s"
          % (record["id"], round_id, latest["pass"], record["n_passes"], record["status"]))
    print("trigger         %s" % record["trigger"])
    for h in latest["hypotheses"]:
        print("  %-3s %-22s %-18s %s"
              % (h["id"], h["diagnostic"], h["reading"], h["claim"][:60]))
    for a in latest["ad_hoc"]:
        print("  ad hoc  %s  (one-off, unversioned)" % a["question"][:60])
    rec = latest["recommendation"]
    print("recommends      %s, confidence %s" % (rec["action"], rec["confidence"]))
    am = rec.get("amendment")
    if am:
        print("amends          %s  (%s, declared %s to %s)"
              % (amend.describe(am["field"], am["from"], am["to"]),
                 "the pool moves" if am["effects"]["pool_changes"] else "the wells re-spend",
                 am["bounds"]["low"], am["bounds"]["high"]))
    print("if wrong        %s" % rec["if_wrong"])
    ruling = latest["ruling"]
    if ruling is None:
        print("ruling          none yet. No action is taken on an unruled record")
    else:
        print("ruling          %s by %s%s"
              % (ruling["verdict"], ruling["by"],
                 "" if not ruling["note"] else " -- %s" % ruling["note"]))
        if ruling["requested"]:
            print("                go and run %s" % ruling["requested"]["diagnostic"])
        mod = ruling.get("modified")
        if mod:
            print("                %s dialled %s from %s to %s"
                  % (ruling["by"], mod["field"], mod["proposed"], mod["to"]))
        elif am:
            print("                the amendment applies as proposed: %s"
                  % amend.describe(am["field"], am["from"], am["to"]))


if __name__ == "__main__":
    sys.exit(main())
