"""Sequence handling and the one-hot feature block.

One-hot is the only feature block in this build: 8 positions by 20 amino acids.
``gp_pca64`` runs a PCA over this same block, so the two-recipe bake-off needs
nothing further.
"""

import numpy as np

AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
AA_INDEX = {a: i for i, a in enumerate(AMINO_ACIDS)}
N_AA = len(AMINO_ACIDS)


def region_slice(editable_region):
    """The editable region is half-open: [start, end), so [98, 106) is 8 positions."""
    start, end = editable_region
    return slice(int(start), int(end))


def region_length(editable_region):
    start, end = editable_region
    return int(end) - int(start)


def window(sequence, editable_region):
    return sequence[region_slice(editable_region)]


def with_window(parent, editable_region, new_window):
    sl = region_slice(editable_region)
    if len(new_window) != sl.stop - sl.start:
        raise ValueError("window length mismatch")
    return parent[: sl.start] + new_window + parent[sl.stop :]


def mutations(parent, sequence, editable_region):
    """-> [(absolute_position, from_aa, to_aa)] inside the editable region."""
    sl = region_slice(editable_region)
    out = []
    for i in range(sl.start, sl.stop):
        if parent[i] != sequence[i]:
            out.append((i, parent[i], sequence[i]))
    return out


def mutation_labels(parent, sequence, editable_region):
    return ["%s%d%s" % (f, p, t) for p, f, t in mutations(parent, sequence, editable_region)]


def n_mutations(parent, sequence, editable_region):
    return len(mutations(parent, sequence, editable_region))


def one_hot(sequences, editable_region):
    """-> float32 (n, L*20), row-major over (position, amino acid)."""
    sl = region_slice(editable_region)
    L = sl.stop - sl.start
    X = np.zeros((len(sequences), L * N_AA), dtype=np.float32)
    for r, seq in enumerate(sequences):
        for j, pos in enumerate(range(sl.start, sl.stop)):
            aa = seq[pos]
            idx = AA_INDEX.get(aa)
            if idx is None:
                raise ValueError("non-standard residue %r at position %d" % (aa, pos))
            X[r, j * N_AA + idx] = 1.0
    return X


def hamming(a, b, editable_region):
    sl = region_slice(editable_region)
    return sum(1 for i in range(sl.start, sl.stop) if a[i] != b[i])


def hamming_matrix(sequences, editable_region):
    """Pairwise Hamming distance over the editable region, via the one-hot block."""
    X = one_hot(sequences, editable_region)
    L = region_length(editable_region)
    matches = X @ X.T
    return (L - matches).astype(np.float32)


def sequence_id(sequence):
    import hashlib

    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()[:12]
