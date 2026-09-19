# CLAUDE.md

Project context and working rules. Read `SPEC.md` for full spec and `DECISIONS.md` for
every choice already settled.

## Where the build is

**Phases 1, 2 and 3 are done and the hour-3 gate passed. Phase 4 is next.** Full status,
results and commands are in `README.md`; every settled choice and its reasoning is in
`DECISIONS.md`. Read both before writing code, and read
`skills/adaptive-optimization/SKILL.md` before touching anything in the round loop.

- Use `.venv/bin/python`, never `python3` — the system interpreter has no numpy.
- Run `.venv/bin/python check.py` before and after any phase. It verifies 73 invariants
  that correspond to rules here and numbers in `DECISIONS.md`; a failure means the state
  drifted from what is documented. It takes about twenty seconds, because it runs two full
  six-round campaigns through the CLI and checks them against the evaluator.
- **The threshold is already fixed at 10.762 pKD**, pre-registered and recorded before any
  campaign ran. Do not recompute, re-pick, or adjust it. Do not change the landscape or
  its parameters. If guided does not separate from random, say so.
- Update `README.md`'s build status table and append to `DECISIONS.md` at the end of every
  phase, so the next session can pick up without reading the transcript.

## What this is

A one-day functional prototype of an adaptive therapeutic optimization workbench: a
scientist-governed system that takes an antibody lead, learns from each round of
experimental results, and recommends the next batch of variants to test.

## Why it exists

This is a pitch artifact aimed at Anthropic. The argument it makes: Claude Science is
excellent at one-shot analyses, and the missing layer above it is **persistent decision
state across experimental rounds** — a template that instantiates a project, skills that
read and write that project's state, connectors that keep the LIMS authoritative, and a
narrow surface for approving decisions rather than chatting about them. The reason that
layer matters is that it is what lets a model exercise judgment across rounds instead of
answering one question at a time.

The audience is technically sophisticated and will poke at it. Optimize for a demo that
survives scrutiny, not for feature count.

**The web app wears the Claude Science interface**, because the claim is that this is a
layer inside it rather than a product beside it: a home screen with a `Needs you` card,
a left rail whose sessions are rounds, a centre conversation, and a right artifact panel
with tabs. The chrome is a wireframe and is labelled one. Decisions 57–66 in
`DECISIONS.md` record that choice, why orchestration runs live while the verdict stays
human, and what was cut to pay for it. Read them before phase 6.

**Phase 5b is the checkpoint that matters for the pitch.** Beta access to Claude Science
is confirmed and it takes custom connectors and local skill packs, so the plugin installs
and the round-4 gate runs in the host. Its second deliverable is an audit of where the
host's abstractions actually run out — it already has projects, Files, persistent kernels,
artifacts with history, inherited skills and a *waiting on you* queue. Any gap this
artifact claims that does not survive contact with the product gets struck, not argued
harder. Phase 6 builds against the surviving list. Decisions 67–71 record this.

## The two proof artifacts

1. **One chart:** cumulative best-observed affinity versus experimental round,
   model-guided selection against a random-selection baseline.
2. **One decision record:** round 4 comes back ambiguous, the agent forms competing
   hypotheses, tests them with library diagnostics, and a named human rules on the
   recommendation.

The chart shows the loop converges. The record shows something is reasoning inside it.
Without the second, an Anthropic audience sees a scheduler calling five scripts in order
and the pitch collapses within ninety seconds. Everything else exists to make both
trustworthy and inspectable.

## Three failure modes that matter more than missing features

1. **A mock dressed up as real.** If something is stubbed, label it stubbed — in the UI
   and in the README. `SPEC.md` has a "What is real and what is staged" table; keep it
   accurate as you build.
2. **The science implemented twice.** The same Python must run in Claude Science, from
   the CLI, and in the browser via Pyodide. Never port `core/` to JavaScript, even if it
   would be faster. That fork would undermine the entire demo.
3. **Overclaiming a synthetic result.** The landscape is invented, so the chart proves
   the machinery and not the chemistry. Say the word "synthetic" in the same breath as
   the number, every time, in every surface.

## Non-negotiables

1. **`core/` is pure numpy.** No scipy, no scikit-learn, no pandas — and this rule is
   about `core/` only. It is not because those packages cannot run in the browser;
   Pyodide ships wheels for all of them. It is because `core/` is the part an audience
   is invited to read, and fifty lines of numpy they can check beats a library call they
   have to trust, and because every wheel is weight on a cold visit to a public URL.
   **Outside `core/` the rule is ordinary judgment.** `simulate_campaign.py` and
   `plot_campaign.py` are evaluator paths, not product paths, and they use matplotlib.
   The web app renders its own charts in the browser from `campaign.json`. Still ask
   before adding a dependency, and never add one to `core/`.
2. `core/` does no network I/O and no printing. Skills, MCP servers, and the web app are
   thin wrappers over it.
3. Project state is a directory of JSON files. No database, no server.
4. The oracle lives behind the registry MCP server. `core/` never imports it. Assay
   results come back with LIMS-owned identifiers, plate wells, assay versions, failures,
   and left-censored values, so `import_round` has real reconciliation work to do.
   `simulate_campaign.py` is the one exception: it is the evaluator, not the product, and
   it reads landscape values to score the diagnostic line. Nothing on a product path may.
   In this build the registry is `lims.py` at the repo root; `mcp/` holds only the two
   server entry points, because an importable package named `mcp` would shadow the PyPI
   distribution FastMCP is built on.
5. Never build sample inventory, plate design, or assay authoring. Their absence is the
   argument.
6. Constraints declared in a template are enforced in code before optimization runs, not
   suggested to the model. The same goes for the anomaly flag: deciding that a round
   *looks wrong* is a threshold, deciding *why* is the agent's job.
7. **The model produces no numbers.** Every value in a decision record traces to a named
   `core/` function with hashed inputs. The model selects which test to run, in what
   order, and what the results mean together. It may write code that produces a number —
   but only ad hoc, only read-only against mounted snapshot arrays, only with the source
   stored beside the result, and the number is evidence a human reads, never an input to
   a code path. The moment an LLM is doing the statistics behind the chart, the demo is
   dead.
8. **Landscape parameters are pre-registered.** Epistasis order, ruggedness, noise scale,
   cliff position and depth, and the detection limit are written into `DECISIONS.md` and
   committed *before* `simulate_campaign.py` runs for the first time, justified on
   grounds independent of the outcome. Git history proves the order. Never tune them
   after seeing a curve.

## How to work

- Build in the order of the phase table in `SPEC.md`, one block at a time. At the end of
  each block, stop and show what works before continuing.
- **The hour-3 gate is real.** `simulate_campaign.py` must show guided selection beating
  random on rounds-to-threshold, over 20 seeds per arm, against a threshold fixed before
  the first run. If it doesn't separate, stop and fix the science — do not start on
  skills or UI. Say plainly that it isn't separating rather than tuning until it looks
  good, and never re-pick the threshold or regenerate the landscape after seeing a curve.
- **The hour-5 gate is real too.** Claude Code, given only the skill and the connectors,
  must diagnose round 4 correctly and write a decision record. If it can't, the agentic
  claim fails and that is worth an hour taken from the web app.
- Prefer the boring implementation. Where the spec leaves a choice open, take the one
  with fewer moving parts and record it in `DECISIONS.md`.
- **Selection must be reproducible, and it is checked.** Ties in predictive uncertainty
  are the normal case rather than a corner case, so anything that ranks candidates breaks
  its ties on a stated reason and then on pool order, never on array order. `check.py`
  runs the CLI and the evaluator over the same six rounds and requires that they choose
  the same 288 wells.
- If something in the spec is wrong, underspecified, or would blow its hour budget, say
  so before building it rather than working around it silently.
- Don't add dependencies without asking. The dependency list is a design constraint, not
  an oversight. numpy for `core/`, matplotlib for the evaluator, and nothing else without
  a conversation.
- Everything laboratory is simulated in this build: synthetic landscape, one-hot features
  only, local provider backend. Real data, real embeddings and the live backend are
  listed under "After the demo works" and are attempted only once phase 9 passes.

## Cut order if time runs short

Ad hoc code execution (keep the five library diagnostics) → second template stub →
Pareto scatter (keep the table) → the Notebook tab → the browser's *live* mode (keep
animated replay) → override note field.

**Never cut:** the proof chart, the approve loop, the round-4 decision record, the
push-back round trip, the CLI path through the skill.

**The shell has no natural stopping point.** Phases 6 and 7 imitate the Claude Science
interface, and every hour on rail iconography is an hour not spent on what the rail holds.
The shell is done when the five demo beats land. If it is eating phase 7, ship it uglier —
the agent in the centre column is the claim and the chrome is the frame around it.
