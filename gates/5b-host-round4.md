# Round 4 diagnosis — demo-trastuzumab (synthetic campaign)

All numbers below are synthetic: the landscape is generated, the LIMS is a mock,
and the assay is an oracle replaying values with noise. Every statistic was
produced by a named `core.diagnostics` function via `run_diagnostic.py`
(read-only); none was computed by hand.

Snapshot `sha256:eedea043…` · batch `sha256:6e4287a2…` · model run 003 `sha256:d86da121…`

## The flag

| | |
| --- | --- |
| Statistic | mean signed residual, fresh designs |
| Value | **-2.046 pKD** (se 0.108, z -18.96), n = 42 |
| Trigger | 0.5 pKD |
| Direction | below prediction |
| Outside the 80% interval | 95.2% (expected 20%) |
| Assay version | v1.3 — first round on it; `known_version_offset` is null |
| Frame as recorded | offset applied 0.000, authority `unruled` |

Two causes trip this statistic identically — an uncharacterized assay step and a
real activity cliff — so the flag says the round needs deciding, not which
explanation wins.

## Five tests

| Test | Result | Reading |
| --- | --- | --- |
| `offset_from_controls` | bridge n=3, offset **-1.014 pKD** (se 0.059); spread sd 0.102 vs tolerance 0.342 (2.0 x read-noise 0.171) → **concordant** | The assay moved. Supported, and the bridge is usable |
| `residual_by_plate` | R4P1 -1.872 (n=23), R4P2 -2.011 (n=23); gap 0.139, se 0.224, z 0.62 | Not a plate artifact — both plates are equally low |
| `replicate_concordance` | read-noise scale 0.171; 0 of 45 designs above the 0.514 tolerance; max read sd 0.354 | The assay was stable while it was read. Not noise |
| `residual_by_mutation_class --by position` | pos 102 n=43 at -1.995 vs n=3 "other"; pos 100 n=4 at -2.416; no class with adequate n separates | Inconclusive. The large class is the whole round and its comparator is 3 carryover designs; the small classes cannot move a round |
| `residual_by_mutation_class --by n_mutations` | 45 of 46 designs are doubles; the 0-mutation class is n=1 | Inconclusive by construction — no contrast to draw |
| `calibration_by_region` | coverage **0.065** vs nominal 0.80, mean residual -1.941 | The intervals are unusable in the raw frame |
| `calibration_by_region --offset bridge` | coverage **0.565**, mean residual -0.927 (all); **0.524** and -1.032 restricted to the 42 fresh designs | The bridge recovers about half the round and no more |

## What this means

The bridge offset is real and the round is genuinely on a different ruler: three
shared designs, measured twice, agree with each other and put the v1.2→v1.3 step
at -1.014 pKD. Round 4 cannot be pooled with rounds 1-3 without it.

The correction does not rescue the round. After applying it, the fresh designs
are still **-1.032 pKD** below prediction with coverage 0.524 against a nominal
0.80. That remainder is not the assay — the plates agree, the reads are
repeatable — and it is not a localized cliff either: the shortfall is flat across
the edited positions rather than concentrated in one class. It is the signature
of a model extrapolating past its training range; the picks were predicted at
10.3-11.3 pKD, above everything the model had seen.

## Recommendation

1. **Apply the bridge offset correction** of -1.014 pKD as the recorded estimate — never a number chosen to make the residuals vanish, which would need roughly twice this and has nothing behind it.
2. **Refit on the corrected pool** and treat the remaining -1.03 pKD as a finding, not an error to be corrected away: the additive surrogate over-credits the dominant substitution when it is combined into doubles.
3. **Widen exploration in round 5** and add a v1.3-to-v1.3 bridge, so a further shift of similar size would distinguish a version step from ongoing drift.

Caveat worth carrying: the bridge is n=3, the minimum that can support a
correction — one discordant member would flip it.

## Status of the record

`decisions/decision_004.json` already carries this as a proposal (8 hypotheses,
action `apply_offset_correction`, confidence `high`, `if_wrong` filled in), with
`status: open` and `ruling: null`. Its numbers reproduce the tests above. **No
action may be taken until a named approver rules on it**, and the loop stays
blocked at step 6 — `models/run_004.json` does not exist — until then.

On an `accepted` ruling the next commands are:

```
python3 skills/adaptive-optimization/scripts/import_round.py --project projects/demo-trastuzumab --round 4 \
    --results lims_store/exports/demo-trastuzumab_round4.csv \
    --offset always --authority decision_004
python3 skills/adaptive-optimization/scripts/fit_surrogates.py --project projects/demo-trastuzumab --round 4
```
