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
| Round-4 assay-version shift | −0.80 pKD, deterministic | An assay version change producing a ~6-fold apparent shift is a thing that happens. At 5.3× the noise σ it is resolvable from a 3-design bridge (offset/SE ≈ 9), which is what makes the diagnosis defensible rather than a coin flip |
| Construct failure rate | 0.03 | Typical for a small expression campaign |
| Assay reads per design | 2 | Returned as separate rows, never pre-averaged |
| Detection limit | 2nd percentile of the landscape | Censors a few percent of round-1 designs; the round-4 offset then pushes more below it, which is realistic and gives `import_round` work to do |
| Threshold (the gate) | 99th percentile of the landscape | Fixed here, before the first run, per SPEC. Absolute value recorded below once generated |
| RNG seed | 20260918 | Fixed so the landscape is reproducible |

### Derived absolute values

Recorded immediately after generation, still before any campaign run.

| Item | Value | Recorded at |
| --- | --- | --- |
| Cliff position (VH index) | _generated_ | phase 1 |
| Detection limit (pKD) | _generated_ | phase 1 |
| Threshold (pKD) | _generated_ | phase 1 |
| Landscape max (pKD) | _generated_ | phase 1 |
| Realized linear R² | _generated_ | phase 1 |

## Decided during the build

_Append here. Date each entry._
