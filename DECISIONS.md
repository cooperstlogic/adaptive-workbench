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

