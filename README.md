# Adaptive Optimization Workbench

**A prototype of a decision layer that sits on top of Claude Science and holds the state of
a multi-round lab campaign.** It takes an antibody lead, learns from each round of
experimental results, and recommends the next batch of variants to test.

## What this is, in sixty seconds

Optimizing an antibody is iterative. You pick ~48 variants, express them, measure how
tightly each binds, learn what that tells you, and pick the next 48. A real cycle takes four
to six weeks, and a campaign is six or more of them. **The hard part is not any single
round — it is that round 6 has to remember what rounds 1 through 5 meant**, including the
rounds where the assay drifted, a plate failed, or the results disagreed with the model and
somebody had to decide why.

This repository is one answer to that, built as three things that share one codebase:

| | What it is |
| --- | --- |
| **A skill** | `SKILL.md` plus seven Python scripts that read and write a project's state on disk. Loads in Claude Code and in Claude Science |
| **Two MCP connectors** | A registry (the LIMS) and a bioprovider (features and property scores), served over MCP stdio. Real servers, real protocol |
| **A web app** | The same Python running in your browser via Pyodide, wearing the Claude Science interface, with a model in the centre seat |

**The web app is a functional agentic system, not a mockup.** Given a round that came back
wrong, a real model chooses which diagnostic to run next, calls real tools that execute real
Python against real project files, writes short numpy analyses when the library has no test
for its question, and hands back a proposal a named human rules on. Nothing is scripted and
nothing is animated.

**It is also a toy.** The laboratory underneath it is simulated: the affinity landscape is
invented, the LIMS is a mock, the assay is an oracle replaying generated values with noise,
and the sequence representation is the simplest one that works rather than a real protein
language model. **Every affinity number in this repository is fabricated.** What the results
show is that the decision loop converges and that its judgments are inspectable — not that
this method finds better antibodies.

Both of those sentences are meant literally, and [What is real and what is
staged](#what-is-real-and-what-is-staged) draws the line component by component.

### The two things worth looking at

| | What it shows |
| --- | --- |
| **[The chart](#the-chart)** — cumulative best-observed affinity by round, model-guided against a random baseline over 20 seeds per arm | The loop converges, and the machinery works |
| **[The round-4 decision record](#the-decision-record)** — a round comes back ambiguous, an agent forms competing hypotheses, tests them, and a named human rules | Something is reasoning inside it |

---

## Contents

- [The idea](#the-idea) — what the layer is, and why it is thin
- [What it is made of](#what-it-is-made-of) — the skill, and the two connectors
- [How it decides what to test next](#how-it-decides-what-to-test-next) — the model, and why one-hot is a stand-in for ESM-2
- [What it proves](#what-it-proves) — the chart, the decision record, and the browser
- [The simulation](#the-simulation-and-how-it-maps-to-a-real-campaign) — why it is synthetic, and how it maps to a real campaign
- [Pre-registered parameters](#pre-registered-landscape-parameters) — the landscape, fixed before anything ran
- [What is real and what is staged](#what-is-real-and-what-is-staged)
- [Using it in Claude Science](#using-it-in-claude-science) · [in Claude Code](#using-it-in-claude-code) · [locally](#running-it-locally)
- [Repo map](#repo-map)

---

## The idea

Claude Science already offers broad connectors and skills. Building an adaptive optimization
workflow on top of them still takes specialized know-how: the data mappings between a LIMS
and a model, the surrogate and its calibration, the decision logic for what to do when a round
disagrees with the prediction, and an interface a scientist can review it through.
**Templating those four things would make the workflow easier to adopt and to repeat**, and
the record they leave behind — objectives, predictions, experiments, outcomes — is worth more
at round twelve than at round one.

The layer is thin. It is a **template** that instantiates a project, declaring the lead, the
editable region, the objectives and their thresholds and which model recipes and diagnostics
are permitted; a **skill** whose scripts read and write that project's state, so round N's
choice is a function of rounds 1 to N−1's results rather than of what is in the context
window; **connectors** that keep the LIMS authoritative, so the workbench never becomes a
second system of record; and **a narrow surface for approving decisions** rather than chatting
about them — a batch is approved or not, and a flagged round is ruled on with one of four
typed verbs bound to code paths.

Together they are what lets a model exercise judgment *across* rounds rather than answer one
question at a time.

The app is called **Shannon Science**, and its shell deliberately wears the host's interface
because this is a layer *inside* Claude Science rather than a product beside it. That is also
how the model in the centre seat is told where it is sitting, in the opening of the system
prompt `web/function/ask.mjs` builds ahead of `SKILL.md` itself:

> You are Claude, seated in a project session of Shannon Science: a thin layer over Claude
> Science that keeps persistent decision state across the experimental rounds of an antibody
> lead-optimization campaign. **The skill below is the same file you would load in Claude Code
> or in Claude Science.** Here its scripts are reachable as tools, and nothing else is.

---

## What it is made of

Nothing here mocks the extension mechanism. The skill is a `SKILL.md` with seven Python
scripts; the connectors are two MCP stdio servers. The same files load in Claude Code, in
Claude Science, and — through Pyodide — in the browser.

### The skill

`skills/adaptive-optimization/SKILL.md` is the state contract, the round loop, the diagnosis
procedure, and four rules its agent does not break. Seven scripts sit under it, each a thin
wrapper over `core/` taking `--project <dir> --round <N>` and writing one artifact. Five are
the pipeline — `generate_candidates` → `select_batch` → *(the registry: submit, order, wait,
pull)* → `import_round` → `evaluate_prior` → `fit_surrogates` — and two are not:
`run_diagnostic.py`, which runs one of five read-only tests on a flagged round, and
`record_decision.py`, which writes a decision record and **refuses any payload that arrives
carrying its own numbers.**

The four rules are the interesting part, because they are the ones a scheduler cannot enforce:
never change objectives without approval, never pool measurements across assay versions without
a bridging set, never invent a model recipe outside the registry, and **never write a number
into a decision record that did not come from a named `core/` function.**

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

**`bioprovider` — the provider stand-in.** Three tools. `embed_sequences` and
`score_properties` are real and hash-identical to `core/encode.py` and `core/scoring.py`;
`predict_structures` is stubbed, returns nulls, and says it predicted nothing. Its `esm_live`
backend is declared and **not wired** — asking for it returns an error naming what is missing,
never one-hot in disguise. A stub that silently falls back is the failure mode this repository
is most careful about.

---

## How it decides what to test next

**In one paragraph.** Everything measured so far trains a model that maps a sequence to a
predicted binding affinity *with an error bar*. That model then scores every candidate
nobody has measured yet, and the next batch is chosen to maximize **expected improvement** —
which balances "this looks good" against "nobody knows what this does, and it could be
great." The batch is not the 48 highest predictions; it is the 48 that buy the most
information about where the optimum is. A handful of wells are spent re-measuring molecules
from the previous round, so the next round can tell *the instrument moved* apart from *we
found something*.

Underneath that, three pieces:

**1. The design space is enumerated and filtered before any model runs.** The template
declares a lead (trastuzumab VH), an editable window (8 residues of CDR-H3) and a mutation
budget (at most 2) — finite, so it is written out: **10,261 sequences**, filtered in code to
**7,294 feasible**. A constraint declared in a template is a hard filter applied before
optimization, never a preference suggested to a model.

**2. The sequence becomes numbers — and this is the toy part.** Each of the 8 editable
positions gets 20 slots, one per amino acid, with exactly one set to 1. That is **one-hot
encoding**: 160 numbers per design, and the simplest possible way to hand a sequence to a
model. Ridge regression over that block then learns **one coefficient per (position, amino
acid) pair** — 160 numbers a protein engineer can print out and argue with. Read as Bayesian
linear regression it is identical arithmetic plus one addition: it returns a *variance* as
well as a mean, so every prediction is `10.4 ± 0.3 pKD`.

> #### What a real system would put here instead
>
> One-hot encoding knows nothing about chemistry. To it, lysine and arginine — two positively
> charged residues that often substitute for each other freely — are exactly as unrelated as
> lysine and tryptophan. Every amino acid is an isolated symbol, so the model can only learn
> effects it has directly observed at that exact position.
>
> **A real deployment replaces this block with a protein language model embedding** — ESM-2
> or similar, trained on hundreds of millions of natural protein sequences. Such a model
> turns a sequence into a vector that already encodes which substitutions are chemically
> interchangeable, which are structurally plausible in a given local context, and what
> hundreds of millions of years of evolution have tolerated at homologous positions.
> Sequences that behave similarly sit near each other in that space.
>
> The practical difference is generalization. A one-hot linear model is **structurally
> incapable of representing epistasis** — it can learn "K at 101 is worth −0.3" and "Y at 104
> is worth +0.2", and will then always predict the double mutant at −0.1. It has no way to
> say *"D at 101 is good only when there is a Y at 104."* An embedding model can generalize
> to combinations it has never seen, because it is reasoning over a learned similarity
> structure rather than over isolated indicator variables.
>
> That limit is calibrated rather than accidental here: the landscape targets a linear R² of
> 0.60 and realized **0.6008**, so roughly 40% of the variation lives in pairwise interactions
> the model provably cannot see. The loop has to work anyway, which is the point — **a
> decision layer that only works when the model is right is not a decision layer.**
>
> One-hot is used here because `core/` is meant to be read and argued with, a 150 MB model
> download is weight on a cold visit to a public URL, and the thing being demonstrated is the
> decision layer rather than the representation. **The swap is a one-layer change**:
> `core/surrogate.py` already runs a per-round bake-off between recipes on held-out predictive
> likelihood, so adding an ESM-2 feature block means the system adopts it if and only if it
> wins — which is exactly how you would want that decision made.

**3. The next 48 are chosen by expected improvement**, not by predicted mean — scoring by the
mean alone would make the loop chase its own opinion. Against an incumbent of 10.80 pKD:

```
A  confident, barely ahead      mean 10.90  sd 0.05  ->  EI 0.1004
B  unsure, looks worse          mean 10.60  sd 0.50  ->  EI 0.1152
C  confident, clearly ahead     mean 11.20  sd 0.05  ->  EI 0.4000
D  parent-ish, very unsure      mean  9.00  sd 0.60  ->  EI 0.0002
```

**B outranks A while predicting a worse molecule.** A is 0.10 ahead and the model is sure of
it, so it is worth almost exactly 0.10; B looks 0.20 *behind*, but its error bar is wide enough
that it could plausibly come back much better. That is exploration as arithmetic rather than a
heuristic bolted on top — and D shows the other half, since a design far below the incumbent
scores essentially zero however unsure the model is.

**4. Six of the 48 wells are not new designs:** 42 fresh picks, 2 controls, 2 replicates from
the previous batch chosen to span its range, and 2 exploration slots. Those re-measured slots
are the **bridge** — the same molecules measured twice on different runs, so next round the
loop can separate an assay shift from a real gain. An offset you cannot estimate is one you
merely suffer.

**5. The human enters on a flag.** If the fresh designs come back on average **more than 0.5
pKD** from prediction — a three-fold change in apparent KD, declared in the template before the
campaign runs — the round is flagged and the loop **stops**. The flag says a round needs
deciding; it never says which explanation wins, because **a run offset and a genuine activity
cliff trip the same statistic identically.** Deciding that a round *looks wrong* is a
threshold; deciding *why* is the judgment call, and it is the only one this build asks an agent
to make. Five read-only diagnostics tell them apart, and each returns numbers and never a
verdict.

---

## What it proves

### The chart

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="web/public/assets/campaign-dark.png">
  <img src="web/public/assets/campaign.png" alt="Two panels. Left, cumulative best observed affinity by round for three arms, median with interquartile bands, against a dashed pre-registered threshold at 10.762 pKD. Right, the true affinity of the design each arm's own project state ranks first. Model-guided leads both panels; guided with naive pooling tracks it until the assay version changes at round 4 and then falls behind.">
</picture>

Twenty seeds per arm, six rounds, batch of 48, scored against the
[10.762 pKD threshold](#pre-registered-landscape-parameters) fixed before any of it ran.

| | guided | random | guided, naive pooling |
| --- | --- | --- | --- |
| Mean rounds to threshold | **2.00** | 2.95 | 2.00 |
| Reached threshold by round 6 | 20/20 | 18/20 | 20/20 |
| Final best observed, median | **11.762** | 11.212 | 11.015 |

Guided is **never slower than random on any of the twenty paired seeds** and faster on eight, an
exact paired sign test at p = 0.0078. **The landscape is synthetic** — this shows the decision
loop converges, not that the method finds better antibodies.

**The third arm is the one that matters.** It is identical to guided except that it pools
measurements across the round-4 assay version change instead of correcting for it. That does not
make the optimizer *pick* worse designs — its noise-free selection line reaches the same
maximum. What it corrupts is the ranking the project holds, so the arm **advances a genuinely
worse molecule in 14 of 20 seeds, a median 0.648 pKD worse — a four-fold error in the KD of the
lead you would take forward.** The best-so-far design is re-run as a control every round, and
pooling its round-4 reading naively drags its own average down until a worse design outranks it:
**the arm demotes its own best molecule.** That is the argument for the bridging set and the
ruling, measured rather than asserted.

### The decision record

Round 4 of the committed demo project comes back flagged, and it is genuinely ambiguous —
**nobody engineered it.** A new assay version appears, 42 fresh designs come back a mean
**−2.046 pKD** from where the model put them, and interval coverage collapses to **0.07**
against 0.80 nominal. All five diagnostics return a number, and between them they say
something a single statistic cannot:

| Test | Reading |
| --- | --- |
| `offset_from_controls` | **−1.014 pKD**, se 0.059, bridge of 3. The shared designs agree with each other, so a correction is available |
| `residual_by_plate` | R4P1 −1.872, R4P2 −2.011 — a gap of 0.139 pKD at 0.62 standard errors. **Not a plate** |
| `replicate_concordance` | Read-noise scale 0.171 pKD; **none** of 45 designs above the 0.514 tolerance. **Not an unstable read** |
| `residual_by_mutation_class` | Under `--scope fresh`, the cliff's own position sits **+0.214 pKD from every other class** — against a cliff depth of −1.50. **Not the cliff** |
| `calibration_by_region` | Coverage **0.065** against 0.80 nominal. Correcting by the bridge takes it to **0.565**, still short, leaving **−0.927 pKD** unexplained |

That last line is the round in one number. The offset is real and the bridge is clean, but
applying it accounts for about half of what came back. **A diagnosis that corrects the offset
and stops is wrong about the other half.**

Two things make the record hold. **The writer accepts no numbers**: a proposal names which
test supports which hypothesis, `record_decision.py` runs that test itself and writes what it
got back, and a payload carrying its own `result` is refused. **And a correction cannot cite
a ruling that said something else**: `import_round.py --authority decision_NNN` checks that
the record exists, is ruled, and recommends the action being taken.

#### What an agent made of it

Round 4's record was written by a **headless Claude Code session given only the skill and the
two connectors**, in a throwaway tree with no documentation at all — because every document in
this repository discusses round 4. It chose its own test order, rejected the plate and the
unstable read on the evidence above, and rejected the cliff **with a reason the library cannot
give**: one position accounts for 43 of 46 designs, so *the class is the round*.

**Then it found something the repository had not.** In one ad hoc analysis it wrote itself:
**40 of the 42 fresh designs carry the same substitution, G102L**, which the model had seen in
exactly one measured design ever — the round-3 incumbent `G102L+A105K` at 11.837. An additive
one-hot ridge has no interaction term, so it credited that pair's whole gain to two main
effects and stacked G102L onto 40 new partners. All 40 fell short. **G102L alone buys about
+0.26 and not +1.80 — the incumbent's affinity belongs to the pair.** Round 4 advanced
nothing, because the optimizer spent 40 of 48 wells re-testing one main effect it had a
single observation of. That is also the epistasis limit above, caught in the wild by the system that has it. 

Two further gates ran under the same conditions: one completed a full round unaided and declined
to sign the batch off under a name that had not reviewed it, and one answered a
`more_evidence_requested` ruling — which is why **the committed round-4 record is two-pass and
still deliberately unruled.** Transcripts in [`gates/`](gates/).

### The same science in the browser

The web app boots Pyodide, **mounts the repository's own modules** into its filesystem, and
runs the round loop against the visitor's own copy of the project. `core/` is never ported to
JavaScript — that fork is the one mistake that would undermine the whole claim.

**It reproduces the campaign's numbers under a different Python and a different numpy**, and
**the browser and the CLI write the same bytes**: `check.py` runs the whole round-4 loop in
Pyodide, drives the CLI scripts over the same starting state, and compares every file — **26 of
28 artifacts are byte-identical**, the two exceptions carrying only timestamps. Not one number
differs. The CLI and the evaluator agree just as tightly, selecting **288 of 288 wells**
identically across six rounds, which is the strongest available statement that the science is
implemented once.

**Without a live model seat the diagnosis is replayed — and recomputed, never carried across.**
What ships is `decision_004.json` with every result and input hash stripped out, the claims
only. The browser hands that to `record_decision.py`, which re-runs all eight tests and writes
the numbers it gets: *8 of 8 results match, 3 of 3 cuts reproduce* is a count the driver made,
not a caption.

**Round 5 flags too, at −0.818 pKD**, and it has no decision record. Only a live model seat
can diagnose it, and that beat is deliberately not in the test harness.

---

## The simulation, and how it maps to a real campaign

**The problem is borrowed from the literature; the numbers are not.** The lead is trastuzumab
VH, the editable window is eight CDR-H3 positions, and the mutation budget is two — which is
the combinatorial design of the `trast-1` dataset in
[Bachas et al. 2022](https://www.biorxiv.org/content/10.1101/2022.08.16.504181v1.full), where
8,932 trastuzumab variants spanning up to two substitutions across eight CDR-H3 positions were
measured by a high-throughput assay. The shape is the same deliberately, so that **replacing
`data/oracle.py` with a loader over real measurements changes one file and no science.** What
is borrowed is the design space. Every affinity value is generated by `data/synthetic.py`.

### Why simulate at all

A real campaign is four to six weeks per round, so demonstrating a *multi-round* decision
layer against real assays is a six-month project. And the thing being demonstrated — that
decision state persists correctly across rounds and that judgments are inspectable — does not
depend on the chemistry being real. It depends on the *failure modes* being real, and those
are what the simulation is built to produce:

| What the oracle does | Why it is there |
| --- | --- |
| Gaussian read noise, σ = 0.15 pKD | ~1.4-fold apparent KD error, typical replicate spread for a well-run binding assay |
| Per-round and per-plate offsets | Run-to-run drift is what the bridging set exists to absorb |
| **An assay version change at round 4**, −0.80 pKD | A ~6-fold apparent shift on a version change happens. At 5.3× the noise σ it is resolvable from a 3-design bridge, which makes the diagnosis defensible rather than a coin flip |
| ~3% construct failure, and left-censoring at a detection limit | Some wells never express and some come back "below LOD". `import_round` has to handle both |
| Two reads per design, returned unaveraged | Replicate concordance is a diagnostic, so the rows have to arrive separate |
| LIMS-owned sample ids, plate wells, assay versions | Reconciliation is real work: 96 rows join to 48 designs through the registry's ids |
| **One structure-activity cliff**, depth −1.50 pKD | A deep cliff at an attractive position competes with the offset as an explanation for round 4 |

That last pair is the whole design. The assay shift and the cliff **trip the same statistic
identically**, and telling them apart requires choosing which diagnostics to run and reading
them against each other. That is what a real campaign produces every few rounds, and it is the
situation this repository exists to put an agent into.

### What a real deployment would change

| Step | Change | What it touches |
| --- | --- | --- |
| 1 | Real measurements: swap `data/oracle.py` for a loader over the `trast-1` release | One file. The design space already matches |
| 2 | **Real features: an ESM-2 embedding block** beside the one-hot one | `data/build_features.py`. The bake-off already arbitrates whether it wins |
| 3 | A second measured objective (expression), making the problem multi-objective | Acquisition: expected improvement becomes expected hypervolume improvement |
| 4 | Predicted properties that are neither measured nor exactly computed | The template schema, which today has `measured` and `computed` and no third category |
| 5 | Generated rather than enumerated candidates | Everything downstream assumes a fixed, hashable pool. This is the expensive one |
| 6 | A widening mutation budget across rounds | A sixth decision verb — *widen* |

### How this compares to a real lab-in-the-loop

[Frey et al. 2025](https://www.biorxiv.org/content/10.1101/2025.02.19.639050v3.full)
(Genentech / Prescient Design) ran 11 seed antibodies against 4 targets, >1,800 variants over
**four rounds** of generate → predict → rank → assay → retrain, on 4–6 week cycles with SPR
readout. That is the same loop this repository runs, with three orders of magnitude more
apparatus behind it.

| | This build | Lab-in-the-loop (Frey et al.) |
| --- | --- | --- |
| Design space | Closed: 10,261 sequences, ≤2 mutations, fixed for all rounds | Open: up to 30,000 designs per lead per round; edit-distance cap **widens** 6 → 8 → 12 |
| Features | One-hot, 160 dimensions | Protein language model embeddings (ESM-2 and Llama-2 architectures) |
| Surrogate | Ridge as Bayesian linear regression; exact GP as challenger | Deep ensemble of neural networks. GPs rejected as computationally prohibitive at their scale |
| Uncertainty | Analytic posterior variance; **coverage is a governed artifact checked every round** | Monte Carlo across ensemble members; calibration reported, not governed |
| Readout and scale | Simulated oracle; 288 wells, one target | SPR on a Biacore 8K+, ~450 designs per round; >1,800 variants, 11 seeds, 4 targets |

**Three of our choices show up independently in Frey**, which is the main reason to trust the
shape: the per-round bake-off between model recipes, the split where uncertain properties
become objectives and exact ones become filters, and the decision not to use a Gaussian
process — they reject it for compute, we reject it for calibration.

**One number from Frey belongs next to our chart.** Against a matched random baseline, their ML
arm produced the best binder for **three of five seeds, and the random control won the other
two** — the honest calibration for what a guided loop buys on real chemistry, and why the
separation above is a claim about machinery and not about molecules.

**What neither paper has is the part this repository is about.** Frey's Methods describe a
LIMS with plating provenance and versioned dataset artifacts. But neither paper treats an
assay version change, a bridging control, a run offset or a left-censored value as something
the *decision* has to survive; neither has a named approver, a decision record, or a
correction that must cite a ruling authorizing it. **That is what this layer is for.**

### Pre-registered landscape parameters

**Committed in `8f13010`, before any landscape was generated and before `simulate_campaign.py`
had ever run.** Commit order is the evidence the sequence was kept: `8f13010` (pre-register) →
`473ac01` (generate the landscape) → `945277c` (first campaign). Those commits are on the
**`build-history`** tag — `git log build-history` — because this branch was squashed to a single
commit and the ordering is the one piece of history that is evidence rather than chronicle.
Every value carries a justification that does not reference the outcome, because picking a
threshold after seeing a curve would make the chart worthless. **The threshold is fixed at
10.762 pKD and is never recomputed.**

The structure is additive site effects plus pairwise epistasis with one cliff — not an NK
model, because with `max_mutations = 2` only first- and second-order terms are ever reachable
from the parent, so higher-order interactions would be terms that can never fire.

| Parameter | Value | Justification (independent of result) |
| --- | --- | --- |
| Lead, editable region | trastuzumab VH; 8 residues of CDR-H3, VH `[99, 107)` | Excludes the conserved flanking `W` and the terminal `DY` motif |
| Max mutations | 2 | Keeps the pool enumerable at 10,261 |
| Parent pKD | 9.00 | Low-nanomolar, the regime an approved anti-HER2 lead occupies |
| Additive effect scale σ_a | 0.45 pKD | Single-point CDR substitutions typically move affinity a few tenths of a log; σ = 0.45 puts 95% of singles inside ±0.9 |
| Epistasis weight β | calibrated to linear R² = 0.60 | Additive-dominant with a substantial epistatic residual is the regime antibody DMS studies report. β is solved against this **pre-registered number** — a calibration, not a tuning to a result |
| Cliff position | the editable position with the largest maximum additive effect | Stated as a **rule, not an index**, so the seed determines it. Placing the cliff at the most attractive position makes the optimizer walk into it naturally |
| Cliff residues, depth | `{P, D, E, K, R}`; −1.50 pKD | Proline breaks backbone geometry and burying charge at a contact residue is costly. Deep enough to dominate the round-4 offset, so the two explanations genuinely compete |
| Assay noise σ | 0.15 pKD | ~1.4-fold apparent KD error |
| Per-round / per-plate offset σ | 0.10 / 0.05 pKD | Round-to-round drift the bridge absorbs; within-round variation set to half of it |
| Round-4 version shift | −0.80 pKD, deterministic | At 5.3× the noise σ it is resolvable from a 3-design bridge (offset/SE ≈ 9) |
| Construct failure rate | 0.03 | Typical for a small expression campaign |
| Assay reads per design | 2 | Returned as separate rows, never pre-averaged |
| Detection limit | 2nd percentile | Censors a few percent of round-1 designs; the round-4 offset pushes more below it |
| **Threshold (the gate)** | **99th percentile** | Fixed here, before the first run |
| RNG seed | 20260918 | Fixed so the landscape is reproducible |

Generated by `python -m data.build_oracle`, recorded immediately and still before any campaign
run: build hash `sha256:c9b2566abc75f0db…`, **7,294 feasible** designs of 10,261, solved β
0.5527, realized linear R² **0.6008** against the 0.60 target, cliff at VH 103 (parent residue
F, selected by the pre-registered rule), detection limit **6.861**, **threshold 10.762**, and
74 of 7,294 designs above it — **1.01%**.

**One protocol change, made before the first campaign run and for a stated reason.** Inspecting
landscape values showed a diversity-maximizing seed batch would draw a design above the
threshold, which — since both arms share the round-1 batch — would have made every run reach
threshold at round 1 and measured nothing. The mitigation was authorized in writing beforehand
(*start from a deliberately mediocre seed set… a change to the protocol, and not a change to
the landscape after seeing a curve*) and taken as written: round 1 is a scan restricted to
single mutants. No single mutant in the feasible pool can reach the threshold (best is 9.919),
so round 1 is **structurally incapable of saturating** — a property of the mutation budget, not
a tuned parameter. The landscape, its parameters, the seed and the threshold did not move.

---

## What is real and what is staged

| Component | Status |
| --- | --- |
| Surrogate fitting, calibration, constraint filtering, batch acquisition | **Real.** Pure numpy, every round, browser and CLI |
| The five pipeline scripts, the round graph, the five diagnostics | **Real.** Six rounds through the CLI, selecting the same 288 wells as the evaluator |
| Both model recipes and the bake-off between them | **Real.** `ridge_onehot` against `gp_pca64` over the one-hot block |
| Developability and liability scores | **Real** deterministic calculations, labelled computed throughout |
| The two connectors | **Real.** MCP stdio, seven tools and three. `check.py` drives both over the protocol and compares them against the CLI |
| The skill and connectors inside Claude Science | **Real, and exercised end to end.** All eight tools run, the host's kernel executes the pipeline scripts, and the round-4 diagnosis reproduces every number and every input hash |
| The decision record | **Real, and exercised three times.** Round 4's pass 1 was written by an agent given only the skill and the connectors, its pass 2 by another after a named person sent it back, and it is deliberately unruled |
| The agent's reasoning in the CLI | **Real, and the transcripts are committed.** Three headless Claude Code sessions on `claude-opus-5`; see [`gates/`](gates/) |
| Rounds run in the browser | **Real, and checked against the CLI.** The repository's own modules, mounted into Pyodide byte for byte and imported rather than ported. State lives in the browser and is never written back |
| The browser's tool-call stream | **Real commands.** Each chip is a script that ran against the visitor's copy of the project, with its exit code and both output streams. It is not an animation |
| The agent's reasoning in the browser | **Real when a live seat is available, replayed otherwise, and a badge over the turn says which.** Live: `claude-sonnet-5` behind one stateless function with `SKILL.md` as its system prompt, handing a proposal to `record_decision.py`, which recomputes every number before it writes |
| **Affinity values** | **Simulated.** Synthetic landscape with pre-registered parameters; the oracle replays its values with noise. **Every affinity number in every surface is invented**, and this shows the decision loop converging, not that the method finds better antibodies |
| The wet lab | **Simulated.** Noise, ~3% construct failure, censoring, per-round and per-plate offsets |
| The LIMS | **Staged, and reachable over MCP.** `lims.py` mints identifiers, lays out plates, exports orders and rows, and answers whether a run has reported |
| The lab round trip | **Staged, deliberately.** Approving submits the batch and writes the order file, then stops. Whether results are back is a separate question put to the registry, refused the first time with the date expected — and that refusal is run and shown, not described. *Have the lab report now* is a demo device labelled *simulated* where it sits; it moves the clock and nothing else, and it is not on the registry's tool list, because a registry does not have a button that finishes an assay |
| **Sequence representation** | **A toy.** One-hot only, 160 dimensions. A real system uses a protein language model embedding — see [above](#how-it-decides-what-to-test-next). `esm_live` is declared and unwired, and asking for it returns an error naming what is missing rather than one-hot in disguise |
| Structure prediction | **Stubbed.** `predict_structures` returns nulls and a note saying it predicted nothing. It invents no confidence score, and nothing downstream reads it |
| The ad hoc sandbox | **A guard, not a sandbox, and labelled so in the source.** Model-written numpy runs read-only behind a read-only `open`, an import denylist and a line budget. Ad hoc output never enters a code path, which `record_decision.py` enforces on its own |
| The function behind the live seat | **Real, stateless, and not a proxy.** It builds every request itself, accepts only transcripts it signed, and reserves each call's cost against a daily cap before the call |
| The proof chart | **Real, and the evaluator's.** Twenty simulated campaigns per arm, drawn as the *template's* validation — never on a project's own progress chart, which draws only what that project measured |
| The web app's chrome, and its scenery | **A wireframe.** The panels, the Python, the state and the hashes inside it are real and running in your tab; the rail's host-only items are drawn and inert with a tooltip saying so, the other projects on the home screen are titles with no content, the second template is a visible stub, and the shipped round dates are spread over six weeks for display while no measurement moves |

---

## Using it in Claude Science

Claude Science is a local application, so it runs the same Python stdio connectors Claude Code
runs. What it has no single installer for is the *bundle* — the skill and the two connectors go
in as three separate acts, one of which is a hand-written config file. **Every step below has
been run.**

**1. The skill, once.** `Settings > Credentials` takes a fine-grained GitHub token with the
resource owner set to the organization that owns the repository and `Contents: Read-only`. Then
`Settings > Skills > Add skill > Import from GitHub`. The host reads
`.claude-plugin/marketplace.json`, resolves `skills/adaptive-optimization` out of it, and
records the commit it came from beside the copy it keeps.

**2. Each connector, by hand.** `Settings > Connectors > Add connector > Local command`, then a
name and one command line — there is no separate arguments field.

| Name | Command |
| --- | --- |
| `registry` | `python /path/to/adaptive-workbench/connectors/registry_server.py` |
| `bioprovider` | `python /path/to/adaptive-workbench/connectors/bioprovider_server.py` |

**`python` stays bare.** The host resolves it to its own bundled environment; an absolute path
to this repo's `.venv` is refused before the process starts.

**3. The sandbox grant, once.** The connectors are files in this repository, and the MCP sandbox
cannot see this repository. Write `~/.claude-science/config.toml`:

```toml
[sandbox]
user_read_paths  = ["/path/to/adaptive-workbench"]
user_write_paths = ["/path/to/adaptive-workbench/lims_store"]
```

Write is granted to exactly one directory — the mock LIMS's own store. Reads and writes are
gated separately, so a read grant alone loads the tools and then fails on the first
`submit_batch`. **The file is read once at startup**, so quit the app from the menu bar icon and
relaunch. Then `registry` lists its seven tools and `bioprovider` its three.

**Four failures hid each other along the way**, and only the first and last say what is wrong.
`execvp() … Operation not permitted` means the sandbox will not exec a binary in your home
directory — use the bare `python`. *Tools load forever with nothing in any log* means the
command box held an interpreter and no script, so a bare Python read the JSON-RPC stream as a
program: **a missing argument produces no error and no timeout.** `ModuleNotFoundError: …
mcp.server.mcpserver` is the host's `mcp` 1.x against this repo's 2.x, where `FastMCP` became
`MCPServer` — both connectors now import whichever is present. And *not visible inside the MCP
sandbox* is the `config.toml` grant above, plus a restart. `~/.claude-science/mcp/local-mcp.json`
records what the dialog actually saved and identified two of the four faster than the interface
did: **check the app's own state before the docs.**

### What a template would add, tested against the product

Installing into the host is the only way to find out which of this layer's claims are real and
which Claude Science already covers. Four were written down beforehand and then audited against
the product. Three survived, each narrower than written: **a ruling has no type** (the host has
scoped, revocable approval, but it gates *access*, not *decisions* — no typed decision, no verbs
bound to code paths, no hashed evidence); **a round graph has nowhere to render** (the rail lists
chat threads, and a campaign is a graph); and **traceability is an after-the-fact check** (the
host versions the *skill* to its commit, but nothing versions a *number* back to the function
and input hash that made it). The fourth — no project instantiation from a declaration — is
under-tested, so nothing in this build leans on it. Three more were found that had not been
claimed: **a connector cannot declare what it needs**, **the connector sandbox and the agent
sandbox hold separate grants** (a connector wrote a CSV the agent in the same session could not
read), and **a local-command connector with a missing argument fails silently.**

What the host already does well is recorded beside them, because an audit that only finds fault
is not an audit: local stdio connectors run, approval carries four scopes, skills import from a
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

Not the focus, but the whole repository reproduces from a fresh clone. numpy is the only
dependency of `core/`, and that is a design constraint rather than an oversight: `core/` is the
part an audience is invited to read. matplotlib is an *evaluator* dependency and the MCP SDK a
*connector* dependency.

```bash
python3.12 -m venv .venv && .venv/bin/pip install numpy matplotlib mcp
.venv/bin/python check.py                # 197 invariant checks, ~40 s
.venv/bin/python simulate_campaign.py    # the evaluator: 20 seeds, 3 arms, the chart, ~35 s

# The product path — the same science through the CLI
.venv/bin/python init_project.py --name demo-trastuzumab --team d.webster --force
.venv/bin/python run_rounds.py --rounds 4 --approved-by d.webster

# The judgment a scheduler cannot make, which is what the skill is for
S=skills/adaptive-optimization/scripts
.venv/bin/python $S/run_diagnostic.py --project projects/demo-trastuzumab --round 4 \
    --test calibration_by_region --offset bridge   # read-only, writes nothing

.venv/bin/python connectors/registry_server.py --tools   # the boundary claim, printed
cd web && npm install && npm run sync && npm run dev     # localhost:5173
```

Use `.venv/bin/python`, not `python3` — the system interpreter has no numpy. `run_rounds.py` is
a deliberately dumb scheduler: it prints every command it runs and **stops** the moment a round
is flagged. `npm run sync` copies `core/`, `data/`, `lims.py` and the skill scripts into
`web/public/workbench/` **byte for byte**, and `check.py` fails if any copy drifts — so **re-run
`python web/bundle.py` after touching anything the browser executes.** The live model seat needs
an `ANTHROPIC_API_KEY`; without one the page stays in verified replay and says so. The gates
re-run with `gates/run_gate.sh round4`, `round1` or `round4-pushback`.

---

## Repo map

| Path | Contents |
| --- | --- |
| `core/` | Pure numpy, shared by every surface. No network, no printing, no scipy/sklearn/pandas. `encode`, `surrogate`, `acquisition`, `reconcile`, `diagnostics`, `candidates`, `scoring`, `schema`, `project` |
| `skills/adaptive-optimization/` | `SKILL.md` and the seven scripts: five pipeline steps plus `run_diagnostic.py` and `record_decision.py` |
| `connectors/` | `registry_server.py` (seven tools over MCP stdio) and `bioprovider_server.py` (three). Not `mcp/`, which would shadow the SDK |
| `data/` | The simulated laboratory. **Never imported by `core/`.** `synthetic.py` is the landscape, `oracle.py` the assay |
| `lims.py` | The mock LIMS. Mints identifiers, owns the plate layout, holds the oracle |
| `projects/demo-trastuzumab/` | The committed demo project, at round 4 with the round deliberately unruled |
| `simulate_campaign.py` | The evaluator. **The only thing permitted to read landscape values** |
| `check.py` | 197 invariant checks. Run it before and after any change |
| `gates/` | The three agent gates: the transcripts, and the script that re-runs them |
| `web/` | `bundle.py` copies the repository into the browser's bundle and proves the derivation by replaying round 4; `function/ask.mjs` is the one stateless model turn, which builds every request itself and refuses what it did not sign; `src/` is the shell — React, a 60-line hash router, no state or charting library |

`CLAUDE.md` holds the conventions anyone changing this code needs. Numbered `decision NNN`
references in source comments point at `DECISIONS.md`, a build decision log removed once the
build finished — read it with `git show 2c60c0b:DECISIONS.md`, from the **`build-history`** tag
that holds the 49 commits this branch was squashed from.
