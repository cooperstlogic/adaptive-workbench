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
| 3 | registry: `submit_batch` | the round's identifiers and plate layout |
| 4 | registry: `export_submission` | the order file the lab receives |
| 5 | registry: `check_run_status` | whether the assay has reported yet |
| 6 | registry: `pull_assay_results` | the round's results CSV |
| 7 | `skills/adaptive-optimization/scripts/import_round.py` | `evidence/snapshot_NNN.json` |
| 8 | `skills/adaptive-optimization/scripts/evaluate_prior.py` | `batches/batch_NNN.eval.json` |
| 9 | `skills/adaptive-optimization/scripts/fit_surrogates.py` | `models/run_NNN.json` |

**Steps 3 to 6 are a laboratory, not a function call.** A submitted round does
not report the moment it is submitted. `export_submission` writes what goes
out — construct, sample, design, plate and sequence, with no value column,
because an order is not a result. `check_run_status` answers whether the assay
has finished, and while it has not, `pull_assay_results` **refuses** and says
so. That refusal is the boundary working: the workbench cannot read a result
the laboratory has not produced.

A scripted campaign never waits, because `submit_batch` holds a round open
only when asked to (`--stagger`, off by default), and nothing in this list
passes it. The interactive surfaces do, so that approving a batch and reading
its data are two moments rather than one second.

Round 1 needs nothing extra. With no model run on disk, `select_batch` takes
the seed branch and returns the template's round-1 policy batch, saying so in
the rationale.

**A batch nobody has approved yet can simply be re-composed.** If the person
reviewing it wants the wells spent differently — more exploration, a wider
bridge — run step 2 again with `--set`:

```
select_batch.py --project ... --round N \
    --set batch.exploration_slots=4 --set-note "two slots is not enough coverage"
```

`batch.controls`, `batch.replicates`, `batch.exploration_slots` and
`batch.diversity_weight` can be set this way, bounded by the same
`core/amend.py` list an amendment is held to. **It needs no ruling behind it**,
because it touches nothing but this batch: `objectives.json` is not written,
the next round reverts to the declaration, and the approval that gates every
batch has not happened yet. The record keeps what moved, who asked and why, in
`policy_overrides`. A round that has already been submitted refuses the flag —
its batch record is the order the laboratory received.

Do not reach for a decision record to do this. That is the other instrument,
below, and it is for changing the declaration rather than one batch.

`import_round` prints whether the round is **flagged**. A flagged round stops
the loop: do not run step 9 and do not select the next batch until the round
has a ruling. Read the diagnosis procedure below.

Three more scripts serve that case:

| Script | Does |
| --- | --- |
| `run_diagnostic.py` | Runs one named test from `core/diagnostics.py` and prints its result as JSON. Read-only, writes nothing |
| `record_decision.py` | Writes hypotheses, evidence, recommendation and ruling into `decisions/`. Adds no arithmetic of its own, and accepts none |
| `amend_objectives.py` | Moves one declared field of `objectives.json`, under a ruling that authorized it. Takes no field and no value of its own: both come out of the record |

## Diagnosing a flagged round

The flag is a threshold: the round's fresh designs came back on average more
than the template's trigger away from where the model put them. That is
arithmetic. What it means is not, and the flag is deliberately a statistic
that several different causes trip in exactly the same way.

| Hypothesis | If true, the right action is |
| --- | --- |
| Assay-version or reagent offset | Estimate the offset from the shared controls, correct, then pool |
| Plate or well-position artifact | Correct per group, or drop the affected wells |
| The model extrapolated into a region it has not seen | Nothing to the data. Refit, and propose an amendment widening exploration next round |
| A real structure-activity cliff the optimizer walked into | Nothing to the data. Correcting it away would erase the finding |

Rows one and four produce the same first look and opposite actions. Telling
them apart means conditioning on the designs shared with earlier rounds
rather than on the new ones, checking whether those shared designs agree with
each other at all, and refusing to correct when they do not.

### The five tests

Each returns numbers and never a verdict. `supported` and `not supported` are
your words, written into the record; the tests do not contain them.

| Test | Returns | Arguments |
| --- | --- | --- |
| `offset_from_controls` | The bridge offset `import_round` recorded, its standard error and bridge size, plus whether the shared designs agree with each other | — |
| `residual_by_plate` | Mean residual by plate, the largest gap between plates and its standard error | — |
| `residual_by_mutation_class` | Mean residual by class, each class against the rest, with `n` and `n_fresh` for both sides | `--by position` (default) or `--by n_mutations` |
| `replicate_concordance` | The round's own read-noise scale, and any design whose two reads disagree by more than the template's tolerance | — |
| `calibration_by_region` | Coverage of the 80% interval overall and by predicted-value bin | `--offset bridge` scores the counterfactual |

`--scope fresh` restricts any of them to the round's fresh designs, which is
the population the flag was computed over. The default is every design the
round both predicted and measured, so the designs carried over from earlier
rounds are visible beside the new ones.

`--offset bridge` is the test that separates the first hypothesis from the
rest, and it is worth understanding rather than copying: it asks what coverage
*would* be if this round were nothing but the assay shift the bridge measured.
If the shift is the whole story, correcting by it restores coverage. Whatever
is still missing afterwards is not the assay. The shift is always the recorded
bridge estimate and never a number you supply, which is the same rule as rule
4 below wearing different clothes.

### Procedure

1. Read the snapshot's `anomaly` block and its `frame.offset_estimate`. Note
   the assay version and whether the project had already characterized it, and
   note the **sign**: a round can flag for coming back better than forecast,
   and that is a different diagnosis with a different action.
2. Run `offset_from_controls` first. It is the only test that can separate a
   run offset from a property of the new designs, because the shared designs
   are the same molecules measured twice.
3. **If the bridge is missing or its members disagree, refuse.** The correct
   output is `no_action` with `confidence: "refuses"` and an explanation. A
   principled refusal is a better demo than a confident correction, and an
   unjustified correction on a real cliff hides the finding. `record_decision`
   enforces this: it will not write a correction with no concordant bridge
   behind it.
4. Choose the second test from what the first returned, not from a checklist.
   A clean offset with concordant bridge members points at the assay and
   `residual_by_plate` tells you whether it is the run or one plate. An offset
   near zero with the fresh designs still off points at the designs, and
   `residual_by_mutation_class` tells you whether one position carries it.
   Wide replicate spread points at the assay before either, so
   `replicate_concordance` comes first when the read standard deviations are
   large.
5. **Check the size of a class before believing it.** A cause that could
   explain a whole round has to appear in a class large enough to move it. A
   class of two designs with a residual twice everyone else's is noise, and
   every test reports `n` next to its mean so you can see that. Note also that
   designs carried over from earlier rounds are the designs the model was
   trained on, so a contrast between them and the fresh ones is confounded
   between "the model has seen these" and whatever else distinguishes them.
   Say so in the record rather than picking one.
6. **An offset that explains part of a round is a finding, not a failure.**
   Compare the bridge estimate against the discrepancy the fresh designs show.
   If the bridge recovers a fraction of it, the honest recommendation corrects
   what the bridge supports and states what remains unexplained. Run
   `calibration_by_region --offset bridge` and put the leftover number in the
   record.
7. Write the record with `record_decision.py --propose payload.json`. The
   payload names hypotheses, the test each rests on, and your reading; the
   script runs those tests itself and writes the numbers it got. **It refuses
   a payload that carries its own `result`** -- there is no channel for a
   number you produced. State every hypothesis you considered, including the
   ones the evidence did not support, and fill `if_wrong` with what would
   falsify your recommendation. That field is the one a sceptical scientist
   reads first, and the script will not write a record without it.
   The recommendation's `action` is about this round's data. If what the round
   shows is that the *policy* is wrong — the model was asked to choose from a
   pool it has already ranked to exhaustion, or two exploration slots cannot
   cover what it is this uncertain about — then say so with an `amendment`
   beside the action. It names one field of `objectives.json` and the value
   you want it to take:

   ```json
   "amendment": {"field": "batch.exploration_slots", "to": 6,
                 "why": "what this round shows the present value costing"}
   ```

   **An amendment is the heavier of the two instruments, and it is for the
   declaration rather than for a batch.** If what someone wants is the batch in
   front of them composed differently, that is `select_batch.py --set` above
   and it needs none of this. Propose an amendment when the round's evidence
   says the policy itself is wrong from here on.

   `core/amend.py` declares which fields are amendable and the bounds on each,
   and `record_decision.py` enforces them before it writes anything — a field
   that is not on the list is refused by name, and so is a value outside its
   bounds or one that would leave the batch fewer than the declared floor of
   fresh designs. What the field is *now*, and what the change would cost the
   candidate pool, are read off the project: you name the field and the value
   and nothing else, which is rule 4 again in different clothes. The value is
   yours to choose because it is a decision rather than a measurement, the
   same way `drop_wells` names a plate.

   The thresholds, the mutation budget, the permitted recipes, the permitted
   diagnostics and the anomaly trigger are **not** amendable, and asking is
   refused. Those are the pre-registration.

8. A ruling is `accepted`, `accepted_with_modification`, `rejected` with a
   reason, or `more_evidence_requested`, which names a test and sends the work
   back to you. Every ruling carries a named approver and a timestamp, and no
   action is taken on an unruled record. If you are handed back a test, run it
   and propose again: the next pass must include what was asked for, and the
   record keeps both passes. A ruling on a recommendation that proposes an
   amendment may also move its number — `accepted_with_modification` with
   `--amend-to` — and then the record holds what you asked for and what was
   decided, and the decided one is what runs.
9. Then act on the ruling, which is the only thing that changes any data:

   - `refit_only` or `no_action` -- change nothing. The round is ruled and the
     loop is unblocked; go straight to step 9 of the round loop.
   - `apply_offset_correction` -- re-import the round naming the ruling:
     `import_round.py ... --offset always --authority decision_NNN`. It checks
     the record: the authority has to exist, be ruled, and recommend the
     action being taken.
   - `drop_wells` -- re-import with `--drop-plate <plate> --authority
     decision_NNN`, which discards those wells before reconciling.

   An amendment runs **beside** whichever of those the action asked for,
   because it changes the next round rather than this one:

   ```
   amend_objectives.py --project ... --authority decision_NNN
   ```

   It reads the field and the value back out of the record, checks that the
   ruling authorized them, and writes `objectives.json` with its `version`
   bumped and the superseded value kept in an `amendments` entry naming the
   ruling. **A parameter that moved is only checkable if what it moved from is
   still written down.**

   Then the order of what follows depends on what moved, and the script prints
   which case it is. A batch-policy amendment leaves the candidate pool alone,
   so carry on with `fit_surrogates.py` as usual. An amendment to the editable
   region moves the pool, and a model run holds one prediction per pool member
   in pool order, so the round has to be fitted against the pool the *next*
   batch will be chosen from:

   ```
   generate_candidates.py --round N+1
   fit_surrogates.py --round N --pool N+1
   select_batch.py --round N+1
   ```

   Fitting round N against its own pool after the window moved is refused,
   which is the guard working rather than an obstacle: the predictions would
   be indexed against the wrong sequences.

   **If you re-imported, re-run `evaluate_prior.py` for that round before
   fitting.** The evaluation records the hash of the snapshot it scored
   against, so a moved frame leaves it pointing at a snapshot that no longer
   exists, and its residuals describe a frame the project has abandoned. The
   two run as a pair on the way in and they run as a pair on the way back.

   Then run `fit_surrogates.py` for the round and continue.

A ruling that changes no data leaves the snapshot's `frame.authority` reading
`unruled`, and that is correct: the field describes the frame, and nothing
moved it. Whether a round has been ruled is a property of its decision
record.

The five diagnostics are a fixed set and the sixth question is always the
interesting one. When you need something the library does not cover, write ten
lines of numpy, run it read-only against the snapshot, and record the code
beside the number in the decision record's `ad_hoc` list, labelled one-off and
unversioned. An ad hoc result is evidence a human reads. It is never an input
to a code path.

**A cut is recorded so it can be run again**, by a reviewer on another machine
or by another surface replaying the record. So it reads only the project
directory and the round's own results export, by path relative to the
repository root: `projects/<name>/...`, and
`lims_store/exports/<name>_round<N>.csv`, which is where the registry writes a
pull when you leave `out` to it. A cut that reads a temporary file or an
absolute path is a number nobody can reproduce, and the record is worth
exactly what can be reproduced from it.

## Four rules you do not break

1. **Never change objectives without explicit approval.** `objectives.json`
   declares the thresholds, the mutation budget, the editable region and the
   batch policy. Amending it changes what every past round meant, so you do
   not write it — you propose one field of it on a decision record, a named
   person rules, and `amend_objectives.py` writes it under that ruling, as a
   new version with the superseded value kept. Most of the file is not
   amendable at all. The ask itself is the approval path; there is no other
   one, and editing the file directly is the rule being broken rather than
   followed.
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

Part of that recommendation can be to change how the next batch is chosen.
That is the one lever here that points forward rather than at the round in
front of you, and it is the difference between reporting what a round cost and
doing something about it — which is also why it is bounded in code and inert
until somebody signs it.
