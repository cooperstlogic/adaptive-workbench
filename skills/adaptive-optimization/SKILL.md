---
name: adaptive-optimization
description: Run design-test-learn rounds on an antibody or protein lead optimization project - select the next batch of variants to test, import assay results, fit and compare surrogate models, score the previous round's predictions, and diagnose a round that came back wrong. Use for affinity maturation, batch selection under developability constraints, active learning over a candidate pool, and deciding what an ambiguous round of results means.
---

# Adaptive optimization

You are operating a project that persists across experimental rounds. The
project directory is the state: read it, run the scripts, write back into it.
Nothing here talks to the network.

**Everything laboratory in this build is simulated.** The landscape is
synthetic, the LIMS is a mock, and the assay is an oracle replaying generated
values with noise. Say "synthetic" in the same breath as any number you quote.

## The project is a directory

```
projects/<name>/
  project.json          lead, target, team, connected sources, template id
  objectives.json       properties, thresholds, batch size, mutation rules,
                        editable region, permitted recipes and diagnostics
  designs.json          sequence, hash, parent, mutation list, registry ids
  evidence/snapshot_NNN.json    what the lab returned, reconciled
  models/run_NNN.json           fitted recipes, the bake-off, pool predictions
  candidates/pool_NNN.json      enumeration and what the constraints removed
  batches/batch_NNN.json        recommended, approved, overrides, rationale
  batches/batch_NNN.eval.json   last round's predictions scored against it
  decisions/decision_NNN.json   a judgment call, its evidence and its ruling
  rounds.json           the decision graph linking all of the above
```

`rounds.json` is the artifact that matters. Every other file could be
regenerated from the snapshots; the link from recommendation to tested
constructs to returned evidence to diagnosis to updated model to next batch
could not. Every record carries a content hash and the hashes of its inputs,
taken over canonical JSON at fixed precision, so any surface recomputes the
same hash and a batch can be walked back to the exact evidence behind it.

## The round loop

Run these in order. Each takes `--project <dir> --round <N>` and writes one
artifact. All paths below are relative to the repository root.

| Step | Script | Writes |
| --- | --- | --- |
| 1 | `skills/adaptive-optimization/scripts/generate_candidates.py` | `candidates/pool_NNN.json` |
| 2 | `skills/adaptive-optimization/scripts/select_batch.py` | `batches/batch_NNN.json` |
| 3 | registry: `submit_batch` then `pull_assay_results` | the round's results CSV |
| 4 | `skills/adaptive-optimization/scripts/import_round.py` | `evidence/snapshot_NNN.json` |
| 5 | `skills/adaptive-optimization/scripts/evaluate_prior.py` | `batches/batch_NNN.eval.json` |
| 6 | `skills/adaptive-optimization/scripts/fit_surrogates.py` | `models/run_NNN.json` |

Round 1 needs nothing extra. With no model run on disk, `select_batch` takes
the seed branch and returns the template's round-1 policy batch, saying so in
the rationale.

`import_round` prints whether the round is **flagged**. A flagged round stops
the loop: do not run step 6 and do not select the next batch until the round
has a ruling. Read the diagnosis procedure below.

Two more scripts serve that case:

| Script | Does | State |
| --- | --- | --- |
| `run_diagnostic.py` | Runs one named test from `core/diagnostics.py` and prints its result. Read-only, writes nothing | **Not built yet** |
| `record_decision.py` | Writes hypotheses, evidence, recommendation and ruling into `decisions/`. A dumb writer with no logic of its own | **Not built yet** |

Those two and `core/diagnostics.py` land in phase 4. Until they do, the
diagnosis procedure below describes what to do and the tests it names cannot
be run. Do not simulate them.

## Diagnosing a flagged round

The flag is a threshold: the round's fresh designs came back on average more
than the template's trigger away from where the model put them. That is
arithmetic. What it means is not, and the flag is deliberately a statistic
that several different causes trip in exactly the same way.

| Hypothesis | If true, the right action is |
| --- | --- |
| Assay-version or reagent offset | Estimate the offset from the shared controls, correct, then pool |
| Plate or well-position artifact | Correct per group, or drop the affected wells |
| The model extrapolated into a region it has not seen | Nothing to the data. Refit and widen exploration next round |
| A real structure-activity cliff the optimizer walked into | Nothing to the data. Correcting it away would erase the finding |

Rows one and four produce the same first look and opposite actions. Telling
them apart means conditioning on the designs shared with earlier rounds
rather than on the new ones, checking whether those shared designs agree with
each other at all, and refusing to correct when they do not.

Procedure:

1. Read the snapshot's `anomaly` block and its `frame.offset_estimate`. Note
   the assay version and whether the project had already characterized it.
2. Run `offset_from_controls` first. It is the only test that can separate a
   run offset from a property of the new designs, because the shared designs
   are the same molecules measured twice.
3. **If the bridge is missing or its members disagree, refuse.** The correct
   output is `no_action` with `confidence: "refuses"` and an explanation. A
   principled refusal is a better demo than a confident correction, and an
   unjustified correction on a real cliff hides the finding.
4. Choose the second test from what the first returned, not from a checklist.
   A clean offset with concordant bridge members points at the assay and
   `residual_by_plate` tells you whether it is the run or one plate. An offset
   near zero with the fresh designs still low points at the designs, and
   `residual_by_mutation_class` tells you whether one position carries it.
   Wide replicate spread points at the assay before either, so
   `replicate_concordance` comes first when the read standard deviations are
   large.
5. Write a decision record with `record_decision.py`. State every hypothesis
   you considered, including the ones the evidence did not support, and fill
   `if_wrong` with what would falsify your recommendation. That field is the
   one a sceptical scientist reads first.
6. A ruling is `accepted`, `accepted_with_modification`, `rejected` with a
   reason, or `more_evidence_requested`, which names a test and sends the work
   back to you. Every ruling carries a named approver and a timestamp, and no
   action is taken on an unruled record.
7. Once ruled, re-import the round naming the authority:
   `import_round.py ... --offset always --authority decision_NNN`. Then
   continue with steps 5 and 6 of the loop.

The five diagnostics are a fixed set and the sixth question is always the
interesting one. When you need something the library does not cover, write ten
lines of numpy, run it read-only against the snapshot, and record the code
beside the number in the decision record's `ad_hoc` list, labelled one-off and
unversioned. An ad hoc result is evidence a human reads. It is never an input
to a code path.

## Four rules you do not break

1. **Never change objectives without explicit approval.** `objectives.json`
   declares the thresholds, the mutation budget, the editable region and the
   batch policy. Amending it changes what every past round meant. Ask, and
   record the amendment as a version.
2. **Never pool measurements across assay versions without a bridging set.**
   Every batch carries the parent and replicates from the round before so a
   per-round offset is estimable. If that bridge is absent or its members
   disagree, refuse to pool and say why.
3. **Never invent a model recipe outside the registry.** `objectives.json`
   lists the permitted recipes and `core/surrogate.py` implements them. Two
   recipes compete each round and the winner is the lowest held-out negative
   log predictive density. Adding a third is a template change, not a run
   choice.
4. **Never write a number into a decision record that did not come from a
   named `core/` function.** You choose which test to run, in what order, and
   what the results mean together. You do not compute the statistics. A number
   you produced yourself goes in `ad_hoc` with its source inlined and is
   evidence, not an input.

## What you are for

Steps 1, 2, 4, 5 and 6 are a pipeline. A pipeline runs the same steps whatever
comes back, and a scheduler can drive it — `run_rounds.py` does exactly that,
and stops the moment a round is flagged. The stop is the job: work out what an
ambiguous round means, in an order that depends on what you find, and hand a
named human a recommendation they can rule on.
