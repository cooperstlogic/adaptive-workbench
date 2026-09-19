"""Scoring candidates and composing a batch.

The hard thresholds are already gone by the time anything here runs:
``generate_candidates`` removed every candidate that failed one and reported
the count and the reason. What survives is scored by expected improvement on
affinity, then selected greedily with a diversity penalty on sequence
distance to members already chosen, breaking ties toward the better
developability margin.

Developability never enters the acquisition itself. Those scores are exact,
so the probability of satisfying one is zero or one, and multiplying that in
would be theatre.
"""

import numpy as np

from . import encode, scoring
from .surrogate import norm_cdf, norm_pdf

DIVERSITY_WEIGHT = 0.25
EXTRAPOLATION_PERCENTILE = 90.0


def expected_improvement(mean, sd, incumbent, xi=0.0):
    """Standard EI against the best value observed so far.

    The incumbent is the best *observed* value, not the best predicted one:
    it is the number on the scientist's slide, and improving on a model's
    opinion of a design nobody measured is not an improvement anyone can bank.
    """
    mean = np.asarray(mean, dtype=np.float64)
    sd = np.maximum(np.asarray(sd, dtype=np.float64), 1e-9)
    gap = mean - float(incumbent) - float(xi)
    z = gap / sd
    return gap * norm_cdf(z) + sd * norm_pdf(z)


def extrapolation_threshold(sd, percentile=EXTRAPOLATION_PERCENTILE):
    """Above this predictive sd a design is flagged as an extrapolation.

    Defined against the pool the model was asked about rather than an absolute
    number in pKD, so the flag keeps meaning 'among the least-certain designs
    here' as the model gets better.
    """
    return float(np.percentile(np.asarray(sd, dtype=np.float64), percentile))


def greedy_diverse(scores, X, k, region_length, already=(), weight=DIVERSITY_WEIGHT,
                   available=None, tiebreak=None):
    """Greedy max of (normalized score) minus (diversity penalty).

    Scores are normalized to their own maximum first, so the weight means the
    same thing whether expected improvement is in the hundredths or the
    tenths, and the ranking of the score alone is untouched by the transform.

    -> list of row indices into ``X``.
    """
    scores = np.asarray(scores, dtype=np.float64)
    n = scores.shape[0]
    mask = np.zeros(n, dtype=bool)
    mask[np.asarray(available, dtype=np.int64)] = True if available is not None else False
    if available is None:
        mask[:] = True

    top = float(scores.max()) if n else 0.0
    unit = scores / top if top > 0 else np.zeros(n)
    tb = np.zeros(n) if tiebreak is None else np.asarray(tiebreak, dtype=np.float64)
    tb_scale = 1e-6 * (1.0 / max(float(np.max(np.abs(tb))), 1.0))

    L = float(region_length)
    dmin = np.full(n, L)
    for idx in already:
        dmin = np.minimum(dmin, L - X @ X[idx])

    chosen = []
    for _ in range(int(k)):
        penalty = weight * (1.0 - dmin / L)
        adjusted = unit - penalty + tb_scale * tb
        adjusted[~mask] = -np.inf
        pick = int(np.argmax(adjusted))
        if not np.isfinite(adjusted[pick]):
            break
        chosen.append(pick)
        mask[pick] = False
        dmin = np.minimum(dmin, L - X @ X[pick])
    return chosen


def developability_margins(sequences, parent, editable_region, objectives):
    return np.array([
        scoring.developability_margin(scoring.score(s, parent, editable_region), objectives)
        for s in sequences
    ], dtype=np.float64)


def _slot(sequence, kind, rationale, **extra):
    rec = {"sequence": sequence, "slot": kind, "rationale": rationale}
    rec.update(extra)
    return rec


def compose_batch(features, policy, *, parent, observed, previous_batch, mean=None, sd=None,
                  incumbent=None, objectives=(), mode="guided", rng=None,
                  diversity_weight=DIVERSITY_WEIGHT):
    """Build one batch: controls, replicates, exploration slots, fresh picks.

    Batch size is inclusive. A batch of 48 is 42 fresh picks plus the six
    control, replicate and exploration slots, so the number of wells is the
    number the scientist set, and the random arm spends the same budget the
    same way.

    The first four re-measured slots are also the bridging set the round-to-
    round offset is estimated from, which is why they exist at all -- an
    offset you cannot estimate is one you merely suffer.
    """
    pool = features.pool
    X = features.X
    L = encode.region_length(features.editable_region)
    size = int(policy["size"])
    n_controls = int(policy.get("controls", 2))
    n_replicates = int(policy.get("replicates", 2))
    n_exploration = int(policy.get("exploration_slots", 2)) if mode == "guided" else 0

    measured = set(observed)
    taken, slots = set(), []

    def take(seq, kind, rationale, bridge=False, **extra):
        if seq is None or seq in taken or seq not in features.index:
            return False
        taken.add(seq)
        slots.append(_slot(seq, kind, rationale, bridge=bool(bridge), **extra))
        return True

    # Controls: the parent, then the best design measured so far.
    #
    # Only the parent anchors the bridge. The best-so-far design is re-run
    # because confirming your top hit is what a lab does, but it was chosen
    # for reading high, so it will read lower next time whatever the assay
    # did. A design selected for being extreme measures regression to the
    # mean, not a run offset, so it is deliberately excluded from the bridge.
    take(parent, "control", "parent, carried in every round as the anchor of the bridging set",
         bridge=True)
    # Sorted on the value and then on the sequence. ``measured`` is a set of
    # strings, whose iteration order is salted per process, so a tie on the
    # value alone -- which censored designs, all sitting exactly at the
    # detection limit, are guaranteed to produce -- would pick a different
    # control on a different run of the same project.
    ranked = sorted((s for s in measured if s != parent),
                    key=lambda s: (-float(observed[s]["value"]), s))
    for seq in ranked:
        if sum(1 for s in slots if s["slot"] == "control") >= n_controls:
            break
        take(seq, "control",
             "best design measured so far, re-run to confirm it; excluded from the bridge "
             "because it was selected for reading high", bridge=False)

    # Replicates: designs spanning the previous batch's observed range rather
    # than its top. Spanning is what makes the mean shift an estimate of the
    # run offset instead of an estimate of how lucky the top hits were.
    prev_ranked = sorted((s for s in (previous_batch or []) if s in measured and s not in taken),
                         key=lambda s: (float(observed[s]["value"]), s))
    if prev_ranked and n_replicates:
        m = len(prev_ranked)
        wanted = [prev_ranked[min(m - 1, int((i + 0.5) / n_replicates * m))]
                  for i in range(n_replicates)]
        for seq in dict.fromkeys(wanted):
            take(seq, "replicate",
                 "re-run from the previous batch, chosen to span its range so the "
                 "round-to-round offset is estimable without regression to the mean",
                 bridge=True)

    fresh_mask = np.array([s not in measured and s not in taken for s in pool])
    fresh_idx = np.flatnonzero(fresh_mask)

    extrap_cut = None
    if mean is not None and sd is not None:
        extrap_cut = extrapolation_threshold(sd)

    margins = None
    if sd is not None or mode == "guided":
        margins = developability_margins(pool, parent, features.editable_region, objectives)

    # Exploration: deliberately the least certain designs available. This is
    # the visible difference between exploiting and gathering information.
    #
    # The tie is not a corner case, it is the normal case. Under a one-hot
    # ridge model every double mutant at a pair of positions the model has not
    # seen jointly carries the *same* predictive variance, so the top of this
    # ranking is dozens of designs at bit-identical sd. numpy's default sort is
    # quicksort and is not stable, so ranking on sd alone picks a different
    # pair on a different numpy build -- and a batch that cannot be reproduced
    # in the browser from the same snapshot breaks the lineage claim the whole
    # demo rests on. So the tie is broken on a stated reason, the better
    # developability margin, and then on pool order, which is deterministic.
    if n_exploration and sd is not None:
        rank = np.lexsort((fresh_idx, -margins[fresh_idx], -sd[fresh_idx]))
        for pos in fresh_idx[rank][: n_exploration * 4]:
            if sum(1 for s in slots if s["slot"] == "exploration") >= n_exploration:
                break
            take(pool[int(pos)], "exploration",
                 "highest predictive uncertainty in the pool, taken to inform the model rather than to win",
                 bridge=False)

    remaining = size - len(slots)
    fresh_mask = np.array([s not in measured and s not in taken for s in pool])
    fresh_idx = np.flatnonzero(fresh_mask)

    if remaining > 0:
        if mode == "random":
            rng = rng or np.random.default_rng(0)
            pick = rng.choice(fresh_idx, size=min(remaining, fresh_idx.size), replace=False)
            for pos in pick:
                take(pool[int(pos)], "pick", "drawn uniformly at random from the feasible pool",
                     bridge=False)
        else:
            ei = expected_improvement(mean, sd, incumbent)
            order = greedy_diverse(
                ei, X, remaining, L,
                already=[features.index[s] for s in taken],
                weight=diversity_weight, available=fresh_idx, tiebreak=margins,
            )
            for rank, pos in enumerate(order, 1):
                take(pool[pos], "pick",
                     "expected improvement rank %d, selected against a diversity penalty" % rank,
                     bridge=False)

    # Annotate every slot with what the model thought of it.
    for rec in slots:
        i = features.index[rec["sequence"]]
        if mean is not None:
            rec["pred_mean"] = float(mean[i])
            rec["pred_sd"] = float(sd[i])
            rec["expected_improvement"] = float(expected_improvement(mean[i], sd[i], incumbent))
            rec["extrapolation"] = bool(sd[i] > extrap_cut) if extrap_cut is not None else False
        rec["n_mutations"] = encode.n_mutations(parent, rec["sequence"], features.editable_region)
        rec["previously_measured"] = rec["sequence"] in measured

    return {
        "slots": slots,
        "sequences": [s["sequence"] for s in slots],
        "size": len(slots),
        "requested_size": size,
        "mode": mode,
        "composition": {k: sum(1 for s in slots if s["slot"] == k)
                        for k in ("control", "replicate", "exploration", "pick")},
        "bridge": [s["sequence"] for s in slots if s["bridge"]],
        "re_measured": [s["sequence"] for s in slots if s["previously_measured"]],
        "fresh": [s["sequence"] for s in slots if not s["previously_measured"]],
        "diversity_weight": float(diversity_weight),
        "incumbent": None if incumbent is None else float(incumbent),
        "extrapolation_cut_sd": extrap_cut,
        "min_pairwise_distance": None,
    }


def assign_plates(sequences, round_id, per_plate=24):
    """Lay a batch out across plates.

    Two plates of twenty-four rather than one of forty-eight, because a single
    plate makes the per-plate effect indistinguishable from the per-round one
    and turns the plate diagnostic into a formality. The registry owns this in
    the product; the campaign calls it directly.
    """
    return ["R%dP%d" % (int(round_id), i // int(per_plate) + 1) for i in range(len(sequences))]
