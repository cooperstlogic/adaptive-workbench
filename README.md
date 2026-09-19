# Adaptive Optimization Workbench

A one-day functional prototype of a scientist-governed system that takes an antibody
lead, learns from each round of experimental results, and recommends the next batch of
variants to test.

Read `SPEC.md` for the full specification, `CLAUDE.md` for the working rules, and
`DECISIONS.md` for every choice already settled and why.

> **Everything about the laboratory is simulated.** The landscape is synthetic, the LIMS
> is a mock, and the wet lab is an oracle that replays generated values with noise. The
> chart this produces demonstrates that the decision loop works — it does not demonstrate
> that the method finds better antibodies. See the staged table at the bottom.

## Setup

numpy is the only dependency of `core/`, and that is a design constraint rather than an
oversight — not because scipy cannot run in the browser, which it can, but because
`core/` is the part an audience is invited to read. matplotlib is an *evaluator*
dependency, used by `plot_campaign.py` and nothing on a product path.

```bash
python3.12 -m venv .venv
.venv/bin/pip install numpy matplotlib
.venv/bin/python check.py      # 73 invariant checks, all should pass
```

`.venv/` is gitignored. Everything else needed — including the generated landscape — is
committed, so a fresh clone plus the two commands above reproduces the current state.

**Use `.venv/bin/python`, not `python3`.** The system interpreter has no numpy.

## What runs today

```bash
.venv/bin/python -m data.build_oracle        # regenerate the landscape (deterministic)
.venv/bin/python simulate_campaign.py        # the evaluator: 20 seeds, 3 arms, chart, ~35 s
.venv/bin/python plot_campaign.py            # re-render the chart alone, ~1 s
.venv/bin/python check.py                    # verify every documented invariant, ~20 s
```

And the product path, which is the same science through the CLI:

```bash
.venv/bin/python init_project.py --name demo-trastuzumab --team d.webster --force
.venv/bin/python run_rounds.py --rounds 4 --ignore-flags --approved-by d.webster
.venv/bin/python lims.py tools               # the LIMS write path, which is the boundary claim
```

`run_rounds.py` is a deliberately dumb scheduler over the five pipeline scripts. It prints
every command it runs and **stops** the moment a round is flagged, because that is where
the judgment is. `--ignore-flags` carries on without a ruling.

`check.py` runs 73 checks in about twenty seconds and is the handoff contract. Every check in it corresponds to a rule in
`CLAUDE.md` or a number recorded in `DECISIONS.md`, so a failure means the state has
drifted from what is documented.

## Build status

| Phase | Deliverable | State |
| --- | --- | --- |
| 1 | Repo skeleton, synthetic oracle, project schema, one-hot encoder, pre-registered parameters | **Done** |
| 2 | `core/surrogate.py`, `acquisition.py`, `reconcile.py`, `simulate_campaign.py` | **Done — gate passed** |
| 3 | The five pipeline scripts, `SKILL.md`, the mock LIMS | **Done** |
| 4 | `core/diagnostics.py`, `run_diagnostic.py`, `record_decision.py`, decision records | **Next** |
| 5 | Both MCP servers, end-to-end run driven by Claude Code | Not started |
| 6 | Web app: Pyodide boot, three panels, approve loop, decision card | Not started |
| 7 | Reasoning panel: function, two tools, budget cap, verified fallback | Not started |
| 8 | Committed demo project at round 3, Netlify deploy, public README | Not started |
| 9 | Demo script and rehearsal | Not started |

### Phase 1 results

| | |
| --- | --- |
| Candidate space | 10,261 enumerated → **7,294 feasible** (1,625 removed for hydrophobicity, 1,342 for introduced liabilities) |
| Realized linear R² | **0.6008** against the pre-registered 0.60 target |
| Parent (trastuzumab VH) | exactly **9.000 pKD** |
| Detection limit / threshold | **6.861** / **10.762 pKD** |
| Above threshold | 74 of 7,294 — **1.01%** |
| Cliff | VH 103, parent residue **F**, residues {P,D,E,K,R}, depth −1.50 pKD |
| Round 1 | 48 single-mutant designs, every editable position covered |
| Build hash | `sha256:c9b2566abc75f0db…` (deterministic across rebuilds) |

### Phase 2 results — the gate

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="web/public/assets/campaign-dark.png">
  <img src="web/public/assets/campaign.png" alt="Two panels. Left, cumulative best observed affinity by round for three arms, median with interquartile bands, against a dashed pre-registered threshold at 10.762 pKD. Right, the true affinity of the design each arm's own project state ranks first. Model-guided leads both panels; guided with naive pooling tracks it until the assay version changes at round 4 and then falls behind.">
</picture>

**The gate passes.** Twenty seeds per arm, six rounds, batch of 48, a shared round-1
single-mutant scan, scored against the 10.762 pKD threshold that was fixed before any of
it ran. Reproduce with `.venv/bin/python simulate_campaign.py`.

**The landscape is synthetic.** This shows the decision loop converges. It does not show
that the method finds better antibodies.

| | guided | random | guided, naive pooling |
| --- | --- | --- | --- |
| Mean rounds to threshold | **2.00** | 2.95 | 2.00 |
| Reached threshold by round 6 | 20/20 | 18/20 | 20/20 |
| Final best observed, median | **11.762** | 11.212 | 11.015 |
| Final best landscape, median | **11.674** | 11.105 | 11.674 |

Guided is **never slower than random on any of the twenty paired seeds** and faster on
eight, an exact paired sign test at p = 0.0078. The interquartile bands separate at rounds
2, 5 and 6 on both the observed and the noise-free line. The median guided run reaches the
feasible pool's global maximum of 11.674 pKD by round 5, and 17 of the 20 individual runs
reach it by round 6; random plateaus at 11.105.

The median rounds-to-threshold ties at 2.0 for both arms and is reported but not tested
against: it is a discrete count with a floor at two and guided lands on that floor in
eighteen of twenty seeds, so it has no resolution here. `DECISIONS.md` records that the
verdict was re-scored on the paired comparison after the first run, what the numbers were
either way, and that nothing about the landscape, the parameters, the seed or the
threshold moved.

**Four things the gate run found, all fixed, none of them the landscape.** The round-1
scan was covering four of eight positions because greedy max-min Hamming is degenerate
over single mutants. The bridging set was selected for high readings, so it measured
regression to the mean and biased every offset estimate by about −0.10 pKD. The anomaly
flag, defined as an interval miss rate, fired on every round — because acquisition
deliberately samples where the model is least certain, so a dispersion statistic always
trips. And building phase 3 found that **batch selection was not reproducible**: dozens of
designs carry bit-identical predictive variance, and the exploration slots were ranked with
an unstable sort, so the same project produced a different batch on a different numpy
build. That one is fixed in `core/`, the gate was re-run, and the verdict did not move.
`DECISIONS.md` has the full account of each.

**What naive pooling actually costs.** The right-hand panel is the one that matters,
and it says something stronger than the headline. Pooling across the round-4 assay
version change does not make the optimizer *pick* worse designs — its noise-free
selection line reaches the same 11.674 as corrected guided selection. What it does is
corrupt the ranking the project holds, so the arm **advances a genuinely worse molecule
in 14 of 20 seeds, a median 0.648 pKD worse — a four-fold error in the KD of the lead
you would take forward.** The mechanism is specific and worth saying out loud: the
best-so-far design is re-run as a control every round, and pooling its round-4 reading
naively drags its own average down until a worse design outranks it. The arm demotes
its own best molecule. One seed in twenty crosses the threshold and then reports itself
back below it. And the round that needed a ruling never gets one, so the flag keeps
firing: 15 of 20 at round 5 and 9 of 20 at round 6, against 3 and 1 for the corrected
arm.

| Also worth knowing | |
| --- | --- |
| Round-4 offset recovery | estimated **−0.852** against a true −0.816, mean error −0.036 pKD |
| Round 4 flags | **19 of 20** seeds; median discrepancy 1.24 pKD against 0.20–0.64 elsewhere |
| Rounds 5 and 6 | go quiet once the version is characterized; the uncorrected arm keeps alarming |
| Bake-off winner | `ridge_onehot` in every round of every seed; the GP loses on calibration |
| Naive pooling | does **not** degrade selection. It degrades the ranking you act on: a worse lead in 14 of 20 seeds, median 0.648 pKD |

### Phase 3 results — the same science through the CLI

**Six rounds run end to end through the five pipeline scripts and the mock LIMS**, and
they select the same wells the evaluator does.

| | |
| --- | --- |
| Fidelity, uncorrected | the CLI reproduces the evaluator's naive arm to **1 × 10⁻⁶ pKD** on every round |
| Fidelity, corrected | the CLI reproduces the evaluator's corrected arm to **7 × 10⁻⁷ pKD** |
| Wells agreeing | **288 of 288** — all six batches identical in membership and order |
| Reconciliation | 96 rows per round joined to 48 designs through the registry's sample ids |
| Round graph | 30 artifacts, every hash matching the record it points at |
| Committed demo project | 4 rounds, round 4 flagged and unruled, 1.3 MB of JSON |

That the CLI and the evaluator pick the same 288 wells is the strongest statement
available that the science is implemented once. It is what non-negotiable 2 asks for, and
it is checked rather than asserted: `check.py` runs both campaigns and compares them.

**The scheduler stops where the judgment is.** `run_rounds.py` calls the five scripts in
order and halts the moment `import_round` raises a flag. In the demo project that happens
twice, at rounds 2 and 4, and the two rounds need opposite answers — which is the argument
for the decision record in one sentence.

| Demo project, round 4 | |
| --- | --- |
| Assay version | **v1.3**, first seen this round, so nothing about it is characterized |
| Fresh designs | 42 came back a mean **−2.046 pKD** from where the model put them |
| Interval coverage | **0.07** realized against 0.80 nominal and 0.82 held out at fit time |
| Bridge | 3 shared designs estimate **−1.014 pKD**, se 0.059 |
| Residual by position | flat from −1.57 to −2.42; cliff-hitting designs are indistinguishable |
| Frame | offset **not applied**; authority `unruled` |

**Round 4 is genuinely ambiguous and nobody engineered it.** SPEC.md asked whether the
ambiguity would arise on its own, and it does — but not as the clean single-cause story
the spec sketched. The bridge recovers about a pKD of assay shift, and that accounts for
only half of what the fresh designs show. The residual is flat across mutated positions,
so it is **not** the cliff. Whatever remains is the model, and a diagnosis that corrects
the offset and stops there will be wrong about half the round. That is a better artifact
than a single-cause round, and it is what phase 4 has to get right.

### Before starting phase 4

- **The threshold is 10.762 pKD and it is already fixed.** Do not recompute it, do not
  re-pick it, and do not adjust it. Do not change the landscape or its parameters.
- `simulate_campaign.py` remains the one and only thing permitted to read landscape
  values. Nothing on a product path may.
- The five diagnostics go in `core/diagnostics.py` as pure numpy, read-only, each under
  twenty lines. `run_diagnostic.py` prints one of them and writes nothing.
  `record_decision.py` is a dumb writer with no logic of its own.
- **Two rounds in the demo project are flagged, not one**, and they want different
  rulings. Round 2 flags *positively*: a model fit on single mutants under-predicts the
  first double mutants, so the right action is `refit_only` and nothing to the data. Round
  4 flags negatively and wants `apply_offset_correction` — partially. The same statistic,
  two correct answers.
- Round 4's discrepancy is **not** fully explained by its offset. `residual_by_mutation_class`
  should come back flat, which is the evidence that rules the cliff out; the remaining gap
  is the model, and `calibration_by_region` is the test that shows it.
- Applying a ruling is `import_round.py --offset always --authority decision_NNN`, which
  rewrites that round's snapshot in the corrected frame. Correcting round 4 makes rounds 5
  and 6 go quiet, and `check.py` verifies that.
- The batch is 48 inclusive: 2 controls, 2 replicates, 2 exploration slots, 42 fresh
  picks. Only 3 of the re-measured designs are the bridge; the best-so-far control is
  re-run to confirm it and is deliberately excluded from the offset estimate.

## Repo map

| Path | Contents |
| --- | --- |
| `core/` | Pure numpy, shared by every surface. No network, no printing, no scipy/sklearn/pandas |
| `core/schema.py` | Canonical JSON, content hashing, project directory layout |
| `core/encode.py` | Sequence handling, the one-hot block, Hamming distance |
| `core/scoring.py` | Deterministic developability scores; liabilities counted as *introduced* |
| `core/candidates.py` | Enumeration, constraint enforcement, the round-1 stratified scan |
| `core/surrogate.py` | The two recipes, their cross-validation, and the bake-off between them |
| `core/acquisition.py` | Expected improvement, diversity-penalized selection, batch composition |
| `core/reconcile.py` | Replicates, censoring, bridging offsets, the anomaly flag |
| `core/project.py` | Template instantiation and project-state accessors |
| `data/` | The simulated laboratory. Never imported by `core/` |
| `data/synthetic.py` | The landscape: additive site effects + pairwise epistasis + one cliff |
| `data/oracle.py` | Noise, ~3% construct failure, censoring, per-round and per-plate offsets |
| `data/build_oracle.py` | Generates and calibrates the landscape, writes the assets |
| `templates/` | One working template, one visible stub |
| `projects/demo-trastuzumab/` | The committed demo project |
| `init_project.py` | Template → project directory. Writes no designs; not part of the round loop |
| `skills/adaptive-optimization/SKILL.md` | The skill: state contract, the round loop, the diagnosis procedure, four rules |
| `skills/adaptive-optimization/scripts/` | The five pipeline scripts. Thin wrappers over `core/`, no network, no lab |
| `lims.py` | The mock LIMS. Mints identifiers, owns the plate layout, holds the oracle |
| `run_rounds.py` | A dumb scheduler over the five scripts. Stops on a flagged round |
| `lims_store/` | The registry's own records, outside the project. Exports are gitignored |
| `simulate_campaign.py` | The evaluator. The only thing permitted to read landscape values |
| `web/public/assets/campaign.json` | The proof chart's data, written by the evaluator |
| `plot_campaign.py` | Renders the proof chart from `campaign.json`. matplotlib lives here, never in `core/` |
| `check.py` | Invariant verification, 73 checks. Run it after any phase |

## What is real and what is staged

| Component | Status |
| --- | --- |
| Surrogate fitting, calibration, constraint filtering, batch acquisition | **Real.** Pure numpy, every round, browser and CLI |
| The five pipeline scripts and the round graph | **Real.** Six rounds through the CLI, selecting the same wells as the evaluator |
| The five diagnostics and the decision record | **Not built.** Phase 4. `SKILL.md` names them and says they cannot be run |
| Both model recipes and the bake-off between them | **Real.** `ridge_onehot` against `gp_pca64` over the one-hot block |
| Developability and liability scores | **Real** deterministic calculations, labelled computed throughout |
| Affinity values | **Simulated.** Synthetic landscape with pre-registered parameters |
| The wet lab | **Simulated.** Noise, ~3% failure, censoring, per-round offsets |
| The LIMS | **Staged.** `lims.py` mints identifiers and exports rows; the write path attaches a link and nothing more. The MCP transport lands in phase 5 |
| Sequence embeddings | **Not built.** One-hot only; the provider interface exists and `esm_live` is unwired |
| Structure prediction | **Stubbed.** Returns a cached result and says so |
| The agent's reasoning in the browser | **Real Claude** while the daily budget holds; verified replay otherwise |
| The agent's reasoning in the CLI | **Not yet exercised.** Phase 5, and it is the hour-5 gate |
| Rounds run in the browser | **Real.** The same Python, state held in the browser, never written back |

Rows for components that do not exist yet describe what they will be, and the build
status table above says which of them are built.
