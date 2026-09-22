"""Amending the declaration a project runs under, with the bounds in code.

``objectives.json`` is the declaration: the thresholds, the mutation budget,
the editable region, the batch policy, the permitted recipes and diagnostics.
The round loop reads it and never writes it, which is what makes a batch a
function of its inputs rather than of what was in a context window.

Some of it should nevertheless be able to move. SKILL.md's diagnosis table
has said since the first round loop that the right answer to *the model
extrapolated into a region it has not seen* is "refit and widen exploration
next round" -- and nothing could widen anything, so the one action the table
named was the one action the system could not take.

This module is that action, and the shape of it is the point:

* **What can move is a fixed list**, declared here, with a low and a high
  bound on every entry. A field that is not in ``AMENDABLE`` is refused by
  name, and the refusal says what the amendable fields are. The thresholds,
  the permitted recipes, the permitted diagnostics and the anomaly trigger
  are all absent from it deliberately -- those are the pre-registration, and
  a trigger moved after a round has been seen is the failure mode this
  repository is most careful about.
* **The bound is enforced before anything runs**, here, in code. It is not
  advice in a prompt.
* **A number in an amendment is a decision, never a measurement.** It travels
  in the same channel as ``drop_wells``'s list of plates: a choice about what
  to do next, which a named person rules on, and which is inert until they
  do. No evidence number comes from here, and nothing here computes one.
* **The mutation budget is not amendable, and the reason is measured rather
  than argued.** Widening it from 2 to 3 over the demo project's
  eight-position window enumerates 394,365 candidates and leaves 261,649
  feasible: a 335 MB feature block and 2.2 GB of peak resident memory, about
  ten seconds on a laptop. The same `core/` runs in the browser under
  Pyodide, where that block is one WASM allocation and every candidate
  carries a stored prediction, so the budget stays what the template declared
  it. ``constraints.max_mutations`` is absent from ``AMENDABLE`` for that one
  reason and no other.
* **The cap that matters is the pool, not the parameter.** The editable region
  can widen, and widening it is what the budget's absence leaves available:
  two more positions costs 13,702 feasible candidates against the present
  7,294, which is the same order of work. Rather than bound the number of
  positions -- a guess about a pool size -- a region amendment is enumerated
  and checked against ``MAX_FEASIBLE_POOL``, and refused with the count it
  would have produced. One number bounds the thing that actually breaks.
* **An amendment may not orphan a design the project has already measured.**
  Narrowing the region under a measured design would leave the project
  holding evidence about a molecule its own declaration calls infeasible.
  That is refused, naming the design, which in practice is what keeps the
  window widening rather than sliding.

Nothing here does network I/O and nothing here prints.
"""

from . import candidates, encode, schema, scoring
from .acquisition import DIVERSITY_WEIGHT

# Fields the round loop reads with a default rather than requiring, so a
# project instantiated before they existed runs unchanged. An amendment still
# has to say what it moved *from*, and the effective value is what it moved
# from -- not null, which would read as though the knob had not been set.
DEFAULTS = {"batch.diversity_weight": DIVERSITY_WEIGHT}

# field path -> (kind, low, high). The path is dotted into objectives.json,
# except for the editable region's two ends, which are named separately
# because a person dialling one of them wants to type a number rather than a
# pair -- and because the two bounds are not the same bound.
AMENDABLE = {
    "batch.controls": ("int", 2, 4),
    "batch.replicates": ("int", 2, 8),
    # Generous on its own -- a third of the batch on pure uncertainty is a
    # legitimate "we are lost, go and map the space" round. What stops the
    # knobs from being wound up together is MIN_FRESH_PICKS, below, and not
    # this number: a bound says how far one may go, the floor says not all of
    # them at once.
    "batch.exploration_slots": ("int", 0, 16),
    "batch.diversity_weight": ("float", 0.0, 0.75),
    "editable_region.start": ("int", 0, 1000),
    "editable_region.end": ("int", 0, 1000),
}

# Which amendments change what the optimizer chooses *from* rather than how it
# spends the wells. These need the pool re-enumerated and the round refitted
# against it before the next batch can be selected, because a model run holds
# one prediction per pool member in pool order.
POOL_FIELDS = ("editable_region.start", "editable_region.end")

# The fields that can also be overridden for a single unapproved batch,
# without touching the declaration at all. Every field that only decides how
# the wells are spent qualifies; the two that move the pool do not, because
# re-enumerating it would leave the round's model run predicting over a
# different set of sequences than the batch is chosen from.
#
# **These are two different instruments and the difference is the point.** An
# amendment says the policy is wrong from here on and needs evidence and a
# ruling behind it. An override says *this* batch should have been composed
# differently, and it is checked by the thing that already gates a batch: the
# approval. Nothing has gone to the laboratory yet, so there is nothing to
# rule on, and the record keeps what moved beside who asked for it.
ROUND_SCOPED = tuple(f for f in AMENDABLE if f not in POOL_FIELDS)

# A batch that is all controls, replicates and exploration slots buys no new
# designs. Forty-eight wells minus twenty-four is the floor the demo project's
# policy sits well clear of, and it is what stops a widening amendment from
# quietly turning a design round into a calibration round.
MIN_FRESH_PICKS = 24

# The ceiling is the browser's, and it is stated as the number it is. The
# same `core/` runs under Pyodide, where the feature block is a single WASM
# allocation and a model run's per-candidate predictions are written into
# IDBFS; 40,000 feasible candidates is a 51 MB block and about 400 KB of
# predictions, which is roughly five times the demo project's pool and still
# comfortable. The mutation budget's 261,649 is not, which is why that field
# is a template declaration and not an amendable one.
MAX_FEASIBLE_POOL = 40_000


class Refused(Exception):
    """An amendment the declaration will not take. The message is the reason."""


def current(obj, field):
    """The value a dotted field has now, or its effective default."""
    if field.startswith("editable_region."):
        end = field.split(".", 1)[1]
        return obj["editable_region"][0 if end == "start" else 1]
    head, tail = field.split(".", 1)
    return obj[head].get(tail, DEFAULTS.get(field))


def _with(obj, field, value):
    """A copy of the objectives body with one field moved. Not stamped."""
    out = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in obj.items()}
    if field.startswith("editable_region."):
        end = field.split(".", 1)[1]
        region = list(out["editable_region"])
        region[0 if end == "start" else 1] = value
        out["editable_region"] = region
    else:
        head, tail = field.split(".", 1)
        out[head] = dict(out[head])
        out[head][tail] = value
    return out


def coerce(field, value):
    """The value as its declared kind, or a refusal. Bounds are not checked."""
    kind = AMENDABLE[field][0]
    try:
        return int(value) if kind == "int" else float(value)
    except (TypeError, ValueError):
        raise Refused("%s takes %s; %r is not one" % (field, "an integer" if kind == "int"
                                                      else "a number", value))


def _bounds_note(field):
    kind, low, high = AMENDABLE[field]
    fmt = "%d" if kind == "int" else "%.2f"
    return ("between " + fmt + " and " + fmt) % (low, high)


def _pool_effects(state, obj_after):
    """Enumerate under the amended declaration and say what it would cost.

    The enumeration is the expensive part of the check and it is done anyway,
    because a bound on a parameter is a guess about a pool size and a bound on
    a pool size is not.
    """
    parent = state["designs"]["parent"]
    before = state["objectives"]
    kept_before, _, _ = _enumerate(parent, before)
    kept_after, removed_after, summary = _enumerate(parent, obj_after)
    return {
        "feasible_before": len(kept_before),
        "feasible_after": len(kept_after),
        "enumerated_after": len(kept_after) + len(removed_after),
        "removed_after_by_reason": summary,
        "cap": MAX_FEASIBLE_POOL,
    }, kept_after


def _enumerate(parent, obj):
    pool = candidates.enumerate_variants(parent, obj["editable_region"],
                                         obj["constraints"]["max_mutations"])
    kept, removed = candidates.constraint_report(pool, parent, obj["editable_region"],
                                                 obj["objectives"], obj["constraints"])
    return kept, removed, candidates.removal_summary(removed)


def _orphans(state, obj_after):
    """Designs the project holds that the amended region would exclude.

    A measured design mutated outside the amended window is evidence about a
    molecule the declaration calls infeasible. There is no honest way to hold
    both, so the amendment is the thing that gives -- which in practice means
    the region widens and does not narrow, because 152 of the demo project's
    designs sit in the first position a narrowing would drop.
    """
    parent = state["designs"]["parent"]
    start, stop = obj_after["editable_region"][:2]
    out = []
    for d in state["designs"]["designs"]:
        seq = d["sequence"]
        if len(seq) != len(parent):
            out.append((d["design_id"], "a different length from the parent"))
            continue
        outside = [i for i in range(len(seq))
                   if seq[i] != parent[i] and not (start <= i < stop)]
        if outside:
            out.append((d["design_id"],
                        "mutated at %s, outside the amended region [%d, %d)"
                        % (", ".join(str(i) for i in outside), start, stop)))
    return out


def validate(state, field, to, *, where="the amendment"):
    """Check one proposed amendment against the declaration and the project.

    -> (from_value, to_value, effects). ``from`` is read off disk and is never
    taken from a payload, which is the same rule the decision writer applies
    to a diagnostic result wearing different clothes.
    """
    obj = state["objectives"]
    if field not in AMENDABLE:
        raise Refused("%s names %r, which is not amendable. The amendable fields are %s. "
                      "The thresholds, the permitted recipes, the permitted diagnostics and "
                      "the anomaly trigger are not among them: those are the "
                      "pre-registration, and moving one after a round has been read is not "
                      "an amendment a run gets to make"
                      % (where, field, ", ".join(sorted(AMENDABLE))))
    value = coerce(field, to)
    _kind, low, high = AMENDABLE[field]
    if not (low <= value <= high):
        raise Refused("%s puts %s at %s, and it is declared %s"
                      % (where, field, value, _bounds_note(field)))
    was = current(obj, field)
    if was == value:
        raise Refused("%s puts %s at %s, which is where it already is"
                      % (where, field, value))

    after = _with(obj, field, value)
    effects = {"pool_changes": field in POOL_FIELDS}

    batch = after["batch"]
    spent = (int(batch.get("controls", 0)) + int(batch.get("replicates", 0))
             + int(batch.get("exploration_slots", 0)))
    fresh = int(batch["size"]) - spent
    effects["fresh_picks"] = fresh
    if fresh < MIN_FRESH_PICKS:
        raise Refused("%s would leave %d of %d wells for fresh designs, and %d is the floor. "
                      "The well budget is the laboratory's and is not amendable here, so "
                      "widening one slot spends another"
                      % (where, fresh, batch["size"], MIN_FRESH_PICKS))

    if field in POOL_FIELDS:
        region = after["editable_region"]
        if not (0 <= region[0] < region[1] <= len(state["designs"]["parent"])):
            raise Refused("%s puts the editable region at %s, which is not a window inside a "
                          "sequence of %d residues"
                          % (where, list(region), len(state["designs"]["parent"])))
        orphans = _orphans(state, after)
        if orphans:
            did, why = orphans[0]
            raise Refused("%s would exclude %d design%s the project has already measured -- "
                          "%s %s. A declaration that calls its own evidence infeasible is "
                          "the amendment being wrong, not the evidence"
                          % (where, len(orphans), "" if len(orphans) == 1 else "s", did, why))
        pool, _kept = _pool_effects(state, after)
        effects.update(pool)
        if pool["feasible_after"] > MAX_FEASIBLE_POOL:
            raise Refused(
                "%s would enumerate %d candidates and leave %d feasible, against a cap of "
                "%d. The cap is the browser's: the same core/ runs under Pyodide, where the "
                "feature block is one allocation and every candidate carries a stored "
                "prediction. Widen the region by fewer positions"
                % (where, pool["enumerated_after"], pool["feasible_after"],
                   MAX_FEASIBLE_POOL))

    return was, value, effects


def _show(value):
    return ("%.2f" % value) if isinstance(value, float) else str(value)


def describe(field, was, to):
    """One line naming what moves, for a log label and a button."""
    return "%s %s -> %s" % (field, _show(was), _show(to))


def record(state, field, to, *, authority, ruled_by, why, at, proposed=None):
    """The amended objectives record: version bumped, the old value kept.

    The superseded value stays in ``amendments`` beside the ruling that moved
    it. That is the same convention ``data/landscape_manifest.json`` uses for
    the one landscape parameter this build moved after seeing results, and for
    the same reason: a parameter that moved is only checkable if what it moved
    from is still written down.
    """
    obj = state["objectives"]
    was, value, effects = validate(state, field, to)
    after = _with(obj, field, value)
    entry = {
        "field": field,
        "from": was,
        "to": value,
        "why": why,
        "authority": authority,
        "ruled_by": ruled_by,
        "at": at,
        "effects": effects,
        "superseded_version": int(obj.get("version", 1)),
    }
    if proposed is not None and proposed != value:
        # The agent asked for one number and the person who ruled wrote
        # another. Both belong in the record; the applied one is ``to``.
        entry["proposed"] = proposed
        entry["modified_by_ruling"] = True
    after["version"] = int(obj.get("version", 1)) + 1
    after["amendments"] = list(obj.get("amendments") or []) + [entry]
    after["amended"] = at
    body = {k: v for k, v in after.items() if k not in ("hash",)}
    return schema.stamp(body), entry


def rescore_designs(state, at=None):
    """Recompute every design's computed properties under the current region.

    Only an amendment to the editable region needs this, and it needs it
    because a developability score is a function of the window it is taken
    over. Leaving the stored values alone would put two definitions of
    hydrophobicity in one project and mix them inside a single batch record.
    The scores are exact, so re-deriving them is not a re-measurement.
    """
    designs = state["designs"]
    parent, region = designs["parent"], state["objectives"]["editable_region"]
    changed = 0
    records = []
    for d in designs["designs"]:
        sc = scoring.score(d["sequence"], parent, region)
        computed = {"hydrophobicity": sc["hydrophobicity"], "net_charge": sc["net_charge"],
                    "liability_count": sc["liability_count"]}
        rec = dict(d, computed=computed,
                   mutations=encode.mutation_labels(parent, d["sequence"], region),
                   n_mutations=encode.n_mutations(parent, d["sequence"], region))
        if rec != d:
            changed += 1
        records.append(rec)
    body = {k: v for k, v in designs.items() if k != "hash"}
    body["designs"] = records
    if at is not None:
        body["rescored"] = at
    return schema.stamp(body), changed


def plan_overrides(objectives, pairs):
    """Validate policy overrides for one batch, without touching the declaration.

    ``pairs`` is a sequence of (field, value). The bounds are the same ones an
    amendment is held to -- one list, in one place, so a knob cannot be wound
    further for one round than it could be wound permanently. The wells floor
    is checked once at the end, against all of them together.

    -> (effective batch policy, [{field, from, to}]). The caller writes both
    into the batch record: the policy because it is what the batch was
    actually composed under, and the list because it is what the declaration
    said instead.
    """
    policy = dict(objectives["batch"])
    moved, seen = [], set()
    for field, raw in pairs:
        if field in POOL_FIELDS:
            raise Refused(
                "%s moves the candidate pool, so it cannot be set for one batch: the "
                "round's model run holds one prediction per pool member, and re-enumerating "
                "underneath it would index every prediction against the wrong sequence. It "
                "goes through an amendment on a decision record instead" % field)
        if field not in ROUND_SCOPED:
            raise Refused("%r is not something a batch can be re-composed on. The fields "
                          "that are: %s" % (field, ", ".join(sorted(ROUND_SCOPED))))
        if field in seen:
            raise Refused("%s was given twice" % field)
        seen.add(field)
        value = coerce(field, raw)
        _kind, low, high = AMENDABLE[field]
        if not (low <= value <= high):
            raise Refused("%s at %s is out of range; it is declared %s"
                          % (field, value, _bounds_note(field)))
        was = current(objectives, field)
        if was == value:
            raise Refused("%s is already %s" % (field, value))
        moved.append({"field": field, "from": was, "to": value})
        policy[field.split(".", 1)[1]] = value

    spent = (int(policy.get("controls", 0)) + int(policy.get("replicates", 0))
             + int(policy.get("exploration_slots", 0)))
    fresh = int(policy["size"]) - spent
    if fresh < MIN_FRESH_PICKS:
        raise Refused("that would leave %d of %d wells for fresh designs, and %d is the "
                      "floor. The well budget is the laboratory's, so spending more on one "
                      "slot spends less on another"
                      % (fresh, policy["size"], MIN_FRESH_PICKS))
    return policy, moved
