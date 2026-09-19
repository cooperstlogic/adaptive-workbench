"""The simulated lab.

Answers exactly one question: given these sequences, what would the lab have
reported? It lives behind the registry MCP server -- ``core`` never imports it,
so the workbench sees only what a lab reported and never ground truth.

The noise model is not decoration. It is what gives ``import_round`` real
reconciliation work, what makes the calibration panel non-trivial, and what
makes round 4 genuinely ambiguous.

``run_seed`` selects an independent replay of the same lab: same landscape,
same pre-registered noise parameters, different draws. It is what makes twenty
seeds per arm twenty independent runs rather than twenty copies of one. It is
not a landscape parameter and changes nothing in DECISIONS.md.
"""

import hashlib

import numpy as np

ASSAY_VERSIONS = {1: "v1.2", 2: "v1.2", 3: "v1.2"}
ASSAY_VERSION_LATE = "v1.3"
VERSION_CHANGE_ROUND = 4


def assay_version(round_id):
    return ASSAY_VERSIONS.get(int(round_id), ASSAY_VERSION_LATE)


def plate_key(plate):
    """A stable integer for a plate label.

    Python's ``hash`` over a string is salted per process, so using it here
    made plate offsets differ between two runs of the same campaign. Any claim
    that a diagnostic recovers a plate effect has to survive a restart, so the
    key is a digest.
    """
    return int(hashlib.sha256(str(plate).encode("utf-8")).hexdigest()[:8], 16)


class Oracle:
    """Replays landscape values with noise, failures, censoring and offsets."""

    def __init__(self, landscape, detection_limit, params=None, run_seed=0):
        self.landscape = landscape
        self.detection_limit = float(detection_limit)
        self.params = dict(params or landscape.params)
        self.run_seed = int(run_seed)

    def _key(self, stream, *rest):
        return (int(self.params["seed"]), stream, self.run_seed) + tuple(int(r) for r in rest)

    def round_offset(self, round_id):
        """Applies to every well in the round, controls included -- which is
        what makes it recoverable from the bridging set rather than merely
        suffered."""
        rng = np.random.default_rng(self._key(9001, round_id))
        drift = float(rng.normal(0.0, self.params["round_offset_sigma"]))
        if int(round_id) >= VERSION_CHANGE_ROUND:
            drift += float(self.params["round4_version_shift"])
        return drift

    def plate_offset(self, round_id, plate):
        if plate is None:
            return 0.0
        rng = np.random.default_rng(self._key(9002, round_id, plate_key(plate)))
        return float(rng.normal(0.0, self.params["plate_offset_sigma"]))

    def measure(self, sequences, round_id, plates=None):
        """-> list of rows, one per read.

        Replicates come back as separate rows, never pre-averaged. Failed
        constructs take out every read for that design, which is what a failed
        expression actually does.
        """
        round_id = int(round_id)
        rng = np.random.default_rng(self._key(7001, round_id))
        truth = self.landscape.value(list(sequences))
        offset = self.round_offset(round_id)
        version = assay_version(round_id)
        reads = int(self.params["reads_per_design"])
        failed = rng.random(len(sequences)) < float(self.params["construct_failure_rate"])

        poff_cache = {}
        rows = []
        for i, seq in enumerate(sequences):
            plate = None if plates is None else plates[i]
            if plate not in poff_cache:
                poff_cache[plate] = self.plate_offset(round_id, plate)
            poff = poff_cache[plate]
            for rep in range(1, reads + 1):
                if failed[i]:
                    rows.append({
                        "sequence": seq, "replicate": rep, "value": None, "plate": plate,
                        "unit": "pKD", "status": "failed", "assay_version": version,
                    })
                    continue
                v = float(truth[i] + offset + poff + rng.normal(0.0, self.params["assay_noise_sigma"]))
                if v < self.detection_limit:
                    rows.append({
                        "sequence": seq, "replicate": rep, "value": self.detection_limit, "plate": plate,
                        "unit": "pKD", "status": "censored_low", "assay_version": version,
                    })
                else:
                    rows.append({
                        "sequence": seq, "replicate": rep, "value": v, "plate": plate,
                        "unit": "pKD", "status": "ok", "assay_version": version,
                    })
        return rows
