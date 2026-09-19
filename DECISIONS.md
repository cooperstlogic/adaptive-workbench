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

**Fill this in and commit it before `simulate_campaign.py` runs for the first time.** Each
value needs a justification that does not reference the outcome. If the hour-3 gate fails
on these parameters, the deliverable is a sentence saying it failed — not a new table.

| Parameter | Value | Justification (independent of result) |
| --- | --- | --- |
| Positions | 8 | Matches the trastuzumab CDR-H3 editable region in the template |
| Max mutations | 2 | Template constraint; keeps the candidate pool enumerable |
| Epistasis order (K) | _TBD_ | Set so a linear model explains roughly 60% of landscape variance, which is the range published DMS landscapes show |
| Ruggedness / correlation length | _TBD_ | |
| Assay noise (lognormal σ, pKD) | _TBD_ | Set from typical ACE-assay replicate spread, not from what separates the arms |
| Per-round batch offset (σ, pKD) | _TBD_ | Large enough that round 4 is genuinely ambiguous, chosen before the arms are run |
| Cliff position | _TBD_ | Placed at a high-expected-improvement position so the optimizer walks into it naturally |
| Cliff depth (pKD) | _TBD_ | |
| Detection limit (pKD) | _TBD_ | Set so a few percent of round-1 designs censor, matching the ~3% failure rate |
| Construct failure rate | 0.03 | Typical for a small expression campaign |

**Pre-registered threshold:** the 99th percentile of the landscape, fixed before the first
run. Recorded here as an absolute pKD value once the landscape is generated, so that it
cannot drift.

| Item | Value | Recorded at |
| --- | --- | --- |
| Threshold (pKD) | _TBD_ | _commit before first gate run_ |

## Decided during the build

_Append here. Date each entry._
