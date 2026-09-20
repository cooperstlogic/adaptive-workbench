# DECISIONS.md

Every choice the spec left open, plus anything decided during the build. One line of
reasoning each. Where a decision must be made *before* a result is observed, it is
recorded here and committed first — git history is the evidence that the order was kept.

## Settled before the build

| # | Decision | Reasoning |
| --- | --- | --- |
| 1 | Everything laboratory is simulated: synthetic landscape, one-hot features, local provider backend only | Deletes the largest external dependency in the plan — a licence question, a 150 MB download and a parse step that could each fail at hour six. Real data and embeddings become self-contained upgrades attempted only after phase 9 passes |
| 2 | The surrogates stay real | `ridge_onehot` and `gp_pca64` are the demo. Mocking them would leave a chart of invented numbers with nothing underneath |
| 3 | `gp_pca64` runs over PCA of the one-hot block | The spec already defined it as PCA over *whichever block is active*, so the two-recipe bake-off survives the loss of embeddings with no change to the registry |
| 4 | Acceptance criterion "switching the provider backend changes no code outside project.json" is struck | The second backend is not wired in this build. A criterion with an asterisk is worth less than one fewer criterion; it moves to the staged table |
| 5 | Exactly one agentic decision point: diagnosing a flagged round | Build one properly rather than five badly. Stop/widen/confirm and cross-round constraint learning both depend on editable objectives, which pulls versioning and staleness through the whole UI |
| 6 | No orchestrator script | The agent *is* the orchestrator — it calls diagnostics through a thin CLI, reads the numbers, and writes a record. A hardcoded sequence would be the pipeline we are trying to escape |
| 7 | The anomaly flag is code, the diagnosis is not | `import_round` decides a round *looks* wrong from a template threshold. Why it looks wrong is the judgment call, and it is the only one |
| 8 | Ad hoc code execution is in scope for day one, at the top of the cut list | The Pyodide sandbox already exists, so it costs one tool definition and a result panel. It is the strongest answer to "isn't this just a decision tree?" — the sixth question is never in the tree |
| 9 | Ad hoc code runs in the browser's existing Pyodide sandbox | Zero new infrastructure, and the boundary is enforced by what is mounted (snapshot arrays and `core/`, never the oracle) rather than by instruction |
| 10 | The reasoning panel's tool loop lives in the browser, not the Netlify function | Pyodide holds the data and the sandbox; the key cannot go client-side. So the function is a stateless single-turn proxy and React owns the loop — which also keeps every invocation inside Netlify's synchronous window |
| 11 | `claude-opus-5`, adaptive thinking, `effort: "low"`, streaming, ~400 max tokens | Effort is the cost lever that matters for a panel that reads small JSON and explains. Sonnet 5 would be ~2.5× cheaper and adequate, but the ad hoc code path benefits from Opus and the caps do the real work |
| 12 | Public access to the panel is funded by a daily cap, not by asking visitors for a key | Key in a Netlify env var, global spend cap and per-IP counter in Netlify Blobs. Over budget, the site returns to verified replay — a complete experience, not an outage |
| 13 | The Netlify function never accepts a caller-supplied `messages` array | It builds the request from a fixed system prompt, server-side project state, and a length-capped question string. Otherwise the deployment is a free Opus endpoint on your card |
| 14 | The Setup panel is read-only in this build | Editing objectives is the mechanic that stop-or-widen recommendations need, and those are out of scope for day one |
| 15 | The round-4 decision card replaces walking three batch rows in the demo | Approving a judgment is something a human can actually do; approving 48 rows is a rubber stamp, and it was the weakest minute in the script |
| 16 | Censored wells enter the fit at the detection limit with a flag | The alternative is a Tobit likelihood and it is not worth the hour. Bias is slightly upward; the flag is surfaced in the batch table |
| 17 | Hashes are over canonical JSON: sorted keys, no insignificant whitespace, fixed float precision | Without it, numpy under WebAssembly and numpy on a laptop produce two hashes for one decision and the lineage claim stops being checkable |

## Pre-registered landscape parameters

**Committed 2026-09-19, before any landscape was generated and before
`simulate_campaign.py` had ever run.** Every value carries a justification that does not
reference the outcome. If the hour-3 gate fails on these parameters, the deliverable is a
sentence saying it failed — not a new table.

### Structure of the landscape

Additive site effects plus pairwise epistasis, over 8 positions of the trastuzumab
CDR-H3, with one structure-activity cliff.

Not an NK model, and the reason is decisive: with `max_mutations = 2`, only first- and
second-order terms are ever reachable from the parent. A model with higher-order
interactions would carry terms that can never fire. Pairwise is exactly expressive
enough, and anything beyond it is unreachable machinery.

| Parameter | Value | Justification (independent of result) |
| --- | --- | --- |
| Lead | trastuzumab VH, public sequence | The template's declared lead |
| Editable region | 8 residues of CDR-H3 (`GGDGFYAM`), 0-based VH indices recorded at build | Excludes the conserved flanking `W` and the `DY` motif; 8 positions matches the template |
| Alphabet | 20 standard amino acids | — |
| Max mutations | 2 | Template constraint; keeps the pool enumerable at 10,261 sequences |
| Parent pKD | 9.00 | Low-nanomolar, the regime an approved anti-HER2 lead occupies |
| Additive effect scale (σ_a) | 0.45 pKD | Single-point CDR substitutions in affinity maturation typically move affinity by a few tenths of a log unit with occasional ~1-log effects; σ = 0.45 puts 95% of singles inside ±0.9 |
| Epistasis weight (β) | calibrated to a linear R² of 0.60 | Set so a one-hot linear model explains 60% of landscape variance over the candidate pool. Additive-dominant with a substantial epistatic residual is the regime antibody affinity DMS studies report; it also gives the surrogate real structure to learn without making epistasis decorative. β is solved numerically against this target, which is a calibration to a pre-registered number, not a tuning to a result |
| Cliff position | the editable position with the largest maximum additive effect | Stated as a rule, not an index, so the seed determines it. Placing the cliff at the most attractive position is what makes the optimizer walk into it naturally rather than by construction |
| Cliff residues | `{P, D, E, K, R}` | Mechanistically motivated and drawn independently of the additive draw: proline breaks backbone geometry and burying charge at a contact residue is costly |
| Cliff depth | −1.50 pKD | Deep enough to dominate the round-4 offset, so the two explanations genuinely compete in the marginals |
| Assay noise (σ, pKD) | 0.15 | ~1.4-fold apparent KD error, typical replicate spread for a well-run binding assay |
| Per-round offset (σ, pKD) | 0.10 | Small round-to-round drift that the bridging set exists to absorb |
| Per-plate offset (σ, pKD) | 0.05 | Plate-to-plate variation inside a single round is typically smaller than run-to-run drift between rounds; set to half the per-round σ |
| Round-4 assay-version shift | −0.80 pKD, deterministic | An assay version change producing a ~6-fold apparent shift is a thing that happens. At 5.3× the noise σ it is resolvable from a 3-design bridge (offset/SE ≈ 9), which is what makes the diagnosis defensible rather than a coin flip |
| Construct failure rate | 0.03 | Typical for a small expression campaign |
| Assay reads per design | 2 | Returned as separate rows, never pre-averaged |
| Detection limit | 2nd percentile of the landscape | Censors a few percent of round-1 designs; the round-4 offset then pushes more below it, which is realistic and gives `import_round` work to do |
| Threshold (the gate) | 99th percentile of the landscape | Fixed here, before the first run, per SPEC. Absolute value recorded below once generated |
| RNG seed | 20260918 | Fixed so the landscape is reproducible |

### Derived absolute values

Generated 2026-09-19 by `python -m data.build_oracle`, recorded immediately and still
before any campaign run. The build is deterministic: rebuilding from the same seed
reproduces the same build hash.

| Item | Value |
| --- | --- |
| Build hash | `sha256:c9b2566abc75f0dba893f4c6628c9bb1213dd2921fa4317b8751be03d2ce3318` |
| Candidate space | 10,261 sequences (7,294 feasible after constraints) |
| Solved epistasis weight β | 0.5527 |
| Realized linear R² | 0.6008 (target 0.60) |
| Cliff position | VH index 103 (window index 4), parent residue **F** |
| Cliff residues | DEKPR, depth −1.50 pKD |
| Parent pKD | 9.000 |
| Landscape min / median / max | 4.961 / 8.865 / 11.675 |
| Detection limit (p2) | **6.861** |
| **Threshold (p99)** | **10.762** |
| Feasible designs above threshold | 74 of 7,294 (1.01%) |

The cliff rule — *the editable position with the largest maximum additive effect* — landed
on VH 103, where the parent residue is phenylalanine. Charge or proline replacing a buried
aromatic is exactly the mechanism the cliff residue set was chosen for, and the position
was selected by the pre-registered rule rather than by hand.

### Protocol change: round 1 is a single-mutant scan

**Found before the first campaign run, by inspecting landscape values.** A
diversity-maximizing seed batch over the *whole* feasible pool drew a design at 10.97 pKD —
above the 10.762 threshold. Since both arms share the round-1 batch, every run would have
reached threshold at round 1 and the comparison would have measured nothing.

`SPEC.md` pre-authorized the mitigation before any of this ran: *start the campaign from a
deliberately mediocre seed set… a change to the protocol, recorded in DECISIONS.md, and not
a change to the landscape after seeing a curve.* Taken as written.

Round 1 is now a diversity-maximizing scan restricted to single mutants, declared in the
template as `batch.round1_policy`. What did **not** change: the landscape, its parameters,
the seed, and the threshold. What makes this sound rather than convenient:

- **No single mutant in the feasible pool can reach the threshold** (best is 9.919 against
  10.762). Round 1 is structurally incapable of saturating — a property of the mutation
  budget, not a tuned parameter.
- It is justified independently of the landscape: a first round of single-point scanning is
  what affinity maturation campaigns actually do, and it teaches the surrogate site effects
  before it has to reason about combinations.
- Both arms still share the seed batch, and rounds 2 onward still draw from the full
  feasible pool, so the comparison is unchanged.
- Headroom from the seed's best (9.75) to the landscape max (11.67) is 1.92 pKD.

Stated plainly because it matters: the saturation was discovered by looking at ground truth.
Doing that before the first run is the point of checking in hour two rather than hour nine.
Doing it after a curve exists would have been the forbidden move.

## Decided during the build

**2026-09-19 (phase 1)**

| # | Decision | Reasoning |
| --- | --- | --- |
| 18 | Python 3.12 venv at `.venv`, numpy only | numpy is the single declared dependency. 3.12 for wheel stability under Pyodide-adjacent versions |
| 19 | Editable region is `[99, 107)`, not the spec's illustrative `[98, 106]` | CDR-H3 begins at VH index 98 with a conserved tryptophan. `[99, 107)` is the 8 residues `GGDGFYAM`, excluding that W and the terminal DY. The spec's numbers were illustrative JSON |
| 20 | `liability_count` counts motifs *introduced* relative to the parent | Trastuzumab's own CDR-H3 carries a DG isomerization motif, and every 8-residue window of that CDR contains it. A filter that rejects the approved lead's own scaffold is one nobody would ship; introducing none is the real design rule. The parent's inherited DG is reported on the lead instead |
| 21 | Hydrophobicity threshold is 0.55, not the spec's illustrative 0.45 | The parent sits at 0.507. Threshold set marginally above it: the lead is an approved therapeutic, so the rule is not to become more aggregation-prone than the molecule that already works. Set before any campaign run |
| 22 | Landscape is additive + pairwise, not NK | With `max_mutations = 2` only first- and second-order terms are reachable. Higher-order terms could never fire |
| 23 | Pairwise terms are zeroed when either residue is the parent's | Epistasis is an interaction between two actual mutations, and it makes the parent sit exactly at 9.000 |
| 24 | The cliff is a single-site effect, so a one-hot linear model can represent it | Deliberate: the cliff must be *learnable* for the round-4 diagnosis to be discoverable rather than a coin flip |
| 25 | Project creation is `init_project.py` at the repo root, not one of the skill's seven scripts | The skill operates on a project that already exists; template instantiation is a separate concern |
| 26 | Round 1 is a single-mutant scan | See the protocol-change section above |
| 27 | Oracle takes optional `plates`, registry owns plate assignment | Keeps the boundary clean: the registry mints identifiers and lays out plates, the oracle only measures |
| 28 | A failed construct takes out every read for that design | What a failed expression actually does. Per-read failure would be wrong |


**2026-09-19 (phase 2)**

| # | Decision | Reasoning |
| --- | --- | --- |
| 29 | Recipes are selected on held-out negative log predictive density, not RMSE | "Held-out calibrated performance" needs to be one number or the tie-break is a judgment call made in code. NLPD is accuracy and calibration in a single quantity, and a recipe that is accurate but overconfident loses to one that knows what it does not know — which is the property batch selection actually consumes. RMSE, R² and 80% coverage are recorded beside it so a human can see why |
| 30 | Predictive intervals include observation noise everywhere | The quantity a batch table shows a scientist is the measurement they will get back, not the latent function. It also makes the coverage number comparable against what actually returns |
| 31 | `gp_pca64` lengthscales are multiples of the median pairwise distance | Makes the two-point grid mean the same thing whatever the principal components happen to be scaled like. Standard median heuristic, and it keeps the hyperparameter search to the two the spec declared |
| 32 | The error function is the Abramowitz–Stegun 7.1.26 form | numpy has no erf and scipy is not a dependency. Maximum absolute error 1.5e-7, pure float64 arithmetic, so a laptop and WebAssembly agree — which matters because these numbers are hashed into batch records |
| 33 | Diversity penalty is subtracted from max-normalized expected improvement, weight 0.25 | An absolute weight against a raw EI scale means something different in round 2 and round 6. Normalizing to the round's own maximum is a monotone transform, so the EI ranking is untouched and only the trade-off is fixed |
| 34 | A design is flagged as extrapolating above the 90th percentile of pool predictive sd | Relative to the pool the model was asked about rather than an absolute pKD number, so the flag keeps meaning "among the least-certain designs here" as the model improves |
| 35 | Reconciliation lives in `core/reconcile.py`, not inside `import_round.py` | `simulate_campaign.py` has to pool measurements across rounds too, and a second implementation of the bridging arithmetic is exactly the fork non-negotiable 2 forbids. `import_round.py` becomes a thin wrapper in phase 3 |
| 36 | Two plates of 24, not one of 48 | One plate makes the per-plate offset indistinguishable from the per-round one and turns `residual_by_plate` into a formality. Two plates is what lets the round-4 diagnosis separate a plate effect from a version change |
| 37 | The oracle takes a `run_seed`, and plate keys are a digest | Twenty seeds per arm has to mean twenty independent replays, and the oracle's RNG was keyed only on the round. Separately, `hash(str(plate))` is salted per process, so plate offsets differed between two runs of the same campaign — any claim that a diagnostic recovers a plate effect has to survive a restart. Neither is a landscape parameter |
| 38 | The campaign writes `web/public/assets/campaign.json` | The proof chart's data has exactly one consumer beyond the terminal, and it is the web app. Writing it twice would let two copies disagree. `simulate_campaign.py` prints an ASCII chart because matplotlib is not a dependency and adding one for an evaluator is not worth it |
| 39 | Runs that never reach the threshold are recorded as round 7, not dropped | Dropping them would score random only on the runs where it succeeded. Two of twenty random runs never reached it |

### Three things found by running the gate, and what was done about them

Each of these was found by looking at the machinery, not at the curve. None of them touched the landscape, its parameters, the seed or the threshold.

**The round-1 "diversity-maximizing scan" scanned four of eight positions.** Greedy
max-min Hamming is the right diversity criterion over the whole pool and a degenerate one
over single mutants: every pair sits one or two apart, and once the parent is taken every
remaining candidate is at distance one forever, so the greedy collapses into enumeration
order and spent all 48 wells on VH 99–102. Positions 103–106 were never sampled, including
the cliff position, so the surrogate entered round 2 knowing nothing about half the
editable region. Replaced by a stratified scan: positions round-robin, six substitutions
each, residues declared in the template as `ADKSLW` — small, acidic, basic, polar,
aliphatic, aromatic. That is what a CDR scan looks like when a protein engineer lays one
out. The pre-registered gate condition still holds unchanged: no single mutant in the pool
can reach the threshold, so round 1 remains structurally incapable of saturating.

**The bridging set was measuring regression to the mean.** The bridge was the parent, the
best design measured so far, and the previous batch's top two — three of the four selected
for having read high, so their re-measurements regressed downward and biased the offset
estimate by about −0.10 pKD on every round. A design chosen because it read high will read
lower next time whatever the assay did. Now the bridge is the parent plus two designs
chosen to *span* the previous batch's range, which is the 3-design bridge DECISIONS.md
pre-registered in the first place; the best-so-far design is still re-run to confirm it,
and is deliberately excluded from the offset estimate. Round-4 offset error fell from
−0.105 to −0.025 pKD against a true shift near −0.82.

**The anomaly flag fired on every round, so it carried no information.** The template
declared it as the fraction of designs outside the model's 80% interval, triggering above
0.35. Measured over twenty seeds it fired on 12 to 20 of 20 runs at *every* round — and
the reason is structural rather than particular to this landscape: acquisition
deliberately samples where the model is least certain, so a dispersion statistic over a
batch chosen by expected improvement is guaranteed to trip. Replaced with the mean
**signed** discrepancy over the round's fresh designs, triggering above 0.5 pKD — a
three-fold change in apparent KD and 3.3 times the assay's noise sigma, which is a
discrepancy a scientist would stop for. Three properties made this the right statistic
rather than a convenient one:

- A run offset and a genuine activity cliff trip it identically. The flag says a round
  needs deciding and never says which explanation wins, which is non-negotiable 6.
- It is scoped to the round's *fresh* designs. Letting the bridge into the flag would mean
  the alert had already concluded the run moved rather than that the designs are worse.
- A round on an assay version the project has already characterized is compared against
  that characterization. Round 4 is the first v1.3 round, so nothing is known and it
  flags; rounds 5 and 6 are compared against the recorded offset and go quiet. The arm
  that never corrected keeps alarming at rounds 5 and 6, which is the honest consequence.

The interval miss rate is still computed and reported, because the calibration panel wants
it. It is reported, not triggered on.

### The gate, and one change to how it was scored

**The gate passes.** Twenty seeds per arm, six rounds, batch of 48, shared round-1 scan,
scored against the 10.762 pKD threshold fixed before any of it ran.

| | guided | random | guided, naive pooling |
| --- | --- | --- | --- |
| Mean rounds to threshold | **2.00** | 2.95 | 2.00 |
| Median rounds to threshold | 2.0 | 2.0 | 2.0 |
| Reached it by round 6 | 20/20 | 18/20 | 20/20 |
| Final best observed, median | **11.755** | 11.212 | 11.052 |
| Final best landscape, median | **11.674** | 11.105 | 11.674 |

Guided is **never slower than random on any of the twenty paired seeds**, faster on eight,
exact paired sign test p = 0.0078. The interquartile bands separate at rounds 2, 5 and 6 on
both the observed and the landscape line. Guided finds the feasible pool's global maximum
of 11.674 pKD by round 5 in every run; random plateaus at 11.105.

**The change, stated plainly because it was made after seeing the first run.** The verdict
was first coded as *guided's median rounds-to-threshold is lower than random's*. Both
medians came back 2.0 and the gate reported a failure while guided was winning 8–0. The
median is a discrete count with a floor at two, guided lands on that floor in eighteen of
twenty seeds, and a statistic with no resolution is not evidence either way. The verdict
now tests the paired comparison across the same twenty seeds — which SPEC.md's wording,
*measurably fewer rounds than random over twenty seeds per arm*, already describes, and
which was computed and printed in the same commit as the median. The mean and the median
are both still reported. **Nothing about the landscape, the parameters, the seed or the
threshold moved**, and the raw per-seed rounds-to-threshold arrays are in
`campaign.json` so the reading can be checked rather than taken.

### What the two metrics showed, and the third arm

SPEC.md asked for both metrics in hour two, and they diverge in the way it anticipated.
Best-observed is a maximum over noisy reads, so random is flattered: its median first
crosses the threshold at round 2 on observed values while its noise-free line is still at
10.683. The divergence is a real result and the calibration panel should carry it.

The third arm earns its place, but not for the reason expected. Naive pooling across the
round-4 assay version change **does not make the optimizer pick worse designs** — its
noise-free line reaches the same 11.674 as corrected guided selection. What it does is
corrupt what you believe you measured: its reported best falls from 11.358 at round 3 to
11.052 at round 6, a median 0.702 pKD below corrected guided selection on all twenty
seeds, which is a five-fold error in the apparent affinity of your own lead. The arm ships,
and the claim attached to it is about reported values and not about selection.

Because a cumulative best that *falls* deserves an explanation rather than a footnote: the
headline metric is the project's current estimate for its best design, and re-measuring a
design moves it. A monotone companion, the running maximum over individual corrected
measurements, is recorded beside it so neither claim rests on the choice of metric.

### Other things worth recording from the run

- **`ridge_onehot` wins the bake-off in every round of every seed.** The GP's held-out
  coverage degrades to 0.59–0.62 while ridge holds 0.80–0.88, so it loses on calibration
  exactly as NLPD selection is meant to catch. SPEC.md predicted one-hot would win here and
  it did; a product that picks the simple model when the simple model wins is more credible
  than one that does not.
- **The flag fires at round 2 in 12 of 20 seeds, positively.** A model fit on single
  mutants alone under-predicts the first double mutants, so they come back better than
  forecast. It is a true signal with a clean explanation and it is left in: round 4's
  median discrepancy of 1.07 pKD still stands more than twice above every other round.
- **One seed in twenty did not flag at round 4.** Its true offset was −0.595 pKD rather
  than the typical −0.82, because that round's drift partly cancelled the version shift.
  A flag that fires when the shift is large and not when it is small is behaving.

**2026-09-19 (phase 2, follow-up: plotting and the third arm)**

| # | Decision | Reasoning |
| --- | --- | --- |
| 40 | The numpy-only rule applies to `core/` and nowhere else; matplotlib is an evaluator dependency | The justification that sounds natural — "it has to run in the browser" — is false: Pyodide ships wheels for scipy, scikit-learn, pandas and matplotlib. Stating it out loud to this audience would cost more than the dependency saves. The two reasons that survive are real and narrower: `core/` is the part an audience is invited to read, where fifty lines of numpy they can check beats a library call they must trust; and every wheel is weight on a cold visit to a public URL. Neither reason reaches `simulate_campaign.py`, which is already not a product path |
| 41 | The chart renderer is `plot_campaign.py`, separate from the campaign | Redrawing from the committed `campaign.json` takes a second where re-running takes thirty-five, and the split means the renderer's only input is the published numbers. `simulate_campaign.py` calls it at the end and degrades to numbers-only if matplotlib is missing |
| 42 | The web app draws its own charts in the browser rather than embedding the rendered image | A visitor's rounds extend the curve live, and a PNG cannot. This duplicates *presentation*, not science — both surfaces read the same `campaign.json`, and the rule that matters, never porting `core/` to JavaScript, is untouched. Rendering through matplotlib under Pyodide would keep one implementation but costs a heavy wheel on boot and looks like matplotlib on a web page |
| 43 | Both light and dark renders ship, and the chart's palette is validated rather than chosen | Categorical slots 1–3 of the reference palette, checked for colourblind separation, lightness band, chroma and contrast in both modes. Slot 3 sits below 3:1 on the light surface, so every series carries a direct endpoint label — the relief, not a flourish |
| 44 | The campaign records the design each arm's own state ranks first, scored at its landscape value | "Your reported number is wrong" is a weaker claim than "you would advance the wrong molecule", and only the second is a decision. The metric is evaluator-only and it is what turned the third arm from a presentational difference into a measured one |

### What the third arm actually shows

The naive-pooling arm was kept on the condition SPEC.md set: it ships only if
mis-correcting degrades measurably. It does, but not where it was expected to, and the
claim attached to it has been narrowed to what the numbers support.

**It does not make the optimizer pick worse designs.** Its noise-free selection line
reaches the same 11.674 pKD as corrected guided selection. Every design it chooses is as
good.

**It corrupts the ranking the project holds, and that is a decision.** At round 6 it
advances a genuinely worse molecule in **12 of 20 seeds, a median 0.605 pKD worse** — a
four-fold error in the KD of the lead taken forward. The mechanism is specific: the
best-so-far design is re-run as a control every round, so pooling its round-4 reading
without correction drags its own average down until a worse design outranks it. The arm
demotes its own best molecule. One seed in twenty crosses the threshold and then reports
itself back below it.

**And the alert never clears.** Because no ruling is ever recorded for v1.3, the flag
keeps firing: 20 of 20 at round 5 and 11 of 20 at round 6, against 6 and 0 for the
corrected arm. That is the cost of a flagged round nobody decided, and it is the most
direct argument in the build for why the decision record exists at all.

The line to use: *not correcting does not change which molecules you make. It changes
which one you believe is best, and in twelve of twenty runs you take the wrong one
forward.*

---

**2026-09-19 (phase 3: the pipeline scripts, the skill, and the mock LIMS)**

| # | Decision | Reasoning |
| --- | --- | --- |
| 45 | Round 1 goes through `generate_candidates.py` and `select_batch.py` like every other round; `init_project.py` writes no designs and no pool | It wrote both before, which meant round 1 was the only round with designs but no batch record — no rationale, no approval, no entry in the round graph, and a second code path writing the same designs the selection script would have written. SPEC.md already said round 1 needs no extra script; the fix was to stop giving it one. Instantiation now reports the constraint summary and stores nothing |
| 46 | The candidate pool is hashed, not stored | Enumeration is deterministic, so `pool_NNN.json` carries counts, the removal reasons and a content hash over the ordered pool. Every later artifact indexes into that order, and each consumer re-enumerates and checks the hash. Storing the hash costs nine hundred bytes where storing 7,294 sequences costs most of a megabyte a round, and a mismatch is caught instead of silently misaligning every prediction by one |
| 47 | A model run stores one prediction per pool member, in the pool's hashed order | SPEC.md asks `fit_surrogates` to store predictions for the whole candidate pool, and every consumer needs them: selection reads the mean and the standard deviation, the batch table shows them to a scientist, and `evaluate_prior` scores them. 205 kB a round, and the alternative — storing the fitted ridge model — is a 160×160 matrix, which is the same size and less useful |
| 48 | The mock LIMS is `lims.py` at the repo root, not a module inside `mcp/` | `mcp/` holding an importable package named `mcp` would shadow the `mcp` PyPI distribution that FastMCP is built on, and phase 5 would lose an hour to an import error with no obvious cause. `mcp/` keeps the two server entry points and nothing importable; they will do `import lims` |
| 49 | The lab stand-in is built now rather than in phase 5 | Phase 3's done-condition is six rounds through the CLI, and six rounds need something that mints sample identifiers and returns assay rows. Building it as a plain module now means phase 5 is a transport change of about eighty lines, and the alternative — a throwaway script writing sequence-keyed CSVs — would make reconciliation fake in phase 3 and rebuild it in phase 5 |
| 50 | `import_round.py` never decides whether to correct a round. The caller passes `--offset {never,if-clear,always}` and must name an `--authority` | The reconciler estimates the offset and sets the flag; it does not rule. Routine control normalization on a round that did not flag is a *policy*, and `run_rounds.py` owns it and says so in the snapshot (`bridge_policy:...`). A flagged round stays in the raw assay frame under authority `unruled`, because an assay shift and a real activity cliff produce the same first look and correcting the wrong one erases the finding. Moving such a round takes `--offset always` and an authority that names the decision record |
| 51 | `run_rounds.py` exists, shells out to the real scripts, prints every command, and stops on a flagged round | Phase 3 needs a way to run six rounds, and the honest way to provide one is a scheduler that is visibly a scheduler. It is also the argument: import, fit, generate, select, repeat needs no agent, and the place it stops is the place the agent is for. `--ignore-flags` continues without a ruling, which is what makes the naive-pooling arm reproducible from the CLI |
| 52 | `evaluate_prior.py` scores against the project's own round-1 scan, not against random selection | SPEC.md asks for realized improvement "against the random baseline", and that baseline is a property of the evaluator: measuring it inside a live campaign would mean spending wells on designs nobody wanted. What a project can compare against honestly is its own round-1 batch, the only one chosen without a model. The random arm stays in `campaign.json`, labelled as coming from the evaluator. The claim was narrowed rather than faked |
| 53 | Predictions are rounded to the stored precision inside `core/surrogate.py`, not at the file boundary | See below: this is the fix for a reproducibility bug, and the reason it belongs in `core/` is that all three surfaces have to select the same batch from the same snapshot. SPEC.md already makes this argument for hashes — fixed precision is what keeps a hash stable across numpy under WebAssembly and numpy on a laptop. Predictions that drive a selection get the same treatment, so the number written into the model run is the number the selection saw |
| 54 | Exploration slots break their tie on the better developability margin, then on pool order | A stable sort alone would be enough for determinism and would pick by enumeration order, which is an accident. Breaking on the margin is the same tie-break `greedy_diverse` already applies to the fresh picks, so the rule is one rule, and the reason is statable to a scientist |
| 55 | A batch records `recommended`, `approved` and `overrides`, and a batch with no named approver is labelled `unreviewed` | This is the governance claim in one file. `--drop DESIGN_ID --drop-note` records a removal with a note, an approver and a timestamp, and `evaluate_prior` scores predictions for the approved designs only, so the model is neither credited nor blamed for designs a scientist removed. A run with no `--approved-by` does not silently claim approval |
| 56 | The assay export carries six decimals | The CSV is a file boundary and therefore has a precision. Four decimals moved the pooled best by 3 × 10⁻⁵ pKD, which is meaningless as chemistry and was enough to change a batch. Six matches `schema.FLOAT_PRECISION`, so the whole system quantizes at one place |

### The bug phase 3 found: batch selection was not reproducible

Building the CLI path gave a way to ask a question the evaluator alone cannot: does the
product select the same batch the evaluator does? It did not. Rounds 1 and 2 agreed to
1 × 10⁻⁶ pKD and round 3 diverged by 0.1 pKD, which is a different molecule.

**The cause is a tie, and the tie is not a corner case — it is the normal case.** Under a
one-hot ridge model, every double mutant at a pair of positions the model has not yet seen
jointly carries *bit-identical* predictive variance. The top of an uncertainty ranking is
therefore dozens of designs deep in exact ties: the ten highest standard deviations in the
round-2 pool were all 0.406393579971. The exploration slots were selected with
`np.argsort`, whose default is quicksort and is not stable, so which two of those dozens
got measured depended on array order — and would differ on a different numpy build, and
in Pyodide.

That is not a cosmetic problem. Two of the demo's load-bearing claims are that clicking a
batch walks back to the exact evidence that produced it, and that the browser runs the same
Python as the CLI. A batch that cannot be reproduced from its own snapshot breaks both.

**The fix, in two parts, both in `core/`.** Exploration slots are now ranked by
`np.lexsort` on standard deviation, then the developability margin, then pool order. And
predictions are rounded to `schema.FLOAT_PRECISION` where they are produced, so the
selection consumes exactly the numbers that get written to disk. Two smaller cases went
with it: the control and replicate sorts keyed on the value alone, and `measured` is a set
of strings whose iteration order is salted per process, so a tie on the value — which
censored designs, all sitting exactly at the detection limit, are guaranteed to produce —
could pick a different control on a different run of the same project.

**The gate was re-run and the verdict did not move.** Stated plainly, because the change
was made after the gate had already passed:

| | before the fix | after the fix |
| --- | --- | --- |
| Mean rounds to threshold, guided vs random | 2.00 vs 2.95 | **2.00 vs 2.95** |
| Paired sign test | 8 wins, 0 losses, p = 0.0078 | **8 wins, 0 losses, p = 0.0078** |
| Interquartile bands separate at | rounds 2, 5, 6 | **rounds 2, 5, 6** |
| Final best observed, median, guided | 11.755 | 11.762 |
| Final best observed, median, naive | 11.052 | 11.015 |
| Round-4 offset recovery, mean error | −0.025 | −0.036 |
| Advances a worse molecule, naive arm | 12 of 20 seeds, median 0.605 | 14 of 20 seeds, median 0.648 |

**The random arm is bit-identical before and after**, which is the confirmation that the
change touched only exploration-slot selection: the random arm has no exploration slots.
Nothing about the landscape, the pre-registered parameters, the seed or the threshold
moved, and the fix was motivated by a reproducibility failure found in a different phase
rather than by any curve.

### One overclaim in the README, corrected

The phase-2 README said guided "reaches the feasible pool's global maximum of 11.674 pKD by
round 5 in every run". That was wrong when it was written: it was 18 of 20 runs at round 5,
not 20, and the 11.674 figure is the *median*, which reaches the maximum because more than
half the runs do. It now reads that the median run reaches it by round 5 and 17 of 20
individual runs reach it by round 6. Worth recording because it is exactly CLAUDE.md's
third failure mode, found by re-deriving a number instead of copying it forward.

### Phase 3 results

**Six rounds run end to end through the five scripts and the mock LIMS, and they select the
same wells the evaluator does.** The CLI reproduces the evaluator's uncorrected arm to
1 × 10⁻⁶ pKD and its corrected arm to 7 × 10⁻⁷ pKD on every round, and all six batches are
identical in membership and order — 288 of 288 wells. The residual 10⁻⁶ is the CSV's own
storage precision and nothing else. `check.py` runs both campaigns and compares them, so
the claim is checked rather than asserted, and it is the strongest available statement that
non-negotiable 2 holds.

**The round graph is complete and self-verifying.** Thirty artifacts over six rounds, every
hash matching the record it points at, every record recomputing its own hash from canonical
JSON. The registry's 288 sample identifiers never coincide with a design identifier, so the
join in `import_round` is real work.

### Two things about the demo project that phase 4 needs to know

**There are two flagged rounds, not one, and they want opposite rulings.** Round 2 flags
*positively*, at +0.765 pKD: a model fit on single mutants alone under-predicts the first
double mutants, so the designs came back better than forecast. The right action is
`refit_only` and nothing to the data. Round 4 flags negatively at −2.046 and wants a
correction. The same statistic, two correct answers, which is the argument for the decision
record made by the data rather than by the spec. `DECISIONS.md` decision 39 already
recorded round 2's positive flag as a true signal with a clean explanation; what is new is
that the product stops for it.

**Round 4 is ambiguous for two reasons, and correcting the offset accounts for only half of
it.** SPEC.md asked whether the ambiguity would arise on its own before engineering it. It
does, and it is richer than the single-cause story the spec sketched:

| Round 4 in `projects/demo-trastuzumab` | |
| --- | --- |
| Assay version | v1.3, first seen this round, so nothing about it is characterized |
| Fresh designs | 42, a mean −2.046 pKD from where the model put them |
| Interval coverage | 0.07 realized against 0.80 nominal and 0.82 held out at fit time |
| Bridge | 3 shared designs, offset −1.014 pKD, se 0.059 |
| Residual by mutated position | flat, −1.57 to −2.42 across seven positions |
| Cliff-hitting designs | 2, mean residual −2.196 against −2.039 for everything else |

The bridge recovers about a pKD of assay shift and the fresh designs are two pKD low, so
**the offset does not account for the round**. The residual is flat across mutated
positions and the cliff-hitting designs are indistinguishable from the rest, so it is
**not** the cliff either — which is the evidence `residual_by_mutation_class` exists to
produce. What remains is the model: the project's pooled incumbent had drifted to 11.837
pKD against a true pool maximum of 11.674, because a cumulative best observed is a maximum
over noisy reads and is flattered by every round of them, so the surrogate was fit on
values that do not exist and extrapolated from there.

A phase-4 diagnosis that corrects the offset and stops is wrong about half of round 4. The
correct recommendation is a partial correction plus a statement about calibration, and
`if_wrong` has something real to say: if the whole discrepancy were the assay, the bridge
and the fresh designs would agree, and they do not.

### The shell is Claude Science's, and the agent runs live inside it

Recorded before phase 4, after reviewing the Claude Science beta interface. Nothing here
touches the landscape, the threshold, the parameters or any number already published; it
changes where phases 5 to 9 put their hours.

**The problem.** Phase 5's gate named Claude Code, and phases 6 and 7 described a bespoke
three-panel dashboard with the model confined to a read-only sidebar. Read together, the
artifact argues it extends Claude Science and then demonstrates in two places that are not
Claude Science. Worse, the browser surface as specified contains no agency at all: Approve
runs the same five steps whatever comes back, the decision card replays a record produced
yesterday in a terminal, and a panel that cannot write project state is a narrator with a
calculator. The agentic claim rested entirely on the terminal beat.

| # | Decision | Reasoning |
| --- | --- | --- |
| 57 | The hour-5 gate is reworded to "an agent given only the skill and the connectors", with Claude Code named as the verifying harness | What the gate tests is whether `SKILL.md`, the five diagnostics and the state contract are *sufficient*, which is a property of the skill pack and not of the client. Claude Code can be scripted, re-run after a skill edit, and committed as a transcript; the beta desktop app can do none of those and cannot sit behind the public URL. Naming the harness and its reason costs two sentences and removes the appearance of a category error |
| 58 | A phase 5b: install the plugin into Claude Science and re-run the same gate there, thirty minutes, cut if beta access does not land | One screenshot of this skill running inside the host product is worth more than every paragraph arguing it is an extension. It is optional because it depends on access we may not have, and nothing downstream depends on it |
| 59 | The web app adopts the Claude Science layout: home with the `Needs you` card and template gallery, left rail with rounds as sessions, centre conversation, right artifact panel with tabs | Borrowing the host's grammar makes the argument before anyone reads a word of copy, and it is *less* to build: Setup, Batch review and Progress become tabs in a slot that already exists, and the reasoning panel merges into the centre column instead of being a fourth surface. The rail's session list, dated across six weeks, states the persistence claim at a glance in a way a timeline strip does not |
| 60 | The chrome is labelled a wireframe, in the staged table and on the page | Failure mode one applies to the frame as much as to the contents. We imitate someone else's interface to show where this layer would live; claiming to *be* it would be the exact mock-dressed-as-real the rules forbid |
| 61 | Orchestration runs live in the browser; the verdict stays the human's | These separate cleanly and only the first needs to be live. Under non-negotiable 7 the model produces no numbers, the tests come from the template's allowlist, and the action is one of four verbs — so a live model chooses a sequence from a five-item list and writes prose, which is bounded, cheap and low-variance. The risk the earlier plan avoided was a wrong *verdict* on stage, and the four ruling buttons already absorb it; SPEC.md had already conceded that a visibly rejected wrong recommendation is the better governance demo |
| 62 | One tool-call stream component, driven by either the live model or the committed record | Replay was specified as a rendered JSON blob, which reads as a finished document rather than as reasoning. Animating the recorded sequence through the same component means a cold visitor with no key watches the diagnosis happen, the diagnostics are still genuinely recomputed and checked, and the badge is the only difference between the two modes. One component instead of two |
| 63 | `more_evidence_requested` is exercised, and becomes acceptance criterion 8 | It was defined as a ruling verb and nothing in the build order made it fire. It is the only beat on the list a pipeline cannot imitate, because passing it requires the next action to depend on a human's push-back. Round 4's record becomes two-pass — recommendation, a ruling naming `calibration_by_region`, the test, a revision, the final ruling — which costs one extra recorded pass and no new code |
| 64 | A Notebook tab resolves any number on screen to the `core/` function, source, arguments and input hash that produced it | Claude Science ships a background reviewer that flags *untraceable numbers*; a template makes them impossible to write, and this is that claim rendered rather than asserted. It displays lineage the project already stores, so it costs a component and no plumbing. Cheapest credibility in the build |
| 65 | The claim "a specialized surface beats open-ended chat" is reworded to "typed artifacts and enumerated actions beat free-form output" | The original argued against the shape we are now adopting. The true claim was never that conversation is the problem — it is that conversation whose output is prose cannot be approved, compared across projects, or walked back to evidence. The conversation stays; what it produces stops being prose |
| 66 | The agent gets one line on unflagged rounds | Declining to act is judgment, and an agent that appears only when something breaks is an alarm rather than a colleague. One sentence per quiet round, from numbers already computed |

**What pays for it.** The Pareto scatter, already first-but-one on the cut list, and the
Setup panel as a standalone surface — it becomes a read-only tab. Phase count is unchanged
at nine plus an optional 5b; phases 6 and 7 are re-cut along a better seam rather than
expanded.

**What did not change.** The threshold, the landscape, its parameters, the seed, every
published number, and the rule that `simulate_campaign.py` is the only thing permitted to
read landscape values.

### Claude Science access is confirmed, and phase 5b becomes a gap audit

The user confirmed access to the Claude Science beta, and that it accepts custom MCP
connectors and local skill packs. Decisions 57 and 58 were written under the assumption
that access might not land; it has, and the consequences reach further than making 5b
non-optional.

| # | Decision | Reasoning |
| --- | --- | --- |
| 67 | Phase 5b is a real phase, not an optional screenshot, and it comes off the cut list | The plugin installing into the host and diagnosing round 4 there is the single strongest asset in the artifact. It is no longer contingent on anything, so it stops being contingent in the plan. What goes onto the cut list in its place is the browser's *live* mode, which is the correct trade once the live-agency proof has a better home |
| 68 | 5b's deliverable is the skill running in the host **and** a written audit of where the host's abstractions run out | The artifact's entire thesis is that a gap exists. The host already has projects, Files, persistent kernels, artifacts that ship with their history, skills every future session inherits, and a *waiting on you* queue. An audience that builds it will ask which of those already covers us, and the answer has to come from using the product rather than from reading its page. Any claimed gap that does not survive contact is struck — the threshold discipline, applied to the pitch instead of the science |
| 69 | The web app is reframed as a proposal built on the audit, and the order of the argument is load-bearing | A mockup of someone else's product shown *before* running inside it is a competitor's redesign. Shown after a real campaign in the host, with each element traceable to an audited gap, it is a feature request with a working implementation attached. Nothing about the shell changes; the sequence it is presented in does, and that is what makes it defensible rather than presumptuous |
| 70 | Demo beat 5 moves from Claude Code to Claude Science, with the terminal as the backup | The beat's claim is "same skill, different harness, same batch hash". Running it in the audience's own product makes that claim twice, and the hash match works identically. Claude Code remains the harness that verifies criterion 3, because it is the one that can be scripted, re-run and committed — the repo carries the proof and the host carries the pitch |
| 71 | Each pipeline script gets a `main(argv)` that both the CLI entry point and a kernel call route through, checked at the start of 5b | `SKILL.md` invokes the scripts as shell commands. A notebook-kernel-first harness may prefer to import them, and discovering that midway through the gate looks like the skill failing when it is the invocation path. One implementation serving both surfaces is also the non-negotiable-2 rule applied to invocation rather than to science |

**The risk this creates, recorded because it is the one that would hurt.** If the audit
finds that two of the four claimed gaps are already covered by Files and artifact history,
the deliverable is a shorter list built properly, not the same list argued harder. That
sentence is in SPEC.md's risk section so it is read before phase 6 rather than after.

### Phase 4: the diagnostics, the decision record, and what the writer refuses

The five tests, `run_diagnostic.py` and `record_decision.py`, plus a first ruling in the
committed demo project. Nothing here touches the landscape, the threshold, the
parameters, the seed or any published number; the campaign was re-run and round 2 still
flags at +0.765, round 3 is still clear at +0.048, and round 4 still flags at −2.046 with
a bridge of −1.014 (se 0.059).

| # | Decision | Reasoning |
| --- | --- | --- |
| 72 | `offset_from_controls` reads the bridge estimate the snapshot already carries rather than estimating its own, and adds only the concordance test | `import_round` computed it with `reconcile.offset_from_bridge` and hashed it into the snapshot. A diagnostic that recomputed the same quantity by a second route could disagree with the evidence record about a number they both claim to hold, which is the fork non-negotiable 2 forbids, one level down from the science |
| 73 | The concordance test compares the spread of the bridge deltas against the round's **own** read-noise scale, estimated from the replicate reads, not against a pre-registered constant | The shared designs are the same molecules measured twice, so their deltas should differ only by read noise. Estimating that noise from the round in hand means the test inherits no number nobody checked, and it degrades gracefully if the assay's noise changes — which, in a round that flagged because the assay version changed, is exactly the case that matters |
| 74 | Tolerances go in the template as `diagnostics_policy`, not in the code as defaults: `bridge_concordance_k` 2.0, `replicate_outlier_k` 3.0, `calibration_bins` 4, interval 0.80. Template bumped to 1.1.0 | They decide whether a round may be corrected at all, which makes them triggers, and the anomaly trigger is already a template declaration for the same reason. Declared ahead of any conversation is the template thesis; chosen while reading a round is the thing the thesis is against. Justified in the template's own note, on grounds independent of what round 4 does |
| 75 | `calibration_by_region` takes a **counterfactual offset**, and the offset is a named source (`bridge`) rather than a number | It is the test that separates "an assay shift" from "an assay shift plus something else", and it answers the question a correction is actually making: if this round were only the shift, correcting by it would restore coverage. Accepting a free float would let a number the model typed enter a code path, so the argument names where the number comes from and `core/` fetches it |
| 76 | `residual_by_mutation_class` takes `--by position` or `--by n_mutations`, and nothing finer | Position is the granularity a structure-activity cliff lives at, and it is the cut that rules the cliff out. Mutation count is the cut that shows a model extrapolating past its training set, which is what round 2 turned out to be and what nothing else in the library could see. A per-substitution cut would produce classes of one or two, which invites over-reading noise; that question is the documented ad hoc example instead |
| 77 | `calibration_by_region` uses four bins, not the deciles SPEC.md asked for | A coverage estimate needs enough designs per bin to tell 0.8 from 0.5. At a batch of 48 quartiles give about twelve each; deciles give five, which quantizes coverage to multiples of 0.2 and reports noise as structure. SPEC.md is wrong on this and the rule is to say so rather than build it and hedge |
| 78 | Every test reports `n` and `n_fresh` beside every mean, and `residual_by_mutation_class` reports the size of the *other* side of each comparison | Round 4's position-102 class holds 43 of 46 designs, so "that class against the rest" is a comparison against three. A cause that could explain a whole round has to appear in a class large enough to move it, and the only way to make that readable rather than a trap is to print the counts next to the means. It is also how the in-sample confound in round 2 stays visible |
| 79 | `record_decision.py` **runs the diagnostics itself** and refuses a payload that supplies its own `result` | Non-negotiable 7 said the model produces no numbers, and until now that was a rule in a file. Making the writer the thing that computes closes the channel: the agent names hypotheses, tests and readings, and there is no field through which a number it produced can reach a decision record. `ad_hoc` is the exception and is labelled one-off and unversioned, exactly as specified |
| 80 | The writer refuses four more things: a test outside the template's list, a correction with no concordant bridge, an empty `if_wrong`, and a second pass that ignores the test a ruling asked for | Each was already written down. A rule that is written down and not enforced is a rule the demo has to be trusted about; a rule that returns exit code 2 is one the audience can test. The bridge refusal in particular is SKILL.md rule 2, and refusing to correct when the shared designs disagree is the behaviour SPEC.md calls the better product |
| 81 | `import_round.py --authority decision_NNN` validates the record: it must exist, be ruled, and recommend the action being taken. A policy authority is still taken at its word | "No action is taken on an unruled record" was a sentence. Now a correction cannot cite a ruling that said `refit_only`. Policy authorities stay unchecked because they cover the rounds nobody had to think about — and a policy never makes a flagged round ruled, which is the distinction `project.names_decision` exists to hold in one place |
| 82 | Ruled-ness is a property of the decision record, not of the snapshot's `frame.authority` | The commonest correct ruling on a flagged round — refit and touch nothing — changes no measurement, so it moves no frame and there is nothing for a re-import to record. Deriving it from the frame would mean either leaving round 2 permanently blocked or re-importing it to write a field, which rewrites a snapshot to record that nothing happened. `frame.authority` describes the frame and keeps saying `unruled`, which is true; `project.is_ruled` describes the round |
| 83 | `drop_wells` is implemented as `--drop-plate`, exercised in `check.py` and in no demo round | An enumerated action bound to a code path is worth nothing if one of the four verbs has no code path — that is failure mode 1 inside the governance surface. Plates are the granularity the plate hypothesis is about, and filtering rows before the join is ten lines. No round in this campaign needs it, and the staged table says so rather than implying a demo beat that does not exist |
| 86 | `residual_by_plate` groups by plate only, and the "and by well position" in SPEC.md is struck | The snapshot averages the replicate reads into one record per design and does not carry wells, and the simulated lab has a per-plate offset term and no well-position term at all. A well-position panel over this data is a test that cannot find anything, dressed as a test that could — failure mode 1, inside the diagnostic library. Keeping wells through reconciliation to serve it would change the evidence schema for a result known in advance to be empty |
| 84 | Round 2 is diagnosed and ruled in phase 4; round 4 is deliberately left unwritten | Round 4's record is the hour-5 gate. Writing it by hand now would make the gate a test of whether an agent can reproduce an answer already sitting in the repo. Round 2 is the easier case, wants the opposite ruling, and proves the whole apparatus end to end — so the machinery is exercised and the gate stays a gate |
| 85 | The demo project was rebuilt so the loop actually stops at round 2, rather than being driven past it with `--ignore-flags` | The committed state is now what the product does: stop, diagnose, rule, continue, stop again. Round 4 has no `models/run_004.json` at all, because the loop stopped before fitting it, and that absence is the flagged-round contract rather than a missing file |

**What round 2 turned out to be, which was not what was expected.** Decision 39 recorded
the positive flag as "a model fit on single mutants under-predicts the first double
mutants", and that is right as far as it goes. What the diagnostics show is sharper: over
the 42 fresh picks the model's predictions span **0.009 pKD** while its own predictive
standard deviation averages **0.406**. It was not under-predicting the doubles so much as
declining to distinguish between them — reporting the parent value with wide error bars —
and the +0.765 surprise is what happens when a batch chosen that way turns out to contain
real improvements. No library test reports the spread of the predictions themselves, so
that number is in the record as an ad hoc result with its source inlined, which is the
escape hatch working as designed on its first real use.

The record also names a confound it cannot resolve: the three single mutants that came
back on target are also the designs carried over from round 1, so they were in the
training set, and "the model handles singles" and "the model handles what it has seen"
are not separable from round 2 alone. Round 3 separates them. Saying so in `if_wrong`
is worth more than picking one.

**Two things phase 4 found that were not diagnostics at all.**

`init_project.py --force` rewrote the four top-level files and reset the round graph, and
left every numbered artifact where it was. Rebuilding the demo project therefore produced
a chimera: rounds 1 and 2 from the new build, rounds 3 and 4 inherited from the old one,
under a round graph that had never heard of them. The scripts read artifacts by filename,
so the stale ones were found and used. `--force` now clears the five artifact directories
and prints how many it removed. It is the only thing in the build that deletes anything.

`run_rounds.py` stopped on a flagged round and said to record a ruling, but not how to
resume. The obvious `--start N` re-runs round N from candidate generation and resubmits it
to the LIMS. The stop now prints the exact commands, including the distinction that
matters: a ruling that changes no data goes straight to `fit_surrogates.py`, and only one
that moves the frame needs a re-import.

**On "each under twenty lines".** Three of the five are, counting their arithmetic and
their returned record together. `residual_by_mutation_class` and `calibration_by_region`
run to about thirty, and almost all of the excess is the dictionary they return — the
per-class counts, the comparison against the other classes, the note that gives a number
its scale. The computation in each is under ten lines. The rule's purpose is that an
audience can read them, and padding the count by moving the output into a helper would
serve the number rather than the purpose.

**Checks went from 73 to 103.** The new ones cover the phase-4 done-condition, that
`run_diagnostic.py` writes nothing, each of the five refusals, the two-pass push-back
round trip end to end, that every number in a written record reproduces when its test is
re-run against the hashed inputs, that both halves of the fourth verb work — a ruling can
drop a plate's wells and nothing can drop them without one — and that round 2 is ruled
while having moved nothing.

### Where this sits in the literature, and what it does not change

Two preprints were read in full and compared against the build: Bachas et al. 2022
(Absci, `10.1101/2022.08.16.504181`) and Frey et al. 2025 v3 (Genentech / Prescient
Design, *Lab-in-the-loop*, `10.1101/2025.02.19.639050`). Nothing in `core/`, the
landscape, the parameters, the threshold or any published number moved as a result. The
outcome is three recorded decisions and one number quoted beside our own.

| # | Decision | Reasoning |
| --- | --- | --- |
| 87 | The README states the design space is `trast-1`'s and says in the same paragraph that every affinity value is synthetic | The arithmetic is exact and worth claiming: Bachas's space is up to double mutants over eight CDR-H3 positions of trastuzumab excluding cysteine, 1 + 8·18 + 28·18² = 9,217, of which they measured 8,932 — the 97% they report. Ours is the same form over all twenty letters, 1 + 8·19 + 28·19² = 10,261, with cysteine removed downstream as a declared liability. That makes the `data/oracle.py` swap a genuinely one-file change rather than an aspiration. But "our use case is based on Bachas" is the sentence failure mode 1 exists to prevent — the design space is borrowed, the measurements are `data/synthetic.py`. Both halves are stated together or neither is. Caveat recorded: the paper's Table 1 is an image and does not give the eight positions in text, so *which* eight is unconfirmed; ours is `GGDGFYAM` at VH 99–106. Checking that against the release is step one of the swap, not a blocker to the claim about shape |
| 88 | The template's `source` field has exactly two values, `measured` and `computed`, and a third for predicted properties is **not** added now | This is a real schema gap and the literature names it twice: Bachas's *naturalness* is a protein-language-model likelihood used as an optimization objective, and Frey's non-specificity is a surrogate trained on 2,305 BV ELISA measurements. Neither is measured, and neither is an exact calculation. The current schema would have to lie about one or the other. It is not filled today because a third category forces a decision about what non-negotiable 7 permits — a pLM score is deterministic and hashable, which is the letter of the rule, but it is not fifty lines of numpy an audience can check, which is its purpose. That argument is worth having once there is a predicted property to have it about, and inventing one to motivate the schema would be building the abstraction before the need |
| 89 | Expected improvement on affinity alone is recorded as a deliberate simplification with a named successor, rather than left as an unmarked gap | Frey selects with Noisy Expected Hypervolume Improvement over a Pareto front in affinity × expression. Ours is single-objective because exactly one property here is measured, so there is no frontier to expand — `core/scoring.py` already argues that exact scores become filters rather than objectives, and Frey independently does the same for liability motifs and conserved residues. The distinction is not EI-versus-NEHVI as a matter of taste; it is that a second *measured* objective is what creates the need, and that is step 3 of the extension path. Naming the successor costs a line and stops the simplification reading as an oversight |

**The number quoted beside our own.** Frey's matched random baseline — control designs
drawn from repertoire mutations, matched on count and on mutational load — produced the
best binder for three of five seeds; the control won the other two. Our guided arm is
never slower than random on any of twenty paired seeds, at p = 0.0078. Both facts are now
in the README, adjacent. The comparison is not apples to apples and the README says why,
but a pitch that cites *Lab-in-the-loop* as the industrial-scale target and omits its
baseline result is citing it selectively, and this audience will have read it.

**What was considered and rejected.** Reporting held-out R² against the replicate-
agreement ceiling, as Bachas does, is a better statistic than absolute R² and the inputs
already exist — `replicate_concordance` estimates the round's read-noise scale, 0.171
pKD in round 4. It is not built because it touches `core/diagnostics.py` and the
invariant set before the hour-5 gate, and the gate is what phase 5 is for. Recorded here
so it is a choice rather than an omission. Widening the mutation budget across rounds, as
Frey ramps 6 → 8 → 12, is rejected outright for this build: decision 22 fixed the
landscape at additive-plus-pairwise *because* `max_mutations = 2` makes higher-order terms
unreachable, so widening the budget would invalidate the landscape's own justification —
and the landscape does not move.

### Phase 5: the two connectors, the plugin, and the hour-5 gate

Both servers, `.mcp.json`, an installable plugin, and the gate run twice — once for
criterion 3 and once for criterion 2. Nothing here touches the landscape, the threshold,
the parameters, the seed or any published number. Round 4 still flags at −2.046 with a
bridge of −1.014 (se 0.059); the difference is that a record now says what that means,
and no human wrote it.

| # | Decision | Reasoning |
| --- | --- | --- |
| 90 | `mcp/` is renamed `connectors/`, and decision 48's mitigation is struck as tested-and-wrong | Decision 48 kept the directory named `mcp/` on the grounds that holding "nothing importable" inside it would stop it shadowing the PyPI `mcp` distribution. That is false, and the test is one line: with the repo root on `sys.path`, `import mcp` resolved to the empty `mcp/` folder, because Python treats any bare directory as an implicit namespace package. The reasoning behind 48 was right and the remedy did not implement it. `connectors/` removes the class of problem rather than managing it, costs one line in CLAUDE.md's non-negotiable 4 and one in the repo map, and is the word the rest of the build already uses. `check.py` now asserts that `import mcp` reaches site-packages, so the claim is checked instead of assumed twice |
| 91 | The official `mcp` SDK, not the standalone `fastmcp` package and not a hand-rolled JSON-RPC loop | Three options were weighed. A hand-rolled stdio server is about 120 lines, keeps the dependency list at numpy and matplotlib, and is readable the way `core/` is — genuinely tempting for this repo's ethos. It was rejected because phase 5b is the strongest asset in the artifact and its failure mode would be a protocol detail the host rejects, which is a hour lost to something that has nothing to do with the science. `fastmcp` 2.x depends on the official SDK anyway, so it is strictly more surface for the same two servers. The SDK is a *connector* dependency in the same sense matplotlib is an *evaluator* dependency: `core/` has not heard of it, and `check.py` asserts that |
| 92 | SPEC.md says "FastMCP" and the code says `MCPServer`, because the SDK renamed it | `mcp.server.fastmcp.FastMCP` is gone in SDK 2.x; the class is `mcp.server.mcpserver.MCPServer` and the import raises with a migration note. Recorded rather than silently absorbed, because SPEC.md names the brand in three places and a future reader comparing the two would otherwise wonder which is wrong. The decorator-per-tool shape SPEC was describing is unchanged |
| 93 | Every refusal is raised as the SDK's `ToolError`, not as a bare exception | A bare exception reaches the client with the reason withheld and a traceback in the server log. (Corrected in 5b: the `Error executing tool <name>:` prefix is the SDK's own marshalling and is present on both 1.x and 2.x whatever we do. What `ToolError` buys is the readable sentence *after* the prefix, and that is the whole of the claim — decision 104.) Every refusal in these two files is deliberate — a round already submitted, an unwired backend, a construct that does not exist — and a refusal whose reason the agent cannot read is indistinguishable from a crash. The refusals *are* the deliverable here: criterion 6 is a tool list, and the `esm_live` error is the whole claim that the provider interface does not quietly substitute one-hot for an embedding |
| 94 | `lims.py` grew `submit_project_batch` and `pull_to_csv`, and `main` now calls them | Decision 71 put a `main(argv)` on every pipeline script so one implementation serves two invocation paths. The submission path needed the same treatment one level up: the orchestration a submit does — read the batch, resolve the designs, mint, write the refs back, link the round — lived inside `main`'s argparse branch, so the connector would have had to either reimplement it or shell out and parse stdout. Now `main` prints what the function returns and the connector serializes it, and `check.py` compares the two exports byte for byte |
| 95 | `pull_assay_results` writes the CSV and returns a summary; `list_designs` caps at 25 | Ninety-six rows of assay export is not something an agent should read, and the next command needs a path rather than a table. The tool returns the counts, the statuses, the columns and the exact `import_round.py` invocation that consumes it. Same reasoning for the 180-construct registry: the count is the useful part of the answer and the records are available on request. This is a judgment about what a tool result is *for*, and it is written down because the opposite choice — return everything, let the model filter — is the common one |
| 96 | `predict_structures` returns nulls, not a plausible-looking confidence | SPEC.md asked for "a cached result with an honest note". A cached result with a pLDDT in it is a number an audience can read off a screen, and it would be invented. The tool returns `prediction: null`, `confidence: null`, `computed: false` and a note saying no structure model runs anywhere in this build — failure mode 1, refused inside the one file where blurring it would be easiest. Nothing downstream reads it, and the staged table says so |
| 97 | The gate runs in a tree with `README.md`, `SPEC.md`, `DECISIONS.md` and `CLAUDE.md` removed, and the isolation is described honestly rather than overclaimed | All four discuss round 4, two of them give the answer. A gate run in this repo as it stands would test whether an agent can find a conclusion already written down. `decision_004.json` comes out of the copy for the same reason; `decision_002.json` stays, because it is the project's own state and a scientist picking up a flagged round would read the last record too. `data/` has to stay, because the registry connector imports the oracle — so the tree denies `Read` on it, the prompt says it is off limits, and the transcript is grepped afterwards. That is a guard and not a sandbox. Both runs came back with zero accesses and the round-1 session volunteered that it had not read it, which is evidence and not proof, and the distinction is stated where the transcripts are |
| 98 | The transcripts are committed raw as well as digested | `gates/*.md` is the readable version and `gates/*.jsonl` is what the session actually emitted. Keeping only the digest would mean the evidence for the central agentic claim is a file this build wrote about itself. The raw transcripts also carry the awkward part: both sessions show an `API Error` on the turn after the `Skill` call, a safeguard flag tagged `[bio]` on an antibody-engineering prompt. The skill content did land — it is the next message in the stream, and `check.py`'s sufficiency claim rests on that — and both sessions continued. It is left in, because a transcript with the inconvenient part edited out is not a transcript |
| 99 | `decision_004.json` is committed exactly as the gate wrote it, unruled, and will not be hand-edited | Its entire value is that no human touched it. `check.py` recomputes all eight of its results from the hashed inputs, so the record is verifiable rather than trusted, and the moment it is edited by hand that property is gone and cannot be recovered. The session itself found a real gap in it — all four cross-version anchors sit on plate R4P1 and the record does not say so — and declined to delete the record to work around the writer's refusal of a second open pass, naming `more_evidence_requested` as the clean route instead. That is the governance surface holding against the agent that wanted past it, which is the only test of it that means anything, so the gap stays until a ruling opens pass 2 |

**What the gate found that phase 4 had not.** Phase 4 could say the round-4 remainder was
not the cliff, and therefore was the model. The session said *which* model error, in an ad
hoc cut it wrote itself after observing that the library's position test could not
resolve it: position 102 appears in 43 of 46 designs, so the class is the round and no
contrast exists inside it. Dropping to residue level, **40 of the 42 fresh designs carry
G102L**, which the model had seen in exactly one measured design — the round-3 incumbent
`G102L+A105K` at 11.837. `ridge_onehot` is additive, so it credited that pair's whole
gain to two main effects and applied G102L to 40 new partners; all 40 fell short, across
six partner positions, with no partner carrying it. In the corrected frame the G102L
doubles average 9.490 against a parent of 9.230 — **G102L alone is worth about +0.26, not
+1.80, and the incumbent's affinity belongs to the pair.** Round 4 advanced nothing,
because the optimizer spent 40 of 48 wells re-testing one main effect it had one
observation of.

Three things about that are worth saying. It is a **finding about the optimizer**, which
means the loop is now producing evidence about itself rather than only about the
molecules. It arrived through the documented escape hatch — ad hoc, read-only, source
inlined, labelled one-off, `stdout` stored beside the code — so no number the model
produced entered a code path, and non-negotiable 7 held under the one condition that
tests it. And it is the clearest available answer to the ninety-second objection: a
scheduler calling five scripts in order produces the flag, and does not produce that
paragraph.

**What was considered and not done.** Ruling `decision_004` was left to a human, which is
the point of the phase and not an omission — the demo opens with round 4 open. Advancing
the committed project past round 4 waits on that ruling. And the amendment the session
asked for, naming R4P1 as the shared plate of all four anchors, is not written in, because
writing it means either a ruling or an edit by hand and the second is decision 99.

**One thing to check first in 5b, before anything else.** The plugin's connectors name
`${CLAUDE_PLUGIN_ROOT}/.venv/bin/python`. Installed anywhere that interpreter is not
beside them, both servers fail to start and the failure looks like the plugin being
broken rather than the environment being incomplete. Whether the host can run a Python
stdio connector at all — and how it expects the interpreter to be declared — is a gap
question in its own right, and it belongs at the top of the audit rather than discovered
halfway through it.

**The install command is a command that has been run.** `claude plugin marketplace add`
and `claude plugin install adaptive-optimization@adaptive-workbench` both succeeded, and
from an unrelated working directory `claude mcp list` reports
`plugin:adaptive-optimization:registry` and `:bioprovider` connected, with
`${CLAUDE_PLUGIN_ROOT}` expanded to this repository. That closes the local half of
SPEC.md's packaging section; the host half is 5b. Two configurations exist and they
differ only in how they spell the path — `.mcp.json` relative, for a clone opened
directly, and the same two servers inline in `plugin.json` under `${CLAUDE_PLUGIN_ROOT}`,
for an install. `check.py` asserts both name the same two servers and that every path in
either one exists.

**A safeguard refusal fired three times during the gates, and it changes one thing in
phase 7.** Both gate sessions show `API Error: Opus 5's safeguards flagged this message`,
category `bio` — twice in the round-4 run, once in the round-1 run, across roughly a
hundred turns of antibody-engineering content. It cost nothing either time: Claude Code
retried, one refused turn emitted a malformed `Grep` call that errored and was reissued,
and both sessions completed with correct output. The gate is unaffected and the record
verifies.

| # | Decision | Reasoning |
| --- | --- | --- |
| 100 | `netlify/functions/ask.ts` sends `fallbacks: "default"` with the `server-side-fallback-2026-07-01` beta, checks `stop_reason` before reading `content`, and treats a surviving refusal exactly as it treats the budget cap | The browser path is a single-shot proxy with no agent loop, so nothing retries for it. A refusal is **HTTP 200** with no usable content and a populated `stop_details`, which means the naive read — `content[0].text` on a 200 — renders an empty bubble in front of the audience and looks like the product being broken. The server-side fallback re-runs the request on another model inside the same call and would have absorbed all three of the gate's refusals; a decline before output is not billed. If the whole chain declines, the badge flips to verified replay, which is a door into a room that already exists rather than new machinery. Recorded now because it is a two-line requirement that is very expensive to discover on stage |

**What is *not* being changed, and why.** The model stays `claude-opus-5`: three fires in
a hundred turns on content that is exactly what this build is about, every one of them
recovered, is not evidence for a downgrade, and the audience for this pitch will find the
subject matter unremarkable. The gate transcripts keep the error text rather than editing
it out — decision 98. And nothing about the CLI path changes, because Claude Code's own
retry is the handling.

**The open question this leaves for 5b.** The same content will run in Claude Science
against the same classifier family. Whether it fires there, and whether the host recovers
as gracefully as Claude Code did, cannot be answered from here. It goes on the 5b
checklist beside the interpreter question, and whatever happens gets written down —
including "it never fired", which is the likeliest outcome and still worth recording
once rather than wondered about twice.

### Phase 5b: what the install into Claude Science cost, and what that is evidence of

The skill and both connectors are installed in Claude Science and serving tools. The
round-4 gate has not been re-run there yet and the gap audit is not written; this section
records only the install, because what the install took is itself a finding and it is
better written down while the error messages are still in front of us.

Nothing here touches the landscape, the threshold, its parameters, the seed, or any
published number. `check.py` passes 131/131 before and after, and the host's interpreter
reproduces the committed one-hot hash `sha256:4f6ba1ff3d2c` exactly, on numpy 2.5.2
against the `.venv`'s 2.5.3.

| # | Decision | Reasoning |
| --- | --- | --- |
| 101 | Both connectors import `MCPServer` (`mcp` 2.x) or `FastMCP` (`mcp` 1.x), whichever is present, and pass `version=` only where it is accepted | Claude Science resolves a bare `python` connector command to its own bundled environment, which carries `mcp` 1.27.1; this repo's `.venv` carries 2.2.0, where `FastMCP` was renamed and `version=` dropped. Pinning either one strands the other surface. A thirteen-line try/except at the import site keeps one implementation serving both, which is non-negotiable 2 applied to the transport layer rather than to the science. `core/` has not heard of it, and the tool lists, the refusals and the one-hot hash are identical under both SDKs |
| 102 | The sandbox grant lives in `~/.claude-science/config.toml` and is not vendored into this repository | It is host configuration on one machine, not project state, and it names an absolute path that is wrong everywhere else. The README carries the block to copy. Putting it in the repo would also imply `check.py` could verify it, and `check.py` verifies this repository rather than the machine it is on |
| 103 | The write grant is `lims_store/` alone, not the repository | The registry is the only connector that writes, and it writes one directory. Granting the repository would hand a connector write access to `core/`, the project state and the gate output, which is the opposite of the boundary this build is arguing for. Reads and writes are separate keys in the host's schema, so the narrow grant costs nothing |

**Four faults, each of which hid the next.** Written out in the README because only the
first and the last say what is wrong. The sandbox refuses to exec an interpreter in the
user's home directory, so `.venv/bin/python` never starts. A command line with no script
argument produces a bare Python that reads the JSON-RPC stream as a program and answers
nothing at all — no error, no timeout, no log line, just a spinner. The host's SDK is a
major version behind the one the connectors were written against. And the connector
cannot see the repository its own code lives in until `[sandbox] user_read_paths` grants
it, which needs a restart. Three of the four are invisible in the Add-connector dialog.

**The finding this makes, and it is better than the one that was pre-registered.** The
claimed gap was that the host has no packaging unit. What is actually true is narrower
and harder to dismiss: **a connector that carries its own interpreter and its own state
cannot be installed through the connector interface alone.** The host has every primitive
needed — sandbox grants, per-tool approval with four scopes, a local-command transport —
and no way for a connector to *declare* what it requires. `plugin.json` states the
interpreter, both servers and the skill in one file; in the host those became three
manual acts, one of them an undocumented TOML key found by reading an error message and
then the application binary.

**And the half of it that runs the other way, recorded because the discipline says so.**
`Import from GitHub` **does** read `.claude-plugin/marketplace.json`. It resolved
`skills/adaptive-optimization` out of the manifest, and it wrote the commit it came from
beside the installed copy — `sha db99c082`, with the plugin and marketplace names. So the
manifest is read for the skill and ignored for the connectors, and the host records skill
provenance to the commit. That is real traceability for the instructions layer and it
partially covers the claimed traceability gap. What survives is the narrower claim: the
host versions the *skill*, and nothing versions the *number a skill produced* back to the
`core/` function and the input hash that produced it. The audit takes the narrower claim.

| # | Decision | Reasoning |
| --- | --- | --- |
| 104 | The `Error executing tool <name>:` prefix is the SDK's, it is not removable, and `check.py` now pins the whole payload shape rather than only the reason | Phase 5's write-up claimed refusals reach the caller "as a message rather than as `error executing tool`". Reading the wire in the host showed that is false, and testing both SDKs showed it was never true: `mcp` 1.27.1 and 2.2.0 both prefix the text, so the claim did not describe our code on either surface. `check.py` asserted only `isError` plus the substring "already been submitted", which is why a wrong sentence survived 131 checks. It now asserts the prefix *and* the sentence after it, so the claim cannot be re-worded back into being wrong. What `ToolError` actually buys is unchanged and is still worth having: the reason instead of a traceback |

**What this cost and what found it.** A documentation claim that was wrong from the day
it was written, caught by running the same connector under a second client with a
different SDK. Nothing in the code changed. This is the phase working as intended — not
every finding is about the host, and the discipline of striking claims that do not
survive contact applies to our own sentences first.

**A test-hygiene rule, learned the expensive way.** During this session the committed
LIMS store was reverted with `git checkout` while an agent in the host was mid-way
through reasoning about a write it had just made. The agent went looking for its own
write, correctly found it gone, and reported its previous turn as wrong — offering two
hypotheses, both of them wrong, because the real cause was outside anything it could
observe. No state is to be reverted underneath a running session. The revert waits until
the session is finished, and any cleanup that cannot wait is told to the session in
words.

**What the install did not answer.** Whether the connector can write `lims_store/` through
the grant — the tools load, but no `submit_batch` has run in the host. Whether the
scripts resolve, given that the skill's copy of them now lives in the application's data
folder while `SKILL.md` names them by repository-relative path and the repository is
granted separately. And whether the `bio` safeguard fires there, which is still the open
question decision 100 left.

### Phase 5b: the gap audit

The round-4 diagnosis ran in Claude Science and reproduced every number. What follows
grades the four gaps this artifact claims against what the product actually does, using
only what was observed today. Decision 68's rule applies: a claimed gap that does not
survive contact is struck or narrowed, not argued harder.

**What the host run is evidence of, and what it is not.** The Claude Code gate removes
`README.md`, `SPEC.md`, `DECISIONS.md`, `CLAUDE.md` and `decision_004.json` from the
tree, because it tests whether `SKILL.md` and the five diagnostics are *sufficient*. The
host session had the whole repository, including `decision_004.json`, and said so: *"A
proposed decision record for round 4 already exists on disk. I'll re-run the diagnostics
myself rather than take its reading on trust."* It then re-ran all five tests and its
numbers reproduce independently. That makes the host run strong evidence that the stack
**runs and reproduces** in the host, and weaker evidence for sufficiency than the Claude
Code gate. Criterion 3 therefore stays anchored in Claude Code, which is what SPEC.md
said from the start: the repo carries the proof, the host carries the pitch.

| # | Claimed gap | Verdict | Evidence |
| --- | --- | --- | --- |
| 105 | A ruling has no type | **Survives, narrowed** | The host has a real, scoped approval primitive — permission cards for folder access, code execution and each connector tool, with Once / This conversation / This project / Global, all revocable in Settings > Permissions. That is more governance than the claim credited it with, and the claim is reworded accordingly. What it gates is **access**, not **decisions**: there is no typed decision over a domain object, no enumerated verbs bound to code paths, no hashed evidence, no `if_wrong`. The host session wrote *"No action may be taken until a named approver rules on it"* — but that rule came from `SKILL.md` and is enforced by `record_decision.py`, not by the product. Nothing in the host represents "round 4 is waiting on a ruling" |
| 106 | `rounds.json` has nowhere to render | **Survives** | The left rail listed three sessions — *Diagnose Round 4…*, *Run evaluate_prior.py Round 3*, *List Designs Registry Connector* — chat threads named after what was asked. A six-week campaign is a round graph, and the host has no view of one. This is the gap that changed least on contact |
| 107 | Traceability is an after-the-fact check | **Survives, heavily narrowed** | Two things cut against it. The host records skill provenance to the commit — `.import-origin` carries `sha db99c082`, and **Check for updates** flags a skill behind its repository. And it ships a background reviewer for untraceable numbers. But the reviewer raised nothing across every session today, and from outside we cannot distinguish *passed the check* from *was not checked*, so it is recorded as neither. The traceability in the memo — input hashes beside every figure, `core.diagnostics` named as the source — came from the skill and the scripts, not from the host. The surviving claim is exact: **the host versions the skill; nothing versions the number a skill produced back to the function and the input hash that made it** |
| 108 | No project instantiation from a declaration | **Survives, but under-tested** | A host project is a session container with custom instructions and persistent folder grants. It does not instantiate `objectives.json`, and it has no notion of a constraint ruleset enforced in code before optimization runs. But no template was instantiated in the host today, so this rests on the product's shape rather than on an experiment. Recorded as the weakest of the four, and phase 6 should not lean on it |

**Three gaps found that were not claimed, and they are better than two of the four.**

| # | Found | Why it matters |
| --- | --- | --- |
| 109 | **A connector cannot declare what it needs.** Installing these two took a bare interpreter name that is the host's and not the one `plugin.json` declares, a full command line in a single field, and a hand-written `config.toml` with an undocumented `[sandbox] user_read_paths` key, plus a restart | `plugin.json` states the interpreter, both servers and the skill in one file. In the host those became three manual acts, one of them undocumented. The host has every primitive needed — sandbox grants, per-tool approval, a local-command transport — and no way for a connector to say what it requires. This is the sharpest finding of the phase |
| 110 | **The connector sandbox and the agent sandbox have separate grants.** `pull_assay_results` wrote a CSV and the agent in the same session could not read it: *"The CSV sits inside the workbench repo, which isn't in my host grants"* | The registry's contract is *here is a path, now run `import_round.py` on it* — it even returns the command. The connector produces an artifact, names it, and the agent that called it cannot open it. Nothing in either grant declares the dependency between them. Two mechanisms for one directory |
| 111 | **A local-command connector with a missing argument fails silently.** Bare `python` with no script reads the JSON-RPC stream as a program and answers nothing: no error, no timeout, no log line, an indefinite spinner | The host validates that the command resolves, not that the process ever speaks MCP. A handshake deadline saying "started but never completed `initialize`" would have turned a long dig through `~/.claude-science/logs/` into one line. The cheapest, most concrete product feedback in the audit |

**What the host does well, recorded because an audit that only finds fault is not an
audit.** Local stdio connectors run at all, which was the question that could have ended
the phase. Per-tool approval carries four scopes and is revocable in one place. Skills
import from a private GitHub repository, record the commit, and flag when they fall
behind. The persistent kernel's starter environment carried numpy and reproduced
`sha256:4f6ba1ff3d2c…` and every diagnostic to the digit under a different Python and a
different numpy. And the sandbox error message named the exact configuration key, the
exact remedy and an alternative — the abstraction running out honestly, which is the
strongest version of this whole argument.

**The `bio` safeguard never fired.** Not once, across every session today, on content
that is exactly what this build is about. Decision 100 left that open for 5b; it is
closed, and the answer is the one that was likeliest and still worth recording rather
than wondered about twice.

**What phase 6 builds against.** Gaps 105, 106 and 109 — a typed decision with enumerated
verbs and hashed evidence, a round graph with somewhere to render, and a declaration of
what a connector needs. 107 is narrowed to one sentence about numbers rather than skills
and should be made in one component, not argued at length. 108 is under-tested and the
shell should not lean on it.

### What phase 5b taught about working inside the host, kept for phases 6 to 9

The gap audit records what the product is missing. This records what using it was like,
because several of these change what later phases should do.

**One mental-model difference explains all four install faults, and it will explain the
next one.** Claude Code treats a connector as a *declaration*: `plugin.json` names the
interpreter, both servers and the skill, and the loader satisfies it. Claude Science
treats a connector as *a program it runs on your behalf*: you supply a command line, it
supplies the interpreter, the sandbox and the working directory. Every fault today was
that difference surfacing one layer at a time — the interpreter it refuses, the arguments
it expects inline, the SDK version it brings, the filesystem it will not show you.
Nothing was broken. When something else fails in the host, look for the next place we
assumed declaration and the product assumed execution, before looking for a bug.

**Failures cluster at seams neither side owns, and they are silent.** A connector with a
missing argument loads forever with no log line. A connector writes a file the agent that
called it cannot read. A configuration key takes effect only after a restart nothing
prompts for. The loud errors — the `execvp` refusal, the sandbox visibility message —
were the easy ones, and the sandbox message was genuinely excellent. Budget time for the
quiet ones, and treat "it is still loading" as a diagnosis rather than a wait.

**The application's own state files are better documentation than the documentation.**
`~/.claude-science/mcp/local-mcp.json` identified two of the four faults faster than the
dialog did; `~/.claude-science/logs/spawn.log` and the strings in the binary produced the
`[sandbox]` schema that the published configuration reference omits entirely. The docs
also described an Advanced-settings arguments field that the form does not have. For a
beta product, verify against the artifact and keep the docs for orientation.

**Determinism held across three numpy versions, and that is what makes demo beat 5
safe.** The `.venv` runs numpy 2.5.3, the bundled connector environment 2.5.2, the
analysis kernel 2.4.6 on Python 3.11. All three reproduce `sha256:4f6ba1ff3d2c…`, the
−1.014229 offset, 0.342449, and a byte-identical `batch_003.eval.json`. The hash-match
beat was never guaranteed by anything we control — it is a property of the numbers being
integer-ish work over hashed inputs, and it now has evidence behind it rather than hope.

**The agent's conduct in the host is the specification for phase 7's centre column.**
Across five sessions, unprompted: it re-ran five diagnostics rather than trust a decision
record sitting on disk; it read a guard in `lims.py` *before* sending a call that might
half-apply; it said "I read the head and the failed rows only" instead of implying it had
read the file; it gave two hypotheses for a missing write and refused to pick; it named
the `fair-esm` escape hatch and asked about provenance before taking it; it refused to
size a correction to make residuals vanish. **Phase 7 should render these, not just the
tool calls.** A stream of green ticks is a pipeline with better typography; the partial
knowledge, the declined choice and the stop for a human are the claim.

**Do not build a claim on the host's reviewer.** It raised nothing across every session,
against numbers that were in fact fully traceable. From outside, *passed the check* and
*was not checked* are indistinguishable, so the Notebook tab's line stays as decision 107
words it — the host versions the skill, nothing versions the number — and never "their
reviewer missed this."

**Demo-day risk, and it is the largest one this phase created.** Beat 5 now depends on a
machine where the skill is imported, both connectors are configured, `config.toml` carries
two sandbox grants, and the app has been restarted since. That is a multi-step manual
install including an undocumented key. **It cannot be done live and it does not travel.**
Demo from a machine set up and verified beforehand, check the connectors list green
before the room fills, and keep Claude Code as the stated fallback for the beat — which
decision 70 already allows for a different reason.

### Phase 6: the browser, and what building it found

The web app boots Pyodide, mounts the repository's own modules, and runs the
round loop against the visitor's own copy of the project. Approving round 4
flags it in 1.5 seconds, the diagnosis recomputes all eight tests, a named
person rules, the correction runs under that ruling, and round 5 is selected —
about six seconds end to end including the boot.

The shell is Claude Science's, as decision 59 settled, and it is labelled a
wireframe in a strip across the top of every screen. What it holds is not a
wireframe: the panels read the project's own JSON, the tool-call chips are
commands that actually ran, and the numbers come out of `core/`.

| # | Decision | Reasoning |
| --- | --- | --- |
| 112 | The browser **mounts** the repository rather than bundling a copy of it. `web/bundle.py` copies `core/`, `data/`, `lims.py` and the seven scripts byte for byte into the same directory shape, records a sha256 per file in a manifest, and `check.py` fails if any of them drifts from its source | Non-negotiable 2 says the science is never implemented twice, and the browser is the surface where a fork would be most tempting and least visible — a "just this one function in JavaScript" is a fifteen-minute change nobody would notice. Copying into the repo's own layout means every `sys.path` walk and every `dirname(__file__)` inside those modules resolves the way it does on a laptop, so Pyodide imports the same code the CLI imports rather than a port of it. The manifest turns "we promise it is the same" into a check |
| 113 | `web/py/wb_driver.py` is the only new Python, it calls each script's `main(argv)`, and it computes nothing | Decision 71 put a `main(argv)` on every script for exactly this. The driver is `run_rounds.py` with the subprocess taken out: same scripts, same order, same arguments, stdout captured instead of inherited. Anything it computed would be a second implementation of something, so it computes nothing — including the progress line, which is `core.reconcile.pool` over a prefix of the snapshots |
| 114 | The state the browser opens on is **derived** from the committed project by rewinding round 4, and the derivation is proved by replaying that round forward and comparing against the committed snapshot | A hand-written demo state is a fixture, and a fixture that drifts from the project is failure mode one with extra steps. The rewind removes round 4's snapshot, evaluation and decision, un-mints its registry ids, and then `bundle.py` replays submit → pull → import → score and requires the returned snapshot to match `snapshot_004` in every field. If the rewind were wrong the replay would not reproduce it |
| 115 | What ships is the **unapproved** round-4 batch record, not the committed one | `--approved-by` stamps `approval.at` inside the hashed body, so an approved batch record can never be reproduced on another machine or at another moment. Without a signature the record is a pure function of the pool, the model run and the objectives, and every surface that selects that batch prints `ff8df7984a20`. This is also the honest version of the demo: approving is what the visitor is there to do, and the batch should be waiting for them rather than already signed |
| 116 | The cross-surface identity claim is therefore made on **selection records**, and acceptance criterion 7 is checked on `batch_005` | An approval timestamp propagates: batch → snapshot → model run → next batch, because each record hashes its inputs. So two surfaces that both ran the round can agree on every number and still disagree on every hash below the signature. Stating the claim on the unsigned record is not a weakening; it is the only version of the claim that was ever true, and it is now mechanically checked |
| 117 | The proposal that ships with the bundle is `decision_004.json` with every `result`, `source` and `inputs` block **stripped out**, and the browser re-runs all eight tests | What survives is what the agent contributed: the claims, which test each rests on, how it read the answer, and the recommendation. `record_decision.py` refuses a payload carrying its own results, so the browser could not smuggle a number in even if it wanted to. A figure that appeared in the browser without being recomputed there is exactly the failure non-negotiable 7 exists to prevent |
| 118 | Pyodide 314.0.7 (Python 3.14.2, numpy 2.4.6), with the runtime and the one wheel served from the site's own origin and the wheel's sha256 checked against pyodide's lock file at build time | SPEC.md's rule: a demo that depends on a third-party CDN and conference wifi at the same moment has a coin flip in it. `core/`'s single dependency is what makes this cheap — 13 MB of runtime and one 2.8 MB wheel, and nothing else to fetch |
| 119 | A visitor's rounds live in Pyodide's filesystem and in `localStorage`, as an **overlay**: only files that differ from the shipped bundle are stored, keyed by the manifest hash | The project is 1.6 MB and `localStorage` is about 5. Storing the diff keeps a full campaign near 1.1 MB, and keying on the manifest means a new bundle starts clean instead of merging a visitor's round 5 into a project that has changed underneath it. Every read and write is wrapped, because a private window can refuse both |

**What building it found, and the two things that changed elsewhere.**

| # | Found | What was done |
| --- | --- | --- |
| 120 | **`evaluate_prior.py` has to run again after a correcting re-import, and `SKILL.md` did not say so.** The evaluation records the hash of the snapshot it scored against; a ruling that moves the frame leaves that pointer aimed at a snapshot that no longer exists, and its residuals describe a frame the project has abandoned | Step 9 of the diagnosis procedure now says to re-score before fitting. The pair runs together on the way in and it runs together on the way back. The hour-5 gate transcripts were produced against the earlier wording; this changes no diagnosis and no number in them, only what happens after a ruling |
| 121 | **Round 5 flags too, at −0.818 pKD, and it is real.** The CLI reproduces it to the digit from the same state. The evaluator's fully-corrected guided arm does not flag round 5 (+0.358) because it corrects every round at import; the product path corrects a flagged round only under a ruling, so rounds 2 and 3 are pooled differently and the model that selects round 5 is a different model | Recorded rather than smoothed. It is the `if_wrong` clause of `decision_004` coming true in the half that predicted it — *the refit still over-predicts* — and it means **phase 7's live agent has a round to diagnose that nothing in this repository has diagnosed before.** That is a better test of the agentic claim than replaying round 4, and phase 7 should use it as one |

**The centre column, and what phase 6 deliberately left for phase 7.**

The session's tool-call chips are not an animation: each one is a command that
ran against the visitor's copy of the project, with its exit code and both of
its output streams. `run_diagnostic.py` prints its record on stdout and its
human summary on stderr, so the driver captures the two separately — merging
them made the record unparseable, which is how that was noticed.

The composer is present, disabled, and says why: the host's approval primitive
is an untyped chat interrupt, and the ruling here deliberately does not go
through the text box. Above it sit four verbs bound to code paths, with hashed
evidence and an `if_wrong` line — gap 105, rendered. The rail carries exactly
one new item, **Rounds**, which is gap 106; everything above it already exists
in Claude Science and is drawn, labelled and inert rather than faked. The
template gallery carries a requirements table assembled by `bundle.py` from
`plugin.json`, `marketplace.json` and the two connector modules, with a column
for what each row cost by hand in the host — gap 109. The Notebook tab resolves
any figure on screen to the `core/` function that produced it, its file, that
file's sha256 and its input hashes — gap 107, narrowed to one component as the
audit said to narrow it. Gap 108 is not leaned on: the gallery says plainly
that instantiating a second project is not wired up in this build.

What phase 7 inherits: the model in the centre seat choosing the sequence, the
push-back round trip that makes `more_evidence_requested` fire, and round 5 as
a round nobody has diagnosed yet.

---

## The web app redesign — decisions 122 to 133

Between phase 6 and phase 7. It changed where things live, what they are
called, what a session is, and how a round gets from approval to data. It
changed nothing in `core/`, nothing about the landscape or the threshold, and
no published number. Both gates still hold and `check.py` went from 147
invariants to 160 without a single existing one being relaxed.

**What was wrong.** The first load gave a visitor, at once: a wireframe
banner; a left rail branded *Adaptive workbench* whose five host items opened
essays in the centre column; a centre column headed *Good afternoon* trying to
be a home page; and a right-hand artifact panel already showing round 4's
48-well batch table, for a round nobody had opened. Four separate faults, and
a fifth underneath them: approving a batch produced measured data in one click
and about a second.

| # | Decided | Why |
| --- | --- | --- |
| 122 | **Two shells, not one.** Home is full-bleed, centred, ~1200px, with no rail and no artifact panel. A project gets the three regions, scoped to that one project. A hash router over seven routes, no library | A home screen drawn inside a project's chrome is a home screen that belongs to that project, and the artifact panel was rendering a round nobody had opened. A hash router because the site is a static bundle served from a path not known at build time; the history API would need a server, and a server is the one thing this build may not acquire |
| 123 | **The product and the project are different objects.** The rail header is the project — back arrow, name, chevron, collapse — with New / Search / Customize / Files / Compute beneath it. The product name appears on home and nowhere else | The rail read `Adaptive workbench / demo-trastuzumab`, which made the product name and the project name one thing. The host's own rail is project-scoped; ours claimed to be a layer inside it and then contradicted the claim in its first element |
| 124 | **Naming.** The app is **Shannon Science** (`Beta` beneath). The template displays as **Adaptive antibody optimization**. The project displays as **Trastuzumab → HER2** with its id in mono beneath. The centre column's speakers are **You / Shannon / Claude** | Only the template's *display* title changes. `antibody-affinity-maturation` is the id written into `project.json`, named by decision records and read by `check.py`; `title` is carried nowhere, so renaming the display costs nothing and renaming the id would cost everything. Two projects from one template share a display title, so the session rows carry the id, which is what is actually unique |
| 125 | **The wireframe banner is removed. This supersedes decision 60.** The prototype framing lives in the README and `SPEC.md`'s staged table | Decision 60 put the label on the page because failure mode 1 says label what is stubbed. It is still labelled — in the two places a sceptic actually looks, and on individual mock fields where they sit. A bar across every screen taxed every beat to make a claim once. `CLAUDE.md`'s failure mode 1 was narrowed to match. **Failure mode 3 is untouched**: the word *synthetic* still appears beside every affinity number, in every surface, because that is a four-word label and not a banner |
| 126 | **A session is a unit of work inside a project, not a round. This amends decision 59.** A new round starts one; a person can start an ad-hoc one at any time; both kinds share the rail list and home's Recent sessions | This is where the thesis stops being asserted. Open a project you have never opened, click New, ask *where are we?* — back comes six rounds, the best observed value, which rounds flagged and which were ruled, how far the frame has moved and under whose authority, which recipe is winning. Every figure is read from an artifact on disk and resolves in the Notebook tab to the `core/` function that produced it. The same question in a chat product gets a summary of the transcript, because there is no state to read |
| 127 | **Decisions are buttons; questions are asks.** Approval and the four ruling verbs stay typed controls outside the composer. Everything that only *reads* state — status, why a round flagged, whether the lab has reported — goes in the composer as a contextual suggested ask | Decision 65's whole point is that the approval primitive is not a chat interrupt, and that does not change. What changes is that the composer stops being decorative: the asks work today, deterministically. A row of suggestions under the composer is the host's own pattern, which is why they are there and not on a button elsewhere on the page |
| 128 | **Until phase 7 an ask is answered by a briefing assembled in `wb_driver` from project artifacts.** No model, every number traced. Free text starts working in phase 7, in the same seat | Decision 62's one-surface, two-sources pattern applied to status rather than diagnosis. `wb_driver` returns typed figures, each carrying its `core/` function and the artifact it was read out of; the page lays them out. There is no sentence in the driver a number could hide inside — non-negotiable 7 applied to the surface most tempted to narrate |
| 129 | **A project opens where you left off.** A flagged unruled round opens at its ruling; a pending batch at its approval; a round at the lab at its results check; otherwise the most recent session; a blank project on a new empty one. The round graph keeps its own route and is one click away in the rail | A project is not a lobby. The route form was already settled in the plan's route table, and a route is more visible than a tab — it can be linked, and the rail item that holds it is the one new item in a rail of host items, which is the argument |
| 130 | **The lab round trip: one approval becomes two moments with a laboratory between them.** Approve signs the batch, submits it, and calls the new `export_submission` for the order file the lab receives. The round's status becomes *at the lab*. The new `check_run_status` is the only thing that releases it, and `pull_assay_results` **refuses** while a run is still going | Approving designs and reading their data in the same second was the least believable thing in the build, and to an audience who have run assays it undercut everything around it. The refusal is a feature: `registry_server.py`'s docstring already says every refusal in that file is deliberate and says what it refused and why, and "R4 is still running: 0 of 96 rows released across R4P1, R4P2 … expected 2026-09-28" belongs in that list. The browser runs the refused pull and shows it rather than describing it |
| 131 | **`submit_batch` gains `stagger`, off by default, and the record it writes with it off is byte-for-byte what it has always written.** On, the record carries `status: "running"`, an explicit commented `release_on_check: 1`, and a check counter. A record with no `release_on_check` key is complete | This is what makes the round trip cost no invariant. Every existing store, every existing round and `check.py`'s six-round CLI campaign are untouched by the argument existing, and the cross-surface byte-identity claim — which is load-bearing — survives intact. The release schedule is a demo device and reads as one in the source, which is the right place for it to be obvious. If it feels bad in rehearsal, `stagger` is one flag away from off |
| 132 | **Projects are created in the browser, from a locked configuration screen, through `init_project.py`.** Every locked row is read out of `template.json`, so the screen renders the declaration rather than disabling a form. Create runs three real commands in Pyodide: `init_project.py`, then round 1 through `generate_candidates.py` and `select_batch.py` | `init_project.py` was already the CLI's path — `main(argv)` from decision 71, paths resolved relative to its own file — so one line in `bundle.py`'s `CODE` list made the browser instantiate through the same code. `--created` pins the timestamp, which is the only thing in the four files that is not a pure function of the template and the three facts a person supplies. **`check.py` now compares a project the browser instantiated against one the CLI instantiates and requires five of six files byte-identical**, `rounds.json` being the known exception that carries the times the graph was rewritten. That is decision 108 — *survives, but under-tested* — in the form a machine can check |
| 133 | **Blank projects are the control arm, and they never touch Python.** They live in `localStorage` and open on an empty chat with a working model picker | `project.load()` requires `project.json`, `objectives.json`, `designs.json` and `rounds.json`; a project with no template has none of them, which is the point rather than a limitation. A blank project beside a templated one, both created live in the same interface, converts decision 108 from an assertion into a demonstration: one opens on a blinking cursor, the other on 48 wells enumerated, filtered under constraints enforced in code, scored by a model that beat another model, waiting for a named person to sign. Templated projects are capped at three, in the driver, because `localStorage` is about 5MB and a refusal a visitor can read beats a save that silently fails |

**Two smaller things, recorded because they will otherwise be re-litigated.**

*Turnaround is display-level.* No simulated dates are written into project
artifacts. `bundle.py` re-dates the **shipped** round graph's `updated` stamps
to span about six weeks — the field `check.py` already excludes from
byte-identity as "the times the graph was rewritten" — and moves the registry
store's `submitted` stamps with them. The rail used to date rounds 1 through 4
*today*, because that is when the demo project was generated, which visibly
contradicted the six-week campaign the pitch rests on. `lims.TURNAROUND_DAYS`
is set to agree with that spacing, so a round submitted here and expected
there tell one story.

*The read seed differs per created project*, derived from the name, so a
second campaign is not a replay of the first. That is read noise — which
constructs fail, where the run offset lands, which values censor — and not a
landscape parameter. `demo-trastuzumab` is pinned to seed 0 and is untouched,
so the shipped campaign is the committed one. Non-negotiable 8 is about
landscape parameters and this is not one.

**What the redesign did not do.** It did not put a model anywhere. The
composer's free text is still phase 7, and it says so rather than pretending.
The four verbs, the hashed evidence, the `if_wrong` line and the refusal to
act on an unruled record are exactly where phase 6 left them. Round 5 still
flags at −0.818 pKD on the product path — decision 121 — and still nobody has
diagnosed it, which remains phase 7's best test.

---

## Show, don't tell — decision 134

After the redesign shipped, the pages still explained themselves. Under the projects
list: *one of these is a campaign and the rest are analyses; the difference is a
template…* Under the sessions list: *a session is a unit of work inside a project…* In
every empty session, a first turn from Claude saying the session was empty and why that
was the point. Under the composer, a paragraph about decision 65. Under every tool call, a
caption about what the command proved. Four rail items that opened essays about what the
host does there, and a badge on the fifth saying *new*. A note on the Progress chart that
gave away the diagnosis before anyone had run it.

| # | Decided | Why |
| --- | --- | --- |
| 134 | **The interface shows and does not tell.** Text on a page reports state — what ran, what came back, where it was read from — or labels a stub or a synthetic number. It does not explain why the interface is shaped the way it is. That reasoning lives in the source comments, the README and this file. An empty session is a title and a composer pinned to the bottom of the column, as in Claude Science; the four host rail items are drawn and inert; the composer has no footnote; tool calls show the command and its output and nothing under them; the requirements table on the New project screen lists what a template needs and where it is declared, and no longer carries a column about the host | Design rationale on a working page reads as an apology for the page. The argument the prototype makes is made by the contrast between a blank project and a templated one, by the asks under the composer answering from disk, and by the verbs sitting outside the text box — every one of which is weaker with a caption beside it saying so. Failure modes 1 and 3 are untouched: stubs keep a terse label where they sit (*Not wired in this prototype*, *No model is connected in this prototype*, *Not declared anywhere in this build*), and *synthetic* still appears beside every affinity number in every surface. What changed is that the label is the whole sentence |

Two things this pass did not do. It did not touch `wb_driver.py`: the tool-log entries
still carry a `note` field, and the page simply stops rendering it, so no bundle or
byte-identity claim moved. And it did not remove the requirements table — decision 109's
artifact — only its third column, which was an audit finding wearing a product screen.

---

## The benchmark belongs to the template — decision 135

The Progress tab overlaid this project's cumulative best on the evaluator's benchmark:
three arms, twenty seeds each, six rounds. With the project at round 3 and the arms
climbing to round 6, the first question anyone asked of it was *why is there data for
rounds 4, 5 and 6?* The legend said why. The chart still read as a forecast.

| # | Decided | Why |
| --- | --- | --- |
| 135 | **The project's Progress tab draws only the project's own artifacts**: its cumulative best from its snapshots through `core.reconcile.pool`, a target line only if the template declares one, and the calibration of its last scored round. **The evaluator's benchmark is drawn as the template's validation** — on the Objectives tab, which is the template's page inside a project, and on the New project configure card — with the threshold, mean rounds-to-threshold per arm, the paired sign test and the rounds where the bands separate beside it, under the synthetic label | The benchmark answers a question that can only be asked when the ground truth is owned: does this machinery converge faster than random? No real campaign can be scored that way, so on a project's own axes the benchmark is either a forecast or a decoration, and a product that appears to forecast a campaign from a simulation is failure mode 3 in a new form. It is a fair thing for a *template* to carry — this is what the declaration was shown to do, on a landscape built for the purpose — and putting it there keeps it one click from the approval beat without letting it be read as the project's future. `simulate_campaign.py` was already "the evaluator, not the product"; its chart now sits on the same side of that line |

The threshold's provenance string — *99th percentile of the landscape, pre-registered in
DECISIONS.md* — went with it. It is evaluator language and had no business under a
project's own line.

---

## The synthetic label is a word, not a paragraph — decision 136

| # | Decided | Why |
| --- | --- | --- |
| 136 | **The three-sentence *Synthetic…* block is removed from the Decision, Progress and Validation surfaces**, and the Batch tab's line about what is computed, predicted and simulated goes with it. What stays is the one-word tag: *synthetic* beside a quoted affinity figure in a briefing and on the home card, with the explanation as its tooltip. The full claim — what is generated, what is mocked, what the chart does and does not show — is made in the README and `SPEC.md`'s staged table, once. **This narrows failure mode 3 as decision 125 narrowed failure mode 1**: the label stays where a number is quoted in prose; the banner-shaped version of it goes | The block was read three times per session and said the same thing each time; on a demo it is the audience's attention spent on a disclaimer instead of the round. Show, don't tell (decision 134) applies to honesty as much as to design: the way to be honest about a synthetic landscape is to label the number and document the landscape, not to apologise on every tab. `CLAUDE.md`'s failure-mode-3 sentence and the README's staged table are the places that carry the claim now, and they should say so in those words |

Two things looked at and left alone. The Objectives tab still renders the template's
own `anomaly_flag.note`, because it is the declaration's justification of the trigger
and is data hashed into `objectives.json`, not the interface explaining itself. And a
*random selection to date* line was considered for the Progress chart and rejected: it is
a counterfactual about designs nobody assayed, obtainable only from the oracle — which no
product path may read — or by clipping the benchmark's random arm, which is correct for
the demo project alone and impossible for a real one. The honest to-date reference a real
product can draw is the lead's own starting affinity, and that is a small driver change
if it is wanted.

---

## Phase 7: the agent in the session — decisions 137 to 152

A model sits in the centre column. It chooses which test to run next, from
the template's list, reads what came back, writes ten lines of numpy when
the library has no cut for the question, and hands back a proposal that
`record_decision.py` recomputes before it writes. A named person rules with
the same four verbs as before, and `more_evidence_requested` sends the work
back to whichever source made the pass. Without a key the same column steps
the committed record through the same component, every test re-run and
hash-compared, and the badge on the byline says which happened. `check.py`
went from 160 invariants to 179; nothing in `core/` moved and no published
number changed.

| # | Decided | Why |
| --- | --- | --- |
| 137 | **The model's system prompt is the skill.** `SKILL.md` verbatim, behind a preamble that maps its three scripts onto three tools, generated by `web/bundle.py` into `web/netlify/functions/lib/skill.mjs` with the file's sha256 beside it; `check.py` requires the string to be the file | The hour-5 gate tests whether the skill is *sufficient*, and the browser's seat is the same claim on a third harness. A second prompt would be a second skill. When the skill changes, the browser changes with Claude Code and Claude Science, and the check says whether it did |
| 138 | **The function accepts only transcripts it signed.** Every response ends with an HMAC over the full message list; a request carrying a transcript that does not verify is refused with a 403 before a token is spent. A tool result must answer exactly the calls the last assistant turn made; a question is a length-capped string; the context is typed, shape-checked and size-capped; the model is one of three ids | SPEC.md's most important line — never accept a client-supplied `messages` array — is enforced rather than promised. The loop has to live in the browser, where the data and the sandbox are, so assistant turns necessarily travel through the client; signing them is what stops one being forged. What is left for an abuser is a low-effort model on an antibody-diagnosis prompt under a daily cap, which is not a free endpoint |
| 139 | **The context is client-supplied, and this amends SPEC.md.** `wb_driver.agent_context` reads the objectives, the round graph, the focus round's 48 wells scored against what came back, every decision record with every pass, and the paths an ad hoc cut may read — about 50 KB — and the page sends it with every turn as the last, cached system block | SPEC.md said the function loads project state server-side. It cannot: since decision 119 the state is the visitor's, in their tab, and a created project or a signed batch never reaches a server. The driver computes nothing in assembling it — every figure is one an artifact already holds — so the constraint that mattered is kept where it was |
| 140 | **Three tools: two that read, one that hands back.** `run_diagnostic` is `run_diagnostic.py` with the permitted tests as a strict enum; `execute_analysis` is the sixth question; `propose_decision` is `record_decision.py --propose`, and the writer's refusal goes back to the model as an error result for it to answer | SPEC.md counted two tools, both read-only, and left the proposal as the model's output. Making the hand-back a tool gives it a schema the model cannot drift from and a refusal channel: a payload that names a result, or a correction with no concordant bridge, comes back as the writer's own words, and the model has to fix it rather than the page silently dropping it. Nothing the model can call writes state; the record is written by the same script the CLI runs |
| 141 | **One loop, driven from two harnesses.** `web/src/agent.js` takes `call` as an argument and never imports the runtime; the page passes `rt.call`, and `web/scripts/pyodide-check.mjs` passes its own and drives the same file in node | The page's loop and the harness's loop would otherwise be two implementations of the one piece of phase 7 that is new, and the harness would be checking a copy. Non-negotiable 2 applied to the orchestration rather than the science |
| 142 | **Replay is the record's claims stepped through the same emitter with every number recomputed.** For each hypothesis: the claim, `run_diagnostic.py` run here and its result hash-compared to the committed record, the reading. For each ad hoc cut: the code run again through `execute_analysis` and its stdout compared. Then the proposal through `record_decision.py`. `web/bundle.py` now strips ad hoc stdout from the shipped proposal along with every result | Decision 62 asked for one component and a badge as the only visible difference. Verification that the page could not have faked needs the reference numbers kept away from the page, so the comparison happens in the driver, on the Python side of the JSON boundary — `0.0` and `0` hash differently once they have been through JavaScript, which is how that was noticed. The badge's *8 of 8 results match · 3 of 3 cuts reproduce* is a count the driver made |
| 143 | **A scripted upstream, for the harness and labelled as such.** `WORKBENCH_UPSTREAM=scripted` makes the function take its model turns from the shipped proposal, as SDK-shaped events; it is on only under an environment variable Netlify never sets, the probe and every closing event report `upstream`, and the badge would read *scripted · harness* | `check.py` has to prove the live loop round-trips — the transcript is signed and verified, tool results answer the calls the model made, the proposal reaches the writer, the push-back continues the transcript — on a machine with no key and without spending anything. Every number it leads to is still computed in Pyodide, because the script names tests and carries none. Failure mode 1 says label a stub; this one is labelled in three places |
| 144 | **Budget: a daily USD cap and a per-address counter**, in Netlify Blobs on the site and in process memory elsewhere, with the store named in the probe. Over either cap the function answers 429 and the page stays in replay with the reason on the badge | SPEC.md's design, with the honest local behaviour spelled out. The cap is approximate — two requests can race past it by one call — and it does not need to be exact: it exists so a public URL cannot run up a bill, not to meter anyone. Cost is priced from the response's own usage at the served model's rates |
| 145 | **Refusal is handled the way the cap is.** `fallbacks: "default"` under `server-side-fallback-2026-07-01` on every request; a `refusal` stop on the final response ends the turn with *declined (category)* on the badge, and a served-by-fallback model is named in the tooltip | The hour-5 gate tripped the `bio` classifier three times. The fallback would have absorbed all three; if the whole chain declines, the page says so instead of rendering an empty bubble, and the same component steps the record. One more door into the room replay already is |
| 146 | **`max_tokens` is 16 000 on a diagnosis turn, effort `low`, adaptive thinking on.** SPEC.md said about 400 | The proposal turn carries the record — eight hypotheses with their reasoning, three cuts with code and stdout, a rationale, the alternatives and an `if_wrong` a sceptic reads first — and on this model thinking counts against the cap. Low effort is still the cost lever: the session reads small JSON, picks tests and explains. An ask gets 4 096 and a chat 2 048 |
| 147 | **Claude speaks only when a model or the record's author wrote the words, and every Claude turn carries a mode badge.** The reconciliation sentence, the two-readings introduction, the record's summary and the quiet-round line are the workbench's, and speak as Shannon | Phase 6 had deterministic prose speaking as Claude, which was tolerable while no Claude existed and a small dishonesty once one did. Decision 66's *one line on quiet rounds* is kept as Shannon's line from numbers, and the model's version becomes an ask offered under the composer when a live seat is available — a question, not an alarm |
| 148 | **The committed round-4 record is two-pass, and the final ruling is left to a person.** d.webster ruled `more_evidence_requested` naming `residual_by_plate`, from the record's own `if_wrong` and the gate's own closing caveat: all four cross-version anchors sit on R4P1. `gates/run_gate.sh round4-pushback` — a headless Claude Code session with the ruled record present and the four documents absent — answered it, and its transcript is committed | SPEC.md said both passes and the final ruling would be committed. Both passes are; the verdict is the visitor's to give, on stage or at 2am, and `check.py`'s *deliberately unruled* invariant stays true. Decision 99's rule held: nobody edited the gate's record; a ruling opened pass 2 and an agent wrote it |
| 149 | **Transcripts are not state.** A signed transcript lives in page memory for the session; the stored agent turn carries the steps and the log numbers, not the messages. A push-back after a reload starts a fresh transcript from the record, which carries everything pass 1 found | The decision record is the durable state and the conversation that produced it is not, which is the thesis. A transcript put through the project's canonical JSON would also stop verifying — sorted keys and fixed-precision floats change the bytes the signature covers — so storing it would have meant storing it somewhere else anyway |
| 150 | **`execute_analysis` is a guard, not a sandbox, and says so.** A read-only `open` that refuses `data/`, `lims_store/` and `session/`; an import denylist; a token check for the laboratory and the registry; a line budget that stops a runaway loop from freezing the tab; the code written to a file the log names | The oracle ships in the bundle because the simulated laboratory runs client-side, and anyone can read it by URL — decision 116 already said to say that first. The claim is that `core/` never reads it and that ad hoc output is evidence a person reads and never an input to a code path, which `record_decision.py` enforces on its own. Same posture as decision 97 for the gate's `data/` rule |
| 151 | **The model picker is wired.** Three ids, the function refuses any other, Opus 5 by default | It was drawn; wiring it cost an allowlist. A picker that does something is one fewer row in the staged table |
| 152 | **Blank projects chat live, with nothing declared.** A one-paragraph system prompt, no tools, no context; the answer says what has not been declared when asked | Decision 133 made blank projects the control arm for decision 108. With a model seated they become what they are — a chat — beside a templated project where the same model has a skill, a state and three typed tools. The contrast is the argument, and it now runs |

**What building it found, recorded because it changed something.**

*The gate's own caveat became the push-back.* The hour-5 transcript closed with: *all four cross-version anchors — the three bridge members and the incumbent — sit on plate R4P1 … the clean route is a ruling of `more_evidence_requested`*. The ruling in decision 148 is that sentence, put back to the agent by name, and it is the reason the two-pass record reads as a scientist's exchange rather than a staged one.

*The first push-back run wrote a cut nobody else could run, and the skill now says why not.* Its second ad hoc analysis read the round's results export from `/tmp/r4_readonly.csv` — the path it had handed `pull_assay_results` itself — so the browser, replaying the record from its own pull, could not reproduce it. The run was otherwise good and found the same thing the committed one did; it is not committed, because the record is worth what can be reproduced from it. `SKILL.md` gained a paragraph: a cut reads the project directory and the round's export where the registry writes it, by relative path, and nothing else. The driver's guard was widened to match — `lims_store/exports/` is readable, the registry's own records beside it are not — and the gate was run again, at $2.64 and 33 turns, reading only project files. The transcripts differ in one more way worth recording: the first listed the real repository, because the plugin installed in phase 5 resolves its skill against this checkout, and saw that the four documents exist there without reading them. The gate tree now denies reads of the repository and greps for its path.

*Pass 2 found something structural.* Answering the ruling, the agent noticed that `core/acquisition.py`'s `assign_plates` lays a batch out in slot order at 24 wells a plate, and the controls and replicates are the first slots — so every round of this template puts its whole bridging set on plate 1, and every future offset estimate carries exactly the blind spot the ruling named. It also noted that the snapshot records the plate a measurement came from and not the well, so a within-plate position effect is not testable from the project directory. Both are recorded here and neither is acted on in this phase: the first is a template change and the second changes a snapshot's hashed body, and both belong to the objectives-amendment work SPEC.md lists under *after the demo works*.

*The context is larger than SPEC.md guessed.* With a two-pass record in it the blob `agent_context` assembles is about 92 KB, roughly 23 000 tokens, against the 20 000 the spec estimated; with the skill it is a 27 000-token cached prefix. Fine at Opus 5's cache rates and not worth trimming a decision record to fit a round number.

*A round nobody has diagnosed is one click past the demo.* Round 5 flags at −0.818 pKD on the product path (decision 121), no record exists for it, and the live seat is the only thing that can read it. Without a key the page offers the five tests by hand and says nothing more. That is the unscripted beat, and it is not in the harness on purpose.

*What phase 8 has to verify on the deployed site, and cannot be verified here.* Netlify's streaming-function limits under a proposal turn that can run a minute; that `included_files` is unnecessary because the skill is a module; that the Blobs store is reachable from the function; and that `ANTHROPIC_API_KEY` is set. The probe reports all four.

---

## The stream is a chat — decision 153

Phase 7 put a name over every turn: *Shannon* on the workbench's prose, *Claude* on a
model's, *You* on the person's, each with an initial in a box. Decision 147 drew the
line between the first two and it was the right line; naming it on every turn was not.
A visitor reading *Shannon* over one paragraph and *Claude* over the next was asked to
learn a distinction the badge already made, and the host draws none of it: its column is
the assistant's, unnamed, and the person's words sit in a bubble on the right.

| # | Decided | Why |
| --- | --- | --- |
| 153 | **The centre column is a chat with two sides and one label.** Your asks and your rulings are bubbles on the right. Everything else is the column's own prose with nothing over it — what ran, what came back, what the record says — and a model's turn carries the mode badge above it: `live · Opus 5`, `replayed · 8 of 8 results match · 3 of 3 cuts reproduce`, or `stopped` with the reason. No turn names a speaker; the `SPEAKERS` table and the initial-in-a-box are gone. The past ruling reads as your bubble with the writer's `record_decision.py --rule` chip beneath it; the ruling verbs, the approve button and *Act on the ruling* are controls in the column, unattributed, exactly as decision 65 placed them. Supersedes the speaker list in 124 and amends 147: the rule that Claude speaks only when a model or the record's author wrote the words stands, and the badge is now the whole of how it is shown | Two names over adjacent turns was the interface explaining itself — decision 134's failure in a byline. The thing that has to be visible is *which turns a model wrote and in what mode*, and the badge carried that on its own; the name beside it was redundant when it agreed with the badge and confusing when a reader tried to work out why the workbench had a first name. The layout is the host's, and a layer inside Claude Science that draws its stream differently from Claude Science is making a claim it does not mean. Failure mode 1 is untouched: every model turn still says live, replayed or stopped, and *scripted · harness* still shows wherever the test double runs |

One thing the bubbles made visible. The ask the registry refused was rendered at the
tail of the stream, after the ruling, because only the ask that succeeded was placed at
the arrival. In a chat that is a question asked after its own answer. Each laboratory
ask is now placed where it happened — the question, then the status and pull calls it
made, then the registry's answer — and the ask that succeeded reads the same way, with
its own status call grouped under the arrival rather than under *Asked the registry*.
That line survives only for registry calls no ask in the session accounts for: a round
checked from another session, or from the harness.

What did not change. `wb_driver.py`, the stored session shape and the function are as
they were; this is `Turn.jsx`, `Session.jsx`'s turn placement and the stylesheet. The
suggested asks still answer from disk with no model and no badge, which is now the only
thing that distinguishes a briefing from a model's answer on the page — and it is enough,
because a briefing has never claimed to be anything else.

---

## The seat is Sonnet 5 — decision 154

| # | Decided | Why |
| --- | --- | --- |
| 154 | **The default model is `claude-sonnet-5`.** The function's `DEFAULT_MODEL`, the picker's first entry and the harness's scripted turns all name it; `claude-opus-5` and `claude-haiku-4-5-20251001` stay on the allowlist and in the picker. The request shape is unchanged — adaptive thinking, effort `low`, `fallbacks: "default"` under the `server-side-fallback-2026-07-01` beta, the context block cached — and one 64-token request on the day of the change confirmed Sonnet 5 accepts it exactly as built. Amends 11 and 151 | Decision 11 already said Sonnet 5 would be adequate and ~2.5× cheaper, and kept Opus for the ad hoc code path; phase 7 made that path a read-only guard whose output is evidence a person reads and never an input, and `record_decision.py` recomputes every number in the proposal before it writes — so what the model gets wrong is caught rather than trusted, and the case for paying Opus rates on every visitor's session went with it. At $2/$10 per million against $5/$25 the daily cap buys two and a half times as many sessions. The committed round-4 record and the three gate transcripts were written on Opus 5 and say so; nothing in them is re-run. The picker still offers Opus 5 for anyone who wants the comparison, which is the point of a picker that works |

---

## A project created in the browser did not survive its own reload — decision 155

Creating a project from the template and reloading the page put the app in a state no
Reset button was offered for: `[Errno 44] No such file or directory:
'/workbench/projects/trastuzumab-affinity-2/evidence'` on the project, and the same line
on the home screen with *no* projects listed — the shipped campaign included, because
`projects()` lists every project's snapshots and the first one that raises takes the list
with it. The shipped project never showed it: it arrives with a file in all five
subdirectories.

| # | Decided | Why |
| --- | --- | --- |
| 155 | **The driver re-asserts the project directory skeleton at boot, and `runtime.js` calls it after restoring the overlay.** `wb_driver.ensure_dirs()` walks `projects/`, and for anything holding a `project.json` re-creates whatever of `schema.SUBDIRS` is missing. It writes no file, so no artifact and no hash moves. `pyodide-check.mjs` drops exactly what the overlay drops from the project it instantiates and check.py asserts the listing breaks before the call and works after — check 180 | The overlay is a map of path to contents, because `dump_state` returns files; a directory with nothing in it yet has nothing to carry. A project instantiated in the browser has five such directories until its first round writes into each, and round 1 fills only `candidates/` and `batches/`. The skeleton is derivable rather than state — every project directory has the same subdirectories, named once in `core/schema.py` — so boot re-asserts it instead of the overlay growing a second entry kind and a migration. The read that raised was `core.project.snapshots`, and it was left alone: `core/` is the part an audience reads, the directory genuinely should exist, and a defensive branch there would have hidden the same gap on the write paths, which `schema.write_json` would have hit next — it does not create parents |

Two notes for whoever reads this next. The failure needed a reload to appear, so it was
invisible to every check that boots once and drives forward — which is all of them until
now. And `MAX_CREATED` is 3, so a visitor could brick their own copy of the demo three
clicks in; the fix is what makes the New project screen safe to show on a public URL,
which phase 8 is about to do.
