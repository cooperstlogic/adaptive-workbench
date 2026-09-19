"""Deterministic in-silico developability scores.

These are exact calculations, not measurements. That asymmetry decides what
each kind of objective is for: affinity is uncertain so it is optimized under a
model, while these are exact so their thresholds are enforced as filters before
optimization runs and whatever margin remains is only a tie-break.

``liability_count`` counts motifs the variant *introduces* relative to the
parent. The trastuzumab CDR-H3 carries a DG isomerization motif of its own, and
a rule that rejected the approved lead's own scaffold would be a filter nobody
would ship. Introducing none is the real design rule.
"""

import numpy as np

from . import encode

# Kyte-Doolittle hydropathy
KD_SCALE = {
    "A": 1.8, "C": 2.5, "D": -3.5, "E": -3.5, "F": 2.8,
    "G": -0.4, "H": -3.2, "I": 4.5, "K": -3.9, "L": 3.8,
    "M": 1.9, "N": -3.5, "P": -1.6, "Q": -3.5, "R": -4.5,
    "S": -0.8, "T": -0.7, "V": 4.2, "W": -0.9, "Y": -1.3,
}
KD_MIN, KD_MAX = -4.5, 4.5

LIABILITY_MOTIFS = ("NG", "DG")
LIABILITY_RESIDUES = ("C",)

CHARGE_POS = ("K", "R")
CHARGE_NEG = ("D", "E")


def _context(sequence, editable_region, pad=1):
    """The editable window plus one flanking residue, so motifs spanning the
    boundary are detected rather than missed."""
    sl = encode.region_slice(editable_region)
    lo = max(0, sl.start - pad)
    hi = min(len(sequence), sl.stop + pad)
    return sequence[lo:hi]


def hydrophobicity(sequence, editable_region):
    """Mean Kyte-Doolittle over the editable window, normalized to [0, 1]."""
    w = encode.window(sequence, editable_region)
    mean = sum(KD_SCALE[a] for a in w) / len(w)
    return (mean - KD_MIN) / (KD_MAX - KD_MIN)


def net_charge(sequence, editable_region):
    """Net formal charge of the editable window at neutral pH."""
    w = encode.window(sequence, editable_region)
    return sum(1 for a in w if a in CHARGE_POS) - sum(1 for a in w if a in CHARGE_NEG)


def liability_motifs(sequence, editable_region):
    """-> sorted list of 'MOTIF@offset' labels found in the window plus flanks."""
    ctx = _context(sequence, editable_region)
    found = []
    for m in LIABILITY_MOTIFS:
        for i in range(len(ctx) - len(m) + 1):
            if ctx[i : i + len(m)] == m:
                found.append("%s@%d" % (m, i))
    for r in LIABILITY_RESIDUES:
        for i, a in enumerate(ctx):
            if a == r:
                found.append("%s@%d" % (r, i))
    return sorted(found)


def introduced_liabilities(sequence, parent, editable_region):
    """Motifs present in the variant and not in the parent, by motif identity.

    Compared as multisets of motif *kinds*, so a DG that merely shifts position
    is not counted as new while a second DG is.
    """
    from collections import Counter

    def kinds(s):
        return Counter(lbl.split("@", 1)[0] for lbl in liability_motifs(s, editable_region))

    var, par = kinds(sequence), kinds(parent)
    out = []
    for k, n in var.items():
        extra = n - par.get(k, 0)
        out.extend([k] * extra) if extra > 0 else None
    return sorted(out)


def liability_count(sequence, parent, editable_region):
    return len(introduced_liabilities(sequence, parent, editable_region))


def score(sequence, parent, editable_region):
    return {
        "hydrophobicity": hydrophobicity(sequence, editable_region),
        "net_charge": net_charge(sequence, editable_region),
        "liability_count": liability_count(sequence, parent, editable_region),
        "introduced_liabilities": introduced_liabilities(sequence, parent, editable_region),
    }


def score_many(sequences, parent, editable_region):
    return [score(s, parent, editable_region) for s in sequences]


def developability_margin(scored, objectives):
    """How much slack a design has against its computed thresholds.

    Used only as a tie-break among candidates that already pass, never folded
    into the acquisition -- the probability of satisfying an exact constraint is
    always zero or one, and multiplying it in would be theatre.
    """
    margins = []
    for obj in objectives:
        if obj.get("source") != "computed" or "threshold" not in obj:
            continue
        v = scored.get(obj["name"])
        if v is None:
            continue
        t = obj["threshold"]
        if obj.get("direction", "minimize") == "minimize":
            margins.append(float(t) - float(v))
        else:
            margins.append(float(v) - float(t))
    return float(np.min(margins)) if margins else 0.0
