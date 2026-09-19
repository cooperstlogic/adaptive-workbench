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

numpy is the only dependency, and that is a design constraint rather than an oversight.

```bash
python3.12 -m venv .venv
.venv/bin/pip install numpy
.venv/bin/python check.py      # 44 invariant checks, all should pass
```

`.venv/` is gitignored. Everything else needed — including the generated landscape — is
committed, so a fresh clone plus the two commands above reproduces the current state.

**Use `.venv/bin/python`, not `python3`.** The system interpreter has no numpy.

## What runs today

```bash
.venv/bin/python -m data.build_oracle        # regenerate the landscape (deterministic)
.venv/bin/python init_project.py --name demo-trastuzumab --force
.venv/bin/python simulate_campaign.py        # the proof chart, ~35 s
.venv/bin/python check.py                    # verify every documented invariant
```

`check.py` runs 44 checks and is the handoff contract. Every check in it corresponds to a rule in
`CLAUDE.md` or a number recorded in `DECISIONS.md`, so a failure means the state has
drifted from what is documented.

## Build status

| Phase | Deliverable | State |
| --- | --- | --- |
| 1 | Repo skeleton, synthetic oracle, project schema, one-hot encoder, pre-registered parameters | **Done** |
| 2 | `core/surrogate.py`, `acquisition.py`, `reconcile.py`, `simulate_campaign.py` | **Done — gate passed** |
| 3 | The five pipeline scripts and `SKILL.md` | **Next** |
| 4 | `core/diagnostics.py`, `run_diagnostic.py`, `record_decision.py`, decision records | Not started |
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
| Round 1 | 48 single-mutant designs |
| Build hash | `sha256:c9b2566abc75f0db…` (deterministic across rebuilds) |

### Phase 2 results — the gate

**The gate passes.** Twenty seeds per arm, six rounds, batch of 48, a shared round-1
single-mutant scan, scored against the 10.762 pKD threshold that was fixed before any of
it ran. Reproduce with `.venv/bin/python simulate_campaign.py`.

**The landscape is synthetic.** This shows the decision loop converges. It does not show
that the method finds better antibodies.

| | guided | random | guided, naive pooling |
| --- | --- | --- | --- |
| Mean rounds to threshold | **2.00** | 2.95 | 2.00 |
| Reached threshold by round 6 | 20/20 | 18/20 | 20/20 |
| Final best observed, median | **11.755** | 11.212 | 11.052 |
| Final best landscape, median | **11.674** | 11.105 | 11.674 |

Guided is **never slower than random on any of the twenty paired seeds** and faster on
eight, an exact paired sign test at p = 0.0078. The interquartile bands separate at rounds
2, 5 and 6 on both the observed and the noise-free line. Guided reaches the feasible
pool's global maximum of 11.674 pKD by round 5 in every run; random plateaus at 11.105.

The median rounds-to-threshold ties at 2.0 for both arms and is reported but not tested
against: it is a discrete count with a floor at two and guided lands on that floor in
eighteen of twenty seeds, so it has no resolution here. `DECISIONS.md` records that the
verdict was re-scored on the paired comparison after the first run, what the numbers were
either way, and that nothing about the landscape, the parameters, the seed or the
threshold moved.

**Three things the gate run found, all fixed, none of them the landscape.** The round-1
scan was covering four of eight positions because greedy max-min Hamming is degenerate
over single mutants. The bridging set was selected for high readings, so it measured
regression to the mean and biased every offset estimate by about −0.10 pKD. And the
anomaly flag, defined as an interval miss rate, fired on every round — because acquisition
deliberately samples where the model is least certain, so a dispersion statistic always
trips. `DECISIONS.md` has the full account of each.

| Also worth knowing | |
| --- | --- |
| Round-4 offset recovery | estimated **−0.841** against a true −0.816, mean error −0.025 pKD |
| Round 4 flags | **19 of 20** seeds; median discrepancy 1.07 pKD against 0.19–0.63 elsewhere |
| Rounds 5 and 6 | go quiet once the version is characterized; the uncorrected arm keeps alarming |
| Bake-off winner | `ridge_onehot` in every round of every seed; the GP loses on calibration, 0.59–0.62 coverage against 0.80–0.88 |
| Naive pooling | does **not** degrade selection. It degrades what you believe you measured, by 0.702 pKD on all 20 seeds |

### Before starting phase 3

- **The threshold is 10.762 pKD and it is already fixed.** Do not recompute it, do not
  re-pick it, and do not adjust it. Do not change the landscape or its parameters.
- `simulate_campaign.py` remains the one and only thing permitted to read landscape
  values. Nothing on a product path may.
- The five pipeline scripts are thin wrappers over `core/`. `import_round.py` in
  particular wraps `core/reconcile.py` and adds no arithmetic of its own — a second
  implementation of the bridging maths is the fork non-negotiable 2 forbids.
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
| `init_project.py` | Template → project directory. Not part of the round loop |
| `simulate_campaign.py` | The evaluator. The only thing permitted to read landscape values |
| `web/public/assets/campaign.json` | The proof chart's data, written by the evaluator |
| `check.py` | Invariant verification, 44 checks. Run it after any phase |

## What is real and what is staged

| Component | Status |
| --- | --- |
| Surrogate fitting, calibration, constraint filtering, batch acquisition | **Real.** Pure numpy, every round, browser and CLI |
| The five diagnostics and the decision record | **Real.** Same code on both surfaces, with hashed inputs |
| Both model recipes and the bake-off between them | **Real.** `ridge_onehot` against `gp_pca64` over the one-hot block |
| Developability and liability scores | **Real** deterministic calculations, labelled computed throughout |
| Affinity values | **Simulated.** Synthetic landscape with pre-registered parameters |
| The wet lab | **Simulated.** Noise, ~3% failure, censoring, per-round offsets |
| The LIMS | **Staged.** Mock server with a deliberately narrow write path |
| Sequence embeddings | **Not built.** One-hot only; the provider interface exists and `esm_live` is unwired |
| Structure prediction | **Stubbed.** Returns a cached result and says so |
| The agent's reasoning in the browser | **Real Claude** while the daily budget holds; verified replay otherwise |
| The agent's reasoning in the CLI | **Real.** Claude Code runs the diagnosis unaided |
| Rounds run in the browser | **Real.** The same Python, state held in the browser, never written back |

Rows for components that do not exist yet describe what they will be, and the build
status table above says which of them are built.
