"""Candidate enumeration, hard-constraint filtering, and the diversity seed batch.

Constraints declared in a template are enforced here, in code, before any
optimization runs -- they are never suggested to the model. What survives this
module is the feasible pool, and both arms of the comparison draw from it.
"""

import itertools

import numpy as np

from . import encode, scoring


def enumerate_variants(parent, editable_region, max_mutations, alphabet=encode.AMINO_ACIDS):
    """Every sequence within the mutation budget, parent first.

    Finite and enumerable by design: 8 positions, at most 2 mutations, 20
    residues gives 10,261 sequences including the parent.
    """
    sl = encode.region_slice(editable_region)
    positions = list(range(sl.start, sl.stop))
    out = [parent]
    seen = {parent}
    for k in range(1, int(max_mutations) + 1):
        for combo in itertools.combinations(positions, k):
            choices = [[a for a in alphabet if a != parent[p]] for p in combo]
            for repl in itertools.product(*choices):
                chars = list(parent)
                for p, a in zip(combo, repl):
                    chars[p] = a
                s = "".join(chars)
                if s not in seen:
                    seen.add(s)
                    out.append(s)
    return out


def constraint_report(sequences, parent, editable_region, objectives, constraints):
    """-> (kept, removed) where removed rows carry the reason.

    Reporting how many candidates were removed and why is part of the contract:
    the batch panel prints it, and the comparison shares this pool across arms
    so the chart measures the model rather than the filter.
    """
    forbidden = set(constraints.get("forbidden_motifs", []))
    thresholds = [
        o for o in objectives if o.get("source") == "computed" and "threshold" in o
    ]
    kept, removed = [], []
    for s in sequences:
        sc = scoring.score(s, parent, editable_region)
        reason = None
        introduced = sc["introduced_liabilities"]
        hit = sorted(set(introduced) & forbidden)
        if hit:
            reason = "introduces_liability:" + ",".join(hit)
        if reason is None:
            for o in thresholds:
                v = sc.get(o["name"])
                if v is None:
                    continue
                if o.get("direction", "minimize") == "minimize" and float(v) > float(o["threshold"]):
                    reason = "%s_above_threshold:%.4f>%.4f" % (o["name"], v, o["threshold"])
                    break
                if o.get("direction") == "maximize" and float(v) < float(o["threshold"]):
                    reason = "%s_below_threshold:%.4f<%.4f" % (o["name"], v, o["threshold"])
                    break
        if reason is None:
            kept.append(s)
        else:
            removed.append({"sequence": s, "reason": reason})
    return kept, removed


def removal_summary(removed):
    counts = {}
    for r in removed:
        key = r["reason"].split(":", 1)[0]
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def diversity_seed_batch(sequences, k, editable_region, seed_index=0):
    """Greedy max-min Hamming selection over the feasible pool.

    With no model run on disk there is nothing to exploit, so round 1 is a
    diversity-maximizing draw. Same code path as every later round, one branch
    deep, and it is the batch both arms of the comparison start from.
    """
    if k >= len(sequences):
        return list(range(len(sequences)))
    X = encode.one_hot(sequences, editable_region)
    L = encode.region_length(editable_region)
    chosen = [int(seed_index)]
    mind = L - X @ X[chosen[0]]
    mind[chosen[0]] = -1.0
    while len(chosen) < k:
        nxt = int(np.argmax(mind))
        chosen.append(nxt)
        d = L - X @ X[nxt]
        mind = np.minimum(mind, d)
        mind[nxt] = -1.0
    return chosen


def max_min_distance(sequences, editable_region):
    """Diagnostic: the minimum pairwise distance within a selected set."""
    if len(sequences) < 2:
        return float("nan")
    D = encode.hamming_matrix(sequences, editable_region)
    np.fill_diagonal(D, np.inf)
    return float(D.min())
