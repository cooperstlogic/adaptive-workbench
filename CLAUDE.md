# CLAUDE.md

Project context and working rules. Read `SPEC.md` for full spec.

## What this is

A one-day functional prototype of an adaptive therapeutic optimization workbench: a
scientist-governed system that takes an antibody lead, learns from each round of
experimental results, and recommends the next batch of variants to test.

## Why it exists

This is a pitch artifact aimed at Anthropic. The argument it makes: Claude Science is
excellent at one-shot analyses, and the missing layer above it is **persistent decision
state across experimental rounds** — a template that instantiates a project, skills that
read and write that project's state, connectors that keep the LIMS authoritative, and a
narrow surface for approving decisions rather than chatting about them.

The audience is technically sophisticated and will poke at it. Optimize for a demo that
survives scrutiny, not for feature count.

## The proof artifact

One chart: cumulative best-observed affinity versus experimental round, model-guided
selection against a random-selection baseline, on real measured data. Everything else
exists to make that chart trustworthy and its decisions inspectable.

## Two failure modes that matter more than missing features

1. **A mock dressed up as real.** If something is stubbed, label it stubbed — in the UI
   and in the README. `SPEC.md` has a "What is real and what is staged" table; keep it
   accurate as you build.
2. **The science implemented twice.** The same Python must run in Claude Science, from
   the CLI, and in the browser via Pyodide. Never port `core/` to JavaScript, even if it
   would be faster. That fork would undermine the entire demo.

## Non-negotiables

1. `core/` is pure numpy. No scipy, no scikit-learn, no pandas.
2. `core/` does no network I/O and no printing. Skills, MCP servers, and the web app are
   thin wrappers over it.
3. Project state is a directory of JSON files. No database, no server.
4. The oracle lives behind the registry MCP server. `core/` never imports it. Assay
   results come back with LIMS-owned identifiers, plate wells, assay versions, failures,
   and left-censored values, so `import_round` has real reconciliation work to do.
   `simulate_campaign.py` is the one exception: it is the evaluator, not the product, and
   it reads landscape values to score the diagnostic line. Nothing on a product path may.
5. Never build sample inventory, plate design, or assay authoring. Their absence is the
   argument.
6. Constraints declared in a template are enforced in code before optimization runs, not
   suggested to the model.

## How to work

- Build in the order of the hour table in `SPEC.md`, one block at a time. At the end of
  each block, stop and show what works before continuing.
- **The hour-3 gate is real.** `simulate_campaign.py` must show guided selection beating
  random on rounds-to-threshold, over 20 seeds per arm, against a threshold fixed before
  the first run. If it doesn't separate, stop and fix the science — do not start on
  skills or UI. Say plainly that it isn't separating rather than tuning until it looks
  good, and never re-pick the threshold after seeing a curve.
- Prefer the boring implementation. Where the spec leaves a choice open, take the one
  with fewer moving parts and record it in `DECISIONS.md`.
- If something in the spec is wrong, underspecified, or would blow its hour budget, say
  so before building it rather than working around it silently.
- Don't add dependencies without asking. The dependency list is a design constraint, not
  an oversight.

## Cut order if time runs short

Explain panel → second template stub → Pareto scatter (keep the table) → override note
field. ESM-2 features are not a cut: they are off the critical path by design, built
only if hour 5 is free, with one-hot as the default feature block either way.

**Never cut:** the proof chart, the approve loop, the CLI path through the skill.
