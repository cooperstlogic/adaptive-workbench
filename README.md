# Adaptive Optimization Workbench

A scientist-governed system that takes an antibody lead, learns from each round of
experimental results, and recommends the next batch of variants to test.

**Live demo — Shannon Science:
[adaptive-workbench-iota.vercel.app](https://adaptive-workbench-iota.vercel.app)**
— the real Python runs in your browser. Nothing is sent anywhere.

> ### Everything laboratory here is simulated
>
> The affinity landscape is synthetic, the LIMS is a mock, and the assay is an oracle
> replaying generated values with noise. **Every affinity number in this repository is
> invented.** What the results below show is that the decision loop converges and that its
> judgments are inspectable — not that this method finds better antibodies.
> [What is real and what is staged](#what-is-real-and-what-is-staged) draws the line
> component by component, and [the simulation](#the-simulation-and-how-it-maps-to-a-real-campaign)
> explains what was borrowed from real measurements and what was not.

---

## The idea

Claude Science already offers broad connectors and skills. Building an adaptive optimization
workflow on top of them still takes specialized know-how: the data mappings between a LIMS
and a model, the surrogate and its calibration, the decision logic for what to do when a
round disagrees with the prediction, and an interface a scientist can review it through.
**Templating those four things would make the workflow easier to adopt and to repeat.**

And a template that persists its work accumulates something. The record of objectives,
predictions, experiments and outcomes grows with every round, and it is project-specific in a
way that nothing else in the stack is — the value of the twelfth round depends on the eleven
before it being on disk, in a form the next session can read. That is accumulating value and
natural stickiness, and it is the point of doing this as a layer rather than as a better
prompt.

The layer itself is thin. It is four things:

- **A template** that instantiates a project — declaring the lead, the editable region, the
  objectives and their thresholds, the mutation budget, and which model recipes and
  diagnostics are permitted.
- **A skill** whose scripts read and write that project's state, so round N's choice is a
  function of rounds 1 to N−1's results rather than of what is in the context window.
- **Connectors** that keep the LIMS authoritative for samples, plates and assay results, so
  the workbench never becomes a second system of record.
- **A narrow surface for approving decisions** rather than chatting about them: a batch is
  approved or not, and a flagged round is ruled on with one of four typed verbs bound to code
  paths.

Together they are what lets a model exercise judgment *across* rounds rather than answer one
question at a time.

### The layer has a name: Shannon Science

The web app in this repository is a demonstration of what Claude Science looks like with that
template installed, so its shell deliberately wears the host's interface — this is a layer
*inside* Claude Science rather than a product beside it. **Shannon Science** is what the
deployed site is titled and what its home screen is branded, `Beta` beneath. It is also how
the model in the centre seat is told where it is sitting — the opening of the system prompt
`web/function/ask.mjs` builds, ahead of `SKILL.md` itself:

> You are Claude, seated in a project session of Shannon Science: a thin layer over Claude
> Science that keeps persistent decision state across the experimental rounds of an antibody
> lead-optimization campaign. **The skill below is the same file you would load in Claude Code
> or in Claude Science.** Here its scripts are reachable as tools, and nothing else is.

**This is a prototype built in a day.** The skill, the connectors, the optimization code and
the decision records are real and run in three places. The laboratory underneath them is
simulated, and Shannon Science's outer chrome is a wireframe.

### The two things worth looking at

| | What it shows |
| --- | --- |
| **[The proof chart](#the-chart)** — cumulative best-observed affinity by round, model-guided against a random baseline over 20 seeds per arm | The loop converges, and the machinery works |
| **[The round-4 decision record](#the-decision-record)** — a round comes back ambiguous, an agent forms competing hypotheses, tests them, and a named human rules | Something is reasoning inside it |

Without the second, this is a scheduler calling five scripts in order.

---

## What it is made of: a real skill and two real connectors

Nothing here mocks the extension mechanism. The skill is a `SKILL.md` with seven Python
scripts; the connectors are two MCP stdio servers. The same files load in Claude Code, in
Claude Science, and — through Pyodide — in the browser.

### The skill

`skills/adaptive-optimization/SKILL.md` is the state contract, the round loop, the diagnosis
procedure, and four rules its agent does not break. Seven scripts sit under it, each a thin
wrapper over `core/` that takes `--project <dir> --round <N>` and writes one artifact:

| Step | Script | Writes |
| --- | --- | --- |
| 1 | `generate_candidates.py` | `candidates/pool_NNN.json` — enumeration, and what the constraints removed |
| 2 | `select_batch.py` | `batches/batch_NNN.json` — the recommended batch |
| 3–6 | *the registry connector* | identifiers, the order file, run status, results |
| 7 | `import_round.py` | `evidence/snapshot_NNN.json` — reconciled, and flagged if it looks wrong |
| 8 | `evaluate_prior.py` | `batches/batch_NNN.eval.json` — last round's predictions scored |
| 9 | `fit_surrogates.py` | `models/run_NNN.json` — the two recipes and the bake-off |

Plus two that are not part of the pipeline: `run_diagnostic.py`, which runs one of five
read-only tests on a flagged round, and `record_decision.py`, which writes a decision record
and **refuses any payload that arrives carrying its own numbers.**

The four rules are the interesting part, because they are the ones a scheduler cannot
enforce: never change objectives without approval, never pool measurements across assay
versions without a bridging set, never invent a model recipe outside the registry, and
**never write a number into a decision record that did not come from a named `core/`
function.**

### The connectors

Two MCP stdio servers, each about two hundred lines of which most is docstring.

**`registry` — the LIMS stand-in.** Seven tools, each one call into `lims.py`:

```
submit_batch           Mint construct and sample ids for approved designs; record the round
export_submission      The order file for a submitted round: what the lab receives
check_run_status       Whether a round's assay has reported yet, and when it is expected
pull_assay_results     Assay rows for a round, keyed by sample id
list_designs           Designs the registry holds, with their construct ids
get_construct          One construct record
attach_recommendation  Attach a recommendation id and a link to an existing record

not available, deliberately: create_sample, edit_assay_result, start_workflow, delete_record
```

Those four withheld names are the boundary claim, and it is a check rather than a sentence:
the served tool list does not contain them, asserted from both ends. **The LIMS stays
authoritative** — the workbench's write path attaches a link and nothing more.

**`bioprovider` — the provider stand-in.** Three tools, two of them real:

```
embed_sequences      Real. The one-hot block, hash-identical to core/encode.py
score_properties     Real. The same arithmetic the constraint filter enforces
predict_structures   Stubbed. Returns nulls and says it predicted nothing

backends: local (built) · esm_live (declared and NOT wired — selecting it is an error)
```

`esm_live` returns an error naming what is missing, never one-hot in disguise. A stub that
silently falls back is the failure mode this repository is most careful about.

---

## How the adaptive loop works

Every piece below is a file in `core/`, and none of it is more than a page of numpy.

**The state is a directory of JSON files** that carries forward from round to round: the
designs ordered, the measurements returned, the model fit each time, the batch selected, and
any decision a human ruled on. No database, no server, nothing held in memory between rounds.
*Adaptive* here means exactly one thing — **round N's choice is a function of rounds 1 to
N−1's results**, and that function is written down and hashed.

**The design space is enumerated and filtered before any model runs.** The template declares a
lead (trastuzumab VH), an editable window (8 residues of CDR-H3, `GGDGFYAM`) and a mutation
budget (at most 2). That is finite, so it is written out: **10,261 sequences**, filtered in
code to **7,294 feasible** — 1,625 removed for hydrophobicity, 1,342 for introducing a
chemical liability the parent does not carry. That pool is fixed for the whole campaign, so
both arms of the chart draw from it and the chart measures the model rather than the filter. A
constraint declared in a template is a hard filter applied before optimization, never a
preference suggested to a model.

**The model is ridge regression over a one-hot block, read as Bayesian linear regression.**
Each of the 8 positions gets 20 slots with exactly one set to 1, so the model is never told
that D lies between C and E. It learns **one number per (position, amino acid) pair** — not a
learned abstraction, but 160 coefficients a protein engineer can print out and argue with.
Reading it as Bayesian linear regression is identical arithmetic plus one addition: it returns
a *variance* as well as a mean, so every prediction is `10.4 ± 0.3 pKD`. An exact Gaussian
process over the first 64 principal components competes with it **every round** on held-out
negative log predictive density; `ridge_onehot` has won every round of every seed.

**The next 48 are chosen by expected improvement**, not by predicted mean — scoring by the mean
alone would make the loop chase its own opinion. Against an incumbent of 10.80 pKD, using
`core.acquisition.expected_improvement`:

```
A  confident, barely ahead      mean 10.90  sd 0.05  ->  EI 0.1004
B  unsure, looks worse          mean 10.60  sd 0.50  ->  EI 0.1152
C  confident, clearly ahead     mean 11.20  sd 0.05  ->  EI 0.4000
D  parent-ish, very unsure      mean  9.00  sd 0.60  ->  EI 0.0002
```

**B outranks A while predicting a worse molecule.** A is 0.10 ahead and the model is sure of
it, so it is worth almost exactly 0.10; B looks 0.20 *behind*, but its error bar is wide enough
that it could plausibly come back much better, and that upside is worth more than A's certainty.
That is exploration as arithmetic rather than a heuristic bolted on top — and D shows the other
half, since a design far below the incumbent scores essentially zero however unsure the model
is. Designs are then taken greedily with a diversity penalty on sequence distance, and ties
break on developability margin and then pool order, **never on array order**.

**Six of the 48 wells are not new designs:** 42 fresh picks, 2 controls (the parent, plus the
best design so far re-run to confirm it), 2 replicates from the previous batch chosen to **span
its range**, and 2 exploration slots where the model is least certain.

Those re-measured slots are the point of the whole design. They are the **bridge**: the same
molecules measured twice on different runs, so next round the loop can tell *the assay moved*
apart from *we found something*. An offset you cannot estimate is one you merely suffer. The
best-so-far control is deliberately excluded from the bridge, because a design selected for
reading high will read lower next time whatever the assay did — that measures regression to the
mean, not a run offset.

**The model's honest limit is that it is additive.** It can learn "K at 101 is worth −0.3" and
"Y at 104 is worth +0.2", and will then always predict the double mutant at −0.1. It has no way
to represent *"D at 101 is good only when there is a Y at 104."* That is epistasis, and the model
is structurally blind to it — calibrated rather than accidental, since the landscape targets a
linear R² of 0.60 and realized **0.6008**, putting roughly 40% of the variation in pairwise
interactions the model cannot see.

**The human enters on a flag.** If the fresh designs come back on average **more than 0.5 pKD**
from prediction — a three-fold change in apparent KD and 3.3× the assay's noise, declared in the
template before the campaign runs — the round is flagged and the loop **stops**.

The flag says a round **needs deciding**. It never says which explanation wins: **a run offset
and a genuine activity cliff trip the same statistic identically**, which is the point. Deciding
that a round *looks wrong* is a threshold; deciding *why* is the judgment call, and it is the
only one this build asks an agent to make. Five read-only diagnostics tell them apart, and
**each returns numbers and never a verdict.** An agent chooses which to run and in what order,
and a named human rules.

---

## What it proves

### The chart

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="web/public/assets/campaign-dark.png">
  <img src="web/public/assets/campaign.png" alt="Two panels. Left, cumulative best observed affinity by round for three arms, median with interquartile bands, against a dashed pre-registered threshold at 10.762 pKD. Right, the true affinity of the design each arm's own project state ranks first. Model-guided leads both panels; guided with naive pooling tracks it until the assay version changes at round 4 and then falls behind.">
</picture>

Twenty seeds per arm, six rounds, batch of 48, a shared round-1 single-mutant scan, scored
against the [10.762 pKD threshold](#pre-registered-landscape-parameters) fixed before any of it
ran. Reproduce with `.venv/bin/python simulate_campaign.py`.

| | guided | random | guided, naive pooling |
| --- | --- | --- | --- |
| Mean rounds to threshold | **2.00** | 2.95 | 2.00 |
| Reached threshold by round 6 | 20/20 | 18/20 | 20/20 |
| Final best observed, median | **11.762** | 11.212 | 11.015 |
| Final best landscape, median | **11.674** | 11.105 | 11.674 |

Guided is **never slower than random on any of the twenty paired seeds** and faster on eight, an
exact paired sign test at p = 0.0078. The interquartile bands separate at rounds 2, 5 and 6. The
median guided run reaches the feasible pool's global maximum of 11.674 pKD by round 5; random
plateaus at 11.105.

**The landscape is synthetic.** This shows the decision loop converges. It does not show that
the method finds better antibodies.

**What the third arm costs, which is the panel that matters.** Pooling measurements across the
round-4 assay version change does not make the optimizer *pick* worse designs — its noise-free
selection line reaches the same 11.674. What it does is corrupt the ranking the project holds,
so the arm **advances a genuinely worse molecule in 14 of 20 seeds, a median 0.648 pKD worse — a
four-fold error in the KD of the lead you would take forward.** The mechanism is specific: the
best-so-far design is re-run as a control every round, and pooling its round-4 reading naively
drags its own average down until a worse design outranks it. **The arm demotes its own best
molecule.** And the round that needed a ruling never gets one, so the flag keeps firing: 15 of
20 at round 5 against 3 for the corrected arm.

That is the argument for the bridging set and the ruling, measured rather than asserted.

### The decision record

Round 4 of the committed demo project comes back flagged, and it is genuinely ambiguous —
**nobody engineered it.** A new assay version (v1.3) appears, 42 fresh designs come back a mean
**−2.046 pKD** from where the model put them, interval coverage collapses to **0.07** against
0.80 nominal, and the residual is flat across mutated positions. All five diagnostics return a
number on that snapshot, and between them they say something a single statistic cannot:

| Test | Reading |
| --- | --- |
| `offset_from_controls` | **−1.014 pKD**, se 0.059, bridge of 3. The shared designs sit 0.102 apart against a 0.342 tolerance, so they **agree**: a correction is available |
| `residual_by_plate` | R4P1 −1.872 over 23 designs, R4P2 −2.011 over 23 — a gap of 0.139 pKD at 0.62 standard errors. **Not a plate** |
| `replicate_concordance` | Read-noise scale 0.171 pKD; **none** of 45 designs with two usable reads above the 0.514 tolerance. **Not an unstable read** |
| `residual_by_mutation_class` | Under `--scope fresh`, the cliff's own position, VH 103, sits **+0.214 pKD from every other class** over 10 designs — against a cliff depth of −1.50. **Not the cliff** |
| `calibration_by_region` | Coverage **0.065** against 0.80 nominal. Correcting by the bridge takes it to **0.565**, still short, and leaves **−0.927 pKD** unexplained |

That last line is the round in one number. The offset is real, the bridge is clean, and applying
it accounts for about half of what came back. **A diagnosis that corrects the offset and stops is
wrong about the other half.**

Two things make the record hold. **The writer accepts no numbers**: a proposal names which test
supports which hypothesis, `record_decision.py` runs that test itself and writes what it got
back, and a payload carrying its own `result` is refused. **And a correction cannot cite a ruling
that said something else**: `import_round.py --authority decision_NNN` loads the record and checks
that it exists, is ruled, and recommends the action being taken. `decision_002` says `refit_only`,
so it authorizes no change to any measurement, and the import refuses.

#### What an agent made of it

Round 4's record was written by a **headless Claude Code session given only the skill and the two
connectors**, in a throwaway tree with no documentation at all — because every document in this
repository discusses round 4. It chose its own test order, rejected the plate on 0.139 pKD at
0.62 se, rejected an unstable read on 0 of 45 outside tolerance, and rejected the cliff **with a
reason the library cannot give**: position 102 is 43 of 46 designs, so *the class is the round*
and no contrast exists inside it.

**Then it found something the repository had not.** In one ad hoc cut it wrote itself: **40 of
the 42 fresh designs carry the same substitution, G102L**, which the model had seen in exactly
one measured design ever — the round-3 incumbent `G102L+A105K` at 11.837. An additive one-hot
ridge has no interaction term, so it credited that pair's whole gain to two main effects and
stacked G102L onto 40 new partners. All 40 fell short. **G102L alone buys about +0.26 and not
+1.80 — the incumbent's affinity belongs to the pair.** Round 4 advanced nothing, because the
optimizer spent 40 of 48 wells re-testing one main effect it had a single observation of.

A scheduler calling five scripts produces the flag. **It does not produce that sentence**, and
the sentence is what a scientist would act on.

Two further gates ran under the same conditions: one completed a full round unaided and declined
to sign the batch off under a name that had not reviewed it, and one answered a
`more_evidence_requested` ruling — which is why **the committed round-4 record is two-pass and
still deliberately unruled.** The final verdict is a human act, and it is the visitor's to give.
All three transcripts are in [`gates/`](gates/).

### The same science in the browser

Shannon Science boots Pyodide, **mounts the repository's own modules** into its filesystem, and
runs the round loop against the visitor's own copy of the project. `core/` is never ported to
JavaScript — that fork is the one mistake that would undermine the whole demo.

**It reproduces the campaign's numbers under a different Python and a different numpy.** Round 4
comes back flagged at a mean signed residual of **−2.046272** pKD with a bridge estimate of
**−1.014229**, identical to the committed snapshot; accepting the recommendation takes interval
coverage from 0.065 to **0.565217**, identical to what the decision record claims it would.

**And the browser and the CLI write the same bytes.** `check.py` runs the whole round-4 loop in
Pyodide, then drives the CLI scripts over the same starting state in the same order, and compares
every file: **26 of 28 artifacts are byte-identical.** The two that differ carry the moment a
person ruled and the moments the graph was rewritten. **Not one number differs.** The CLI and the
evaluator agree just as tightly — six rounds, **288 of 288 wells** identical in membership and
order, which is the strongest available statement that the science is implemented once.

**The replayed diagnosis is recomputed, never carried across.** What ships is `decision_004.json`
with every `result`, `source` and `inputs` block stripped out — the claims and the choice of test
for each. The browser hands that to `record_decision.py`, which re-runs all eight tests and writes
the numbers it gets: *8 of 8 results match, 3 of 3 cuts reproduce* is a count the driver made, not
a caption.

**Round 5 flags too, at −0.818 pKD**, and it has no decision record. Only a live model seat can
diagnose it, and that beat is deliberately not in the test harness.

---

## The simulation, and how it maps to a real campaign

### What was borrowed, and what was invented

**The problem is borrowed from the literature; the numbers are not.** The lead is trastuzumab VH,
the editable window is eight CDR-H3 positions, and the mutation budget is two — which is the
combinatorial design of the `trast-1` dataset in
[Bachas et al. 2022](https://www.biorxiv.org/content/10.1101/2022.08.16.504181v1.full), where
8,932 trastuzumab variants spanning up to two substitutions across eight CDR-H3 positions were
measured by a high-throughput cell-sorting assay. Their space excludes cysteine and comes to 9,217
sequences; this one allows all twenty letters, comes to 10,261, and filters cysteine out
downstream as a declared liability.

The shape is the same deliberately, so that **replacing `data/oracle.py` with a loader over real
measurements changes one file and no science.** What is borrowed is the design space. Every
affinity value here is generated by `data/synthetic.py`.

### Why simulate at all

A real campaign is four to six weeks per round. Demonstrating a *multi-round* decision layer
against real assays is a six-month project, and the thing being demonstrated — that decision state
persists correctly across rounds and that judgments are inspectable — does not depend on the
chemistry being real. It depends on the *failure modes* being real, and those are what the
simulation is built to produce:

| What the oracle does | Why it is there |
| --- | --- |
| Gaussian read noise, σ = 0.15 pKD | ~1.4-fold apparent KD error, typical replicate spread for a well-run binding assay |
| Per-round offsets, σ = 0.10 pKD | Run-to-run drift is what the bridging set exists to absorb |
| Per-plate offsets, σ = 0.05 pKD | Within-round variation is typically smaller than between-round drift |
| **An assay version change at round 4**, −0.80 pKD deterministic | A ~6-fold apparent shift on a version change is a thing that happens. At 5.3× the noise σ it is resolvable from a 3-design bridge, which makes the diagnosis defensible rather than a coin flip |
| ~3% construct failure | Typical for a small expression campaign |
| Left-censoring at a detection limit | Some wells come back "below LOD", and `import_round` has to handle them |
| Two reads per design, returned unaveraged | Replicate concordance is a diagnostic, so the rows have to arrive separate |
| LIMS-owned sample ids, plate wells, assay versions | Reconciliation is real work: 96 rows join to 48 designs through the registry's ids |
| **One structure-activity cliff**, depth −1.50 pKD | A deep cliff at an attractive position competes with the offset as an explanation for round 4 — which is what makes the diagnosis a judgment rather than a lookup |

That last pair is the whole design. The assay shift and the cliff **trip the same statistic
identically**, and telling them apart requires choosing which diagnostics to run and reading them
against each other. That is the situation a real campaign produces every few rounds, and it is the
situation this repository exists to put an agent into.

### What a real deployment would change

In rough order of how much each moves, and each a change to one layer:

| Step | Change | What it touches |
| --- | --- | --- |
| 1 | Real measurements: swap `data/oracle.py` for a loader over the `trast-1` release | One file. The design space already matches |
| 2 | Real features: `esm2_t12_35M_UR50D` mean-pooled, PCA to 64 dims, as a second feature block | `data/build_features.py`. The recipe bake-off already exists to arbitrate whether it beats one-hot |
| 3 | A second measured objective (expression), making the problem genuinely multi-objective | Acquisition: expected improvement becomes expected hypervolume improvement |
| 4 | Predicted properties that are neither measured nor exactly computed | The template schema, which today has `source: measured` and `source: computed` and no third category |
| 5 | Generated rather than enumerated candidates, which makes the space open | Everything downstream assumes a fixed, hashable pool. This is the expensive one |
| 6 | A widening mutation budget across rounds | A sixth decision verb — *widen* |

### How this compares to a real lab-in-the-loop

[Frey et al. 2025](https://www.biorxiv.org/content/10.1101/2025.02.19.639050v3.full)
(Genentech / Prescient Design) ran 11 seed antibodies against 4 targets, >1,800 variants over
**four rounds** of generate → predict → rank → assay → retrain, on 4–6 week cycles with SPR
readout. That is the same loop this repository runs, with three orders of magnitude more apparatus
behind it.

| | This build | Lab-in-the-loop (Frey et al.) |
| --- | --- | --- |
| Design space | Closed and enumerable: 10,261 sequences, ≤2 mutations, fixed for all rounds | Open: up to 30,000 designs per lead per round; edit-distance cap **widens** 6 → 8 → 12 across rounds |
| Features | One-hot, 8 × 20 = 160 dimensions | Protein language model embeddings (ESM-2 and Llama-2 architectures, UniRef50 + OAS) |
| Surrogate | Ridge as Bayesian linear regression; exact GP as challenger | Deep ensemble of neural networks. GPs explicitly rejected as computationally prohibitive at their scale |
| Uncertainty | Analytic posterior variance; **interval coverage is a governed artifact checked every round** | Monte Carlo across ensemble members; calibration reported as predicted-vs-measured correlation, not governed |
| Readout and scale | Simulated oracle, 48 wells per round; 288 wells and one target in total | SPR on a Biacore 8K+, ~450 designs per round on 4–6 week cycles; >1,800 variants, 11 seeds, 4 targets |

**Three of our choices show up independently in Frey**, which is the main reason to trust the
shape: the per-round bake-off between model recipes, the split where uncertain properties become
objectives and exact ones become filters, and the decision not to use a Gaussian process — they
reject it for compute, we reject it for calibration.

**One number from Frey belongs next to our chart.** Against a matched random baseline, their ML
arm produced the best binder for **three of five seeds, and the random control won the other
two**. They defend the result on the grounds that the controls ignored developability and
expression, which is fair. It is still the honest calibration for what a guided loop buys on real
chemistry, and it is why the separation reported above is a claim about machinery and not about
chemistry.

**What neither paper has is the part this repository is about.** Frey's Methods describe a LIMS
with plating provenance, a registration system minting unique identifiers, and versioned dataset
artifacts. Neither paper treats an assay version change, a bridging control, a run offset or a
left-censored value as something the *decision* has to survive; neither has a named approver, a
decision record, or a correction that must cite a ruling authorizing it. Round 4 of the demo
project has no counterpart in either. **That is what this layer is for.**

### Pre-registered landscape parameters

**Committed in `8f13010`, 2026-09-19, before any landscape was generated and before
`simulate_campaign.py` had ever run.** Git history is the evidence that the order was kept:
`8f13010` (pre-register) → `473ac01` (generate the landscape) → `945277c` (first campaign). Every
value carries a justification that does not reference the outcome, because picking a threshold
after seeing a curve would make the chart worthless. **The threshold is fixed at 10.762 pKD and is
never recomputed.**

The structure is additive site effects plus pairwise epistasis with one cliff — not an NK model,
because with `max_mutations = 2` only first- and second-order terms are ever reachable from the
parent, so higher-order interactions would be terms that can never fire.

| Parameter | Value | Justification (independent of result) |
| --- | --- | --- |
| Lead | trastuzumab VH, public sequence | The template's declared lead |
| Editable region | 8 residues of CDR-H3 (`GGDGFYAM`), VH `[99, 107)` | Excludes the conserved flanking `W` and the terminal `DY` motif |
| Max mutations | 2 | Template constraint; keeps the pool enumerable at 10,261 |
| Parent pKD | 9.00 | Low-nanomolar, the regime an approved anti-HER2 lead occupies |
| Additive effect scale σ_a | 0.45 pKD | Single-point CDR substitutions typically move affinity by a few tenths of a log with occasional ~1-log effects; σ = 0.45 puts 95% of singles inside ±0.9 |
| Epistasis weight β | calibrated to linear R² = 0.60 | Additive-dominant with a substantial epistatic residual is the regime antibody affinity DMS studies report. β is solved numerically against this **pre-registered number** — a calibration, not a tuning to a result |
| Cliff position | the editable position with the largest maximum additive effect | Stated as a **rule, not an index**, so the seed determines it. Placing the cliff at the most attractive position makes the optimizer walk into it naturally rather than by construction |
| Cliff residues | `{P, D, E, K, R}` | Mechanistically motivated, drawn independently of the additive draw: proline breaks backbone geometry, burying charge at a contact residue is costly |
| Cliff depth | −1.50 pKD | Deep enough to dominate the round-4 offset, so the two explanations genuinely compete |
| Assay noise σ | 0.15 pKD | ~1.4-fold apparent KD error |
| Per-round / per-plate offset σ | 0.10 / 0.05 pKD | Round-to-round drift the bridge absorbs; within-round variation set to half of it |
| Round-4 assay-version shift | −0.80 pKD, deterministic | At 5.3× the noise σ it is resolvable from a 3-design bridge (offset/SE ≈ 9) |
| Construct failure rate | 0.03 | Typical for a small expression campaign |
| Assay reads per design | 2 | Returned as separate rows, never pre-averaged |
| Detection limit | 2nd percentile of the landscape | Censors a few percent of round-1 designs; the round-4 offset pushes more below it |
| **Threshold (the gate)** | **99th percentile of the landscape** | Fixed here, before the first run |
| RNG seed | 20260918 | Fixed so the landscape is reproducible |

Generated 2026-09-19 by `python -m data.build_oracle`, recorded immediately and still before any
campaign run:

| Item | Value |
| --- | --- |
| Build hash | `sha256:c9b2566abc75f0dba893f4c6628c9bb1213dd2921fa4317b8751be03d2ce3318` |
| Candidate space | 10,261 sequences → **7,294 feasible** |
| Solved epistasis weight β | 0.5527 |
| Realized linear R² | **0.6008** (target 0.60) |
| Cliff position | VH index 103, parent residue **F** — selected by the pre-registered rule |
| Detection limit (p2) / **Threshold (p99)** | 6.861 / **10.762** |
| Feasible designs above threshold | 74 of 7,294 — **1.01%** |

**One protocol change, made before the first campaign run and for a stated reason.** Inspecting
landscape values showed a diversity-maximizing seed batch would draw a design above the threshold,
which — since both arms share the round-1 batch — would have made every run reach threshold at
round 1 and measured nothing. The mitigation was authorized in writing beforehand (*start from a
deliberately mediocre seed set… a change to the protocol, and not a change to the landscape after
seeing a curve*) and taken as written: round 1 is now a scan restricted to single mutants. No
single mutant in the feasible pool can reach the threshold (best is 9.919 against 10.762), so
round 1 is **structurally incapable of saturating** — a property of the mutation budget, not a
tuned parameter. The landscape, its parameters, the seed and the threshold did not move.

---

## What is real and what is staged

| Component | Status |
| --- | --- |
| Surrogate fitting, calibration, constraint filtering, batch acquisition | **Real.** Pure numpy, every round, browser and CLI |
| The five pipeline scripts and the round graph | **Real.** Six rounds through the CLI, selecting the same 288 wells as the evaluator |
| The five diagnostics | **Real.** Pure numpy, read-only, and none of them decides anything |
| Both model recipes and the bake-off between them | **Real.** `ridge_onehot` against `gp_pca64` over the one-hot block |
| Developability and liability scores | **Real** deterministic calculations, labelled computed throughout |
| The two connectors | **Real.** MCP stdio, seven tools and three, each one call into `lims.py` or `core/`. `check.py` drives both over the protocol and compares them against the CLI |
| The skill and connectors inside Claude Science | **Real, and exercised end to end.** All eight tools run, the host's kernel executes the pipeline scripts, and the round-4 diagnosis reproduces every number and every input hash |
| The decision record | **Real, and exercised three times.** Round 2 carries a full record with a ruling. Round 4's pass 1 was written by an agent given only the skill and the connectors, its pass 2 by another after a named person sent it back, and it is deliberately unruled |
| The agent's reasoning in the CLI | **Real, and the transcripts are committed.** Three headless Claude Code sessions on `claude-opus-5`; see [`gates/`](gates/) |
| Rounds run in the browser | **Real, and checked against the CLI.** The repository's own modules, mounted into Pyodide byte for byte and imported rather than ported. State lives in the browser and is never written back |
| The browser's tool-call stream | **Real commands.** Each chip is a script that ran against the visitor's copy of the project, with its exit code and both output streams. It is not an animation |
| The agent's reasoning in the browser | **Real when a live seat is available, replayed otherwise, and a badge over the turn says which.** Live: `claude-sonnet-5` behind one stateless function with `SKILL.md` as its system prompt, handing a proposal to `record_decision.py`, which recomputes every number before it writes. Replayed: the committed record's claims stepped through the same component, every test re-run and hash-compared |
| **Affinity values** | **Simulated.** Synthetic landscape with pre-registered parameters; the oracle replays its values with noise. **Every affinity number in every surface is invented**, and this shows the decision loop converging, not that the method finds better antibodies. **This row is where that is said in full** |
| The wet lab | **Simulated.** Noise, ~3% construct failure, censoring, per-round and per-plate offsets |
| The LIMS | **Staged, and reachable over MCP.** `lims.py` mints identifiers, lays out plates, exports orders and rows, and answers whether a run has reported |
| The lab round trip | **Staged, deliberately.** Approving submits the batch and writes the order file, and then stops. Whether the results are back is a separate question put to the registry, refused the first time with the date it is expected — and that refusal is run and shown, not described |
| The lab reporting on demand | **A demo device, labelled *simulated* where it sits.** *Have the lab report now* marks a held run reported. It moves the clock and nothing else. It is not on the registry's tool list, because a registry does not have a button that finishes an assay |
| Sequence embeddings | **Not built.** One-hot only. The provider interface is real and served over MCP; `esm_live` is declared and unwired, and asking for it returns an error naming what is missing |
| Structure prediction | **Stubbed.** `predict_structures` returns nulls and a note saying it predicted nothing. It invents no confidence score, and nothing downstream reads it |
| The ad hoc sandbox | **A guard, not a sandbox, and labelled so in the source.** Model-written numpy runs read-only behind a read-only `open`, an import denylist, a token check and a line budget. The claim is that ad hoc output never enters a code path, which `record_decision.py` enforces on its own |
| The function behind the live seat | **Real, stateless, and not a proxy.** It builds every request itself, accepts only transcripts it signed, and reserves each call's maximum against a daily cap before the call |
| Shannon Science's chrome | **A wireframe.** It renders the layer in the host's own grammar; the panels, the Python, the state and the hashes inside it are real and are running in your tab. The rail's host-only items are drawn and inert, with a tooltip saying so |
| The proof chart | **Real, and the evaluator's.** Twenty simulated campaigns per arm, drawn as the *template's* validation — never on a project's own progress chart, which draws only what that project measured |
| Round dates in the shipped campaign | **Display-level.** The round graph's `updated` stamps are spread over about six weeks. No simulated date is written into a project artifact and no measurement moves |
| The four other projects on the home screen | **Scenery, and empty.** Plausible titles with no template and no content, so the list reads like a workspace. Opening one shows exactly what it is |
| The second template | **A visible stub.** `templates/enzyme-thermostability/` declares itself and is not wired |

---

## Using it in Claude Science

Claude Science is a local application, so it runs the same Python stdio connectors Claude Code
runs. What it has no single installer for is the *bundle* — the skill and the two connectors go in
as three separate acts, one of which is a hand-written config file. **Every step below has been
run.**

**1. The skill, once.** `Settings > Credentials` takes a fine-grained GitHub token with the
resource owner set to the organization that owns the repository and `Contents: Read-only`. Then
`Settings > Skills > Add skill > Import from GitHub`. The host reads
`.claude-plugin/marketplace.json`, resolves `skills/adaptive-optimization` out of it, and records
the commit it came from beside the copy it keeps.

**2. Each connector, by hand.** `Settings > Connectors > Add connector > Local command`, then a
name and one command line — there is no separate arguments field.

| Name | Command |
| --- | --- |
| `registry` | `python /path/to/adaptive-workbench/connectors/registry_server.py` |
| `bioprovider` | `python /path/to/adaptive-workbench/connectors/bioprovider_server.py` |

**`python` stays bare.** The host resolves it to its own bundled environment; an absolute path to
this repo's `.venv` is refused before the process starts.

**3. The sandbox grant, once.** The connectors are files in this repository, and the MCP sandbox
cannot see this repository. Write `~/.claude-science/config.toml`:

```toml
[sandbox]
user_read_paths  = ["/path/to/adaptive-workbench"]
user_write_paths = ["/path/to/adaptive-workbench/lims_store"]
```

Write is granted to exactly one directory — the mock LIMS's own store. Reads and writes are gated
separately, so a read grant alone loads the tools and then fails on the first `submit_batch`.
**The file is read once at startup**, so quit the app from the menu bar icon and relaunch; closing
the browser tab is not enough. Then `registry` lists its seven tools and `bioprovider` its three.

### Four failures, each of which hid the next

Only the first and the last say what is wrong, which is why they are written down.

| What you see | What it is |
| --- | --- |
| `sandbox-exec: execvp() of '…/.venv/bin/python' failed: Operation not permitted` | The sandbox will not exec a binary in your home directory. Use the bare name `python` |
| Tools load forever; nothing in any log | The command box held an interpreter and no script, so a bare Python read the JSON-RPC stream as a program and answered nothing. **A missing argument produces no error and no timeout** |
| `ModuleNotFoundError: No module named 'mcp.server.mcpserver'` | The host's environment carries `mcp` 1.x; this repo's `.venv` carries 2.x, where `FastMCP` was renamed `MCPServer`. Both connectors now import whichever is present |
| `… exists on this machine but is not visible inside the MCP sandbox` | The `config.toml` grant above, and a restart |

`~/.claude-science/mcp/local-mcp.json` records what the dialog actually saved, and it identified
two of the four faults faster than the interface did. **Check the app's own state before the
docs.**

### What a template would add, tested against the product

Installing into the host is the only way to find out which of this layer's claims are real and
which Claude Science already covers. Four were written down beforehand and then audited against
the product; three survived, each narrower than it was written:

| Claimed contribution | Verdict |
| --- | --- |
| A ruling has no type | **Survives, narrowed.** The host has scoped, revocable approval for folder access, code execution and each connector tool. It gates *access*, not *decisions*: no typed decision, no verbs bound to code paths, no hashed evidence, no `if_wrong` |
| A round graph has nowhere to render | **Survives.** The rail lists chat threads named after what was asked. A campaign is a round graph and there is no view of one |
| Traceability is an after-the-fact check | **Survives, heavily narrowed.** The host records skill provenance to the commit. What survives is only this: it versions the *skill*, and nothing versions the *number* back to the function and input hash that made it |
| No project instantiation from a declaration | **Survives, but under-tested.** No template was instantiated in the host, so this rests on the product's shape rather than on an experiment — and nothing in this build leans on it |

Three more were found that had not been claimed, and two are stronger than the four above: **a
connector cannot declare what it needs** (interpreter, code location, writable state — three
manual acts and an undocumented TOML key), **the connector sandbox and the agent sandbox hold
separate grants** (a connector wrote a CSV the agent in the same session could not read), and **a
local-command connector with a missing argument fails silently** rather than timing out.

What the host already does well is recorded beside them, because an audit that only finds fault is
not an audit: local stdio connectors run, approval carries four scopes, skills import from a
private repository with their commit, and the kernel reproduced every number.

## Using it in Claude Code

`.mcp.json` registers both connectors, so opening this repo connects them with no setup. To
install the bundle elsewhere:

```bash
claude plugin marketplace add /path/to/adaptive-workbench
claude plugin install adaptive-optimization@adaptive-workbench
```

Both commands have been run; from an unrelated directory `claude mcp list` then reports
`plugin:adaptive-optimization:registry` and `:bioprovider` as connected. The plugin needs the
`.venv` beside it, because the connectors are Python.

## Running it locally

Not the focus — the deployed site runs everything without a checkout — but the whole repository
reproduces from a fresh clone. numpy is the only dependency of `core/`, and that is a design
constraint rather than an oversight: `core/` is the part an audience is invited to read.
matplotlib is an *evaluator* dependency and the MCP SDK a *connector* dependency.

```bash
python3.12 -m venv .venv
.venv/bin/pip install numpy matplotlib mcp
.venv/bin/python check.py                      # 198 invariant checks, ~40 s

# The evaluator — the proof chart, 20 seeds across 3 arms, ~35 s
.venv/bin/python simulate_campaign.py

# The product path — the same science through the CLI
.venv/bin/python init_project.py --name demo-trastuzumab --team d.webster --force
.venv/bin/python run_rounds.py --rounds 4 --approved-by d.webster

# The judgment a scheduler cannot make, which is what the skill is for
S=skills/adaptive-optimization/scripts
.venv/bin/python $S/run_diagnostic.py  --project projects/demo-trastuzumab --round 4 \
    --test calibration_by_region --offset bridge        # read-only, writes nothing
.venv/bin/python $S/record_decision.py --project projects/demo-trastuzumab --round 2 \
    --rule accepted --by d.webster --note "..."         # a named human disposes

# The connectors, and the registry read the lab round trip is built on
.venv/bin/python connectors/registry_server.py --tools
.venv/bin/python lims.py release --project projects/demo-trastuzumab --round R4  # simulated

# Shannon Science
cd web && npm install && npm run sync && npm run dev    # http://localhost:5173
```

Use `.venv/bin/python`, not `python3` — the system interpreter has no numpy. `run_rounds.py` is
a deliberately dumb scheduler: it prints every command it runs and **stops** the moment a round
is flagged. `npm run sync` copies `core/`, `data/`, `lims.py` and the seven skill scripts into
`web/public/workbench/` **byte for byte** with a sha256 per file, and `check.py` fails if any
copy drifts — so **re-run `python web/bundle.py` after touching anything the browser executes.**
The live model seat needs an `ANTHROPIC_API_KEY`; without one the page stays in verified replay
and says so. The gates re-run with `gates/run_gate.sh round4`, `round1` or `round4-pushback`.

---

## Repo map

| Path | Contents |
| --- | --- |
| `core/` | Pure numpy, shared by every surface. No network, no printing, no scipy/sklearn/pandas. `encode`, `surrogate`, `acquisition`, `reconcile`, `diagnostics`, `candidates`, `scoring`, `schema`, `project` |
| `skills/adaptive-optimization/` | `SKILL.md` and the seven scripts: five pipeline steps plus `run_diagnostic.py` and `record_decision.py` |
| `connectors/` | `registry_server.py` (seven tools over MCP stdio) and `bioprovider_server.py` (three). Not `mcp/`, which would shadow the SDK |
| `data/` | The simulated laboratory. **Never imported by `core/`.** `synthetic.py` is the landscape, `oracle.py` the assay |
| `lims.py` | The mock LIMS. Mints identifiers, owns the plate layout, holds the oracle |
| `templates/` | One working template, one visible stub |
| `projects/demo-trastuzumab/` | The committed demo project, at round 4 with the round deliberately unruled |
| `simulate_campaign.py` | The evaluator. **The only thing permitted to read landscape values** |
| `check.py` | 198 invariant checks. Run it before and after any change |
| `gates/` | The three agent gates: the transcripts, and the script that re-runs them |
| `web/bundle.py` | Copies the repository into the browser's bundle and proves the derivation by replaying round 4 |
| `web/function/ask.mjs` | The one function: a stateless model turn. Builds every request itself and refuses what it did not sign |
| `web/src/` | The shell. React, a 60-line hash router, no state library, no charting library |

`CLAUDE.md` holds the conventions anyone changing this code needs — what `core/` may depend on,
why the science must stay implemented once, and which numbers are pre-registered and fixed.
Numbered `decision NNN` references in source comments point at a build decision log that was
removed once the build finished; it remains in git history.
