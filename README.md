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
.venv/bin/python check.py      # 23 invariant checks, all should pass
```

`.venv/` is gitignored. Everything else needed — including the generated landscape — is
committed, so a fresh clone plus the two commands above reproduces the current state.

**Use `.venv/bin/python`, not `python3`.** The system interpreter has no numpy.

## What runs today

```bash
.venv/bin/python -m data.build_oracle        # regenerate the landscape (deterministic)
.venv/bin/python init_project.py --name demo-trastuzumab --force
.venv/bin/python check.py                    # verify every documented invariant
```

`check.py` is the handoff contract. Every check in it corresponds to a rule in
`CLAUDE.md` or a number recorded in `DECISIONS.md`, so a failure means the state has
drifted from what is documented.

## Build status

| Phase | Deliverable | State |
| --- | --- | --- |
| 1 | Repo skeleton, synthetic oracle, project schema, one-hot encoder, pre-registered parameters | **Done** |
| 2 | `core/surrogate.py`, `acquisition.py`, `simulate_campaign.py` | **Next — this is the gate** |
| 3 | The five pipeline scripts and `SKILL.md` | Not started |
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

### Before starting phase 2

Phase 2 is the real gate. Read `DECISIONS.md` first, then hold these fixed:

- **The threshold is 10.762 pKD and it is already fixed.** It was pre-registered as the
  99th percentile and recorded before any campaign ran. Do not recompute it, do not
  re-pick it, and do not adjust it after seeing a curve.
- **Do not change the landscape or its parameters.** If guided does not separate from
  random, the deliverable is a sentence saying it did not. See non-negotiable 8.
- 20 seeds per arm, plotted as median with an interquartile band.
- Both arms share the round-1 seed batch (a single-mutant scan) and the same 7,294-design
  feasible pool, so the chart measures the model rather than the filter.
- `simulate_campaign.py` is the one and only thing permitted to read landscape values,
  and only to score the diagnostic line. Nothing on a product path may.
- Expect a fair fight, not a walkover: with 1.01% of the pool above threshold and 42
  fresh picks per round, random has roughly a 35% chance per round of stumbling into it.
  Separation should show in rounds-to-threshold; the bands may overlap more than a rigged
  setup would.
- A third arm (guided with naive pooling, no round-4 offset correction) is optional and
  only ships if mis-correcting measurably hurts. If it does not, say so and drop it.

## Repo map

| Path | Contents |
| --- | --- |
| `core/` | Pure numpy, shared by every surface. No network, no printing, no scipy/sklearn/pandas |
| `core/schema.py` | Canonical JSON, content hashing, project directory layout |
| `core/encode.py` | Sequence handling, the one-hot block, Hamming distance |
| `core/scoring.py` | Deterministic developability scores; liabilities counted as *introduced* |
| `core/candidates.py` | Enumeration, constraint enforcement, diversity seed batch |
| `core/project.py` | Template instantiation and project-state accessors |
| `data/` | The simulated laboratory. Never imported by `core/` |
| `data/synthetic.py` | The landscape: additive site effects + pairwise epistasis + one cliff |
| `data/oracle.py` | Noise, ~3% construct failure, censoring, per-round and per-plate offsets |
| `data/build_oracle.py` | Generates and calibrates the landscape, writes the assets |
| `templates/` | One working template, one visible stub |
| `projects/demo-trastuzumab/` | The committed demo project |
| `init_project.py` | Template → project directory. Not part of the round loop |
| `check.py` | Invariant verification. Run it after any phase |

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
