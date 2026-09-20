# CLAUDE.md

Working rules for this repository. `README.md` explains what the project is, what is real
and what is staged, and how the loop works — read it first. Read
`skills/adaptive-optimization/SKILL.md` before touching anything in the round loop.

## What this is

A functional prototype of an adaptive therapeutic optimization workbench: a
scientist-governed system that takes an antibody lead, learns from each round of
experimental results, and recommends the next batch of variants to test.

The vision it demonstrates is this: Claude Science already offers broad connectors and
skills, and building an adaptive optimization workflow on them still takes specialized
know-how — the data mappings, the models, the decision logic and the review interface.
**Templating those makes the workflow adoptable and repeatable, and the persistent record
of objectives, predictions, experiments and outcomes accumulates project-specific value
over rounds.** Frame it as that positive vision, not as a gap in the product.

**The build is complete and deployed** — https://adaptive-workbench-iota.vercel.app, on
Vercel rather than Netlify because the proposal turn runs 70 to 110 seconds and Netlify's
streaming limit is a hard 60. **Deploys come from GitHub**: a push to `main` is production
and every other branch gets a preview. The Vercel project's Root Directory is `web`, so
the CLI is run from the repository root, and the key and the budget variables are set on
Production only — a preview runs without a seat and spends nothing.

## Commands

- Use `.venv/bin/python`, never `python3` — the system interpreter has no numpy.
- **Run `.venv/bin/python check.py` before and after any change.** It verifies 197
  invariants; a failure means the state drifted from what is documented. It takes about
  forty seconds, because it runs two full six-round campaigns through the CLI, checks them
  against the evaluator, drives both connectors over the MCP protocol, boots Pyodide twice
  to compare the browser's artifacts against the CLI's byte for byte, and calls the model
  function in-process with no key. Those need `cd web && npm install && npm run sync`;
  without it they report SKIPPED and fail, which is deliberate.
- **Re-run `python web/bundle.py` after touching anything the browser executes** —
  including `web/py/wb_driver.py`, and including `SKILL.md`, which the same script writes
  into the model function as its system prompt.

## Non-negotiables

1. **`core/` is pure numpy.** No scipy, no scikit-learn, no pandas — and this rule is
   about `core/` only. Not because those cannot run in the browser, which they can, but
   because `core/` is the part an audience is invited to read: fifty lines of numpy they
   can check beats a library call they have to trust. **Outside `core/` the rule is
   ordinary judgment** — `simulate_campaign.py` and `plot_campaign.py` are evaluator paths
   and use matplotlib. Still ask before adding a dependency, and never add one to `core/`.
2. **The science is implemented once.** The same Python must run in Claude Science, from
   the CLI, and in the browser via Pyodide. Never port `core/` to JavaScript, even if it
   would be faster. That fork would undermine the whole claim.
3. `core/` does no network I/O and no printing. Skills, MCP servers and the web app are
   thin wrappers over it.
4. Project state is a directory of JSON files. No database, no server.
5. **The oracle lives behind the registry MCP server; `core/` never imports it.**
   `simulate_campaign.py` is the one exception — it is the evaluator, not the product, and
   it reads landscape values to score the diagnostic line. Nothing on a product path may.
   The connector directory is `connectors/` and **not** `mcp/`: a bare directory of that
   name is a namespace package and shadows the `mcp` PyPI distribution.
6. **Never build sample inventory, plate design, or assay authoring.** Their absence is
   the argument.
7. **Constraints declared in a template are enforced in code before optimization runs**,
   not suggested to the model. Same for the anomaly flag: deciding that a round *looks
   wrong* is a threshold, deciding *why* is the agent's job.
8. **The model produces no numbers.** Every value in a decision record traces to a named
   `core/` function with hashed inputs. The model selects which test to run, in what order,
   and what the results mean together. It may write code that produces a number — but only
   ad hoc, only read-only against mounted snapshot arrays, only with the source stored
   beside the result, and the number is evidence a human reads, never an input to a code
   path. The moment an LLM is doing the statistics behind the chart, the claim is dead.
9. **Landscape parameters are pre-registered; the threshold was amended once, on the record.**
   Do not change the landscape, the seed or any other parameter — git history proves the
   order and `landscape.npz` is still byte-for-byte what `473ac01` produced. The gate is the
   one exception: it was moved on 2026-09-20 from the pre-registered 99th percentile
   (10.762 pKD) to 75% of the parent-to-max climb (**11.006 pKD**), after the runs were seen,
   because rounds-to-threshold was ceiling-limited and had no resolution. **A threshold moved
   after the fact is an amendment and is written down as one**: the superseded rule and value
   stay in the `amendments` block of `data/landscape_manifest.json`, the README states it in
   its own section, and `check.py` asserts the block is intact. Never restate the amended
   number as pre-registered, and never quote its margin without the amendment beside it.
   **Any further move needs the same treatment or it does not happen.** If guided does not
   separate from random, say so.
10. **Selection must be reproducible, and it is checked.** Ties in predictive uncertainty
    are the normal case rather than a corner case, so anything that ranks candidates breaks
    its ties on a stated reason and then on pool order, never on array order. `check.py`
    runs the CLI and the evaluator over the same six rounds and requires that they choose
    the same 288 wells.

## Three failure modes that matter more than missing features

1. **A mock dressed up as real.** If something is stubbed, label it stubbed. The claim
   lives in the README's "What is real and what is staged" table, which is where a sceptic
   goes looking, and it is stated once there rather than banged on a banner across every
   screen. Individual mock fields still carry their own label where they sit — as a word or
   a tooltip, never a paragraph. **Show, don't tell.** Text on a page reports state or
   labels a stub; it never explains why the interface is shaped the way it is. That
   reasoning lives in source comments and the README.
2. **The science implemented twice.** See non-negotiable 2.
3. **Overclaiming a synthetic result.** The landscape is invented, so the chart proves the
   machinery and not the chemistry. Say the word "synthetic" in the same breath as the
   number wherever a number is quoted in prose — the one-word tag on a briefing figure,
   with the explanation as its tooltip — and make the full claim once, in the README's
   staged table. **The evaluator's benchmark is drawn on the template surfaces as the
   template's validation and never on a project's own axes**: a project cannot be compared
   against a random arm it never ran, and a chart that looks like a forecast from a
   simulation is this failure mode in a new coat.

## The two proof artifacts

1. **One chart:** cumulative best-observed affinity versus experimental round, model-guided
   selection against a random-selection baseline.
2. **One decision record:** round 4 comes back ambiguous, the agent forms competing
   hypotheses, tests them with library diagnostics, and a named human rules.

The chart shows the loop converges. The record shows something is reasoning inside it.
Without the second, this is a scheduler calling five scripts in order.

**`decision_004.json` is gate output and is not to be hand-edited.** An agent with only the
skill and the connectors wrote it, `check.py` recomputes every number in it, and its whole
value is that nobody touched it. Amendments go through a ruling.

**Round 5 flags at −0.818 pKD on the product path** and nobody has diagnosed it: only a
live seat can, and that beat is deliberately not in the harness.

## How the interface is shaped

**The app is called Shannon Science** — `web/src/lib.jsx`'s `APP`, the tab title, the home
brandmark with `Beta` beneath, and the first sentence of the model's system prompt in
`web/function/ask.mjs`. It is this repository's layer; Claude Science is the host it is
arguing about. **It wears the Claude Science interface**, because the claim is that this is
a layer inside it rather than a product beside it. It is **two shells**: a home screen that
is full-bleed and owns no project, and a project shell with a rail, a centre conversation
and a right artifact panel. **A session is a unit of work** — a round starts one, and a
person can start an ad-hoc one at any time.

**Decisions are buttons; questions are asks.** Approval and the four ruling verbs are typed
controls outside the composer — that is why the approval primitive is not a chat interrupt.
Everything that only *reads* state belongs in the composer, as free text to the seat.

**Nothing sits over the composer.** There were suggested asks once, presented as a card of
numbered options; they were more distraction than help and are gone, together with the
driver's `suggested_asks` and the checks on it. Do not put a suggestion, a chip or a
generic ask back under the box. Without a seat the composer says so and stays disabled;
the loop still runs entirely on buttons. **The results check is a button**, *Ask the
registry*, beside the lab control — it is a call to the registry rather than a question,
the model cannot make it, and it goes through `wb_driver.ask("results_back")` so the turn
it leaves is a question and the registry's answer. That deterministic briefing, assembled
from artifacts on disk, **is not to be removed**: it is what the arrival renders, and the
figures in it resolve to `core/` functions in the Notebook tab. A round is settled the
moment it is fitted and the next batch is out, however quietly it came back.

**The lab is not instantaneous, and it must not become so again.** Approving a batch
submits it and writes the order file the lab receives, and then stops. Whether the results
are back is a separate question put to the registry, refused the first time with the date
it is expected. `lims.py`'s `submit_batch` takes `--stagger`, off by default, so every CLI
path and every existing store is byte-for-byte unaffected. **The clock can be moved by
hand, and only by hand** — *Have the lab report now* is a control marked **simulated**,
calling `lims.py release`, and it changes when the registry hands the rows over and nothing
about what they say. It does not collapse the two moments: a released run still has to be
pulled by someone asking for it, and the state between the two — *results ready* — is a
place the interface has. **Approving must never produce data again.**

**The shell has no natural stopping point.** Every hour on rail iconography is an hour not
spent on what the rail holds. The agent in the centre column is the claim and the chrome is
the frame around it.

## The model in the seat

- **The model produces no numbers, still.** Its tools are two reads, the registry, and
  `record_decision.py --propose`, and the writer's refusal goes back to it as an error
  result. `check_lab_results` is the one tool that writes, and what it writes is a round the
  laboratory reported, pulled and imported by the same two scripts every surface runs.
- **The function is not a proxy.** It builds every request itself and accepts only
  transcripts it signed — never loosen `validate()` to take a `messages` array.
- **The session is the conversation, and transcripts are not state.** A session holds one
  signed transcript in page memory, and the diagnosis, every question asked after it and
  the ruling that sends it back all continue it, so a follow-up can refer to what was said.
  The decision record is what persists and is re-read into the context on every turn; after
  a reload the next turn starts a fresh transcript from it, and a transcript the function
  refuses starts over with *restarted* on the badge rather than ending the turn.
- **Claude speaks only when a model or the record's author wrote the words**, with a mode
  badge over every such turn — and the badge is the only label in the stream. The column is
  a chat: your asks and rulings are bubbles on the right, the workbench's prose is the
  column itself with nothing over it, and no turn names a speaker.
- `WORKBENCH_UPSTREAM=scripted` is the harness's test double and is labelled everywhere it
  shows; **it is never to be set on the site.**

## Working in Claude Science

- **Check the app's own state before the docs.** `~/.claude-science/mcp/local-mcp.json` is
  what the connector dialog actually saved, and `logs/spawn.log` is what the daemon
  actually did. Both beat the published documentation.
- **Never revert repository state underneath a running host session.** Doing so made an
  agent correctly report its own verified write as missing, and offer two wrong hypotheses
  for why. Cleanup waits for the session to finish, or is told to the session in words.
- **A connector that is "still loading" is diagnosed, not waited on.** A missing argument
  produces no error, no timeout and no log line.
- **The host install does not travel.** Showing it there needs a machine with the skill imported,
  both connectors configured, `config.toml` carrying both sandbox grants, and a restart
  since. Verify it green before the room fills; it cannot be done live.

## How to work

- Prefer the boring implementation. Where a choice is open, take the one with fewer moving
  parts.
- If something is wrong or underspecified, say so before building it rather than working
  around it silently.
- Don't add dependencies without asking. The dependency list is a design constraint, not an
  oversight — numpy for `core/`, matplotlib for the evaluator, and nothing else without a
  conversation.
- Everything laboratory is simulated in this build: synthetic landscape, one-hot features
  only, local provider backend. Real data, real embeddings and a live backend are upgrades
  beyond it.
- Numbered `decision NNN` references in source comments point at `DECISIONS.md`, a build
  decision log removed once the build finished. Read it with `git show 2c60c0b:DECISIONS.md`.
  It lives on the **`build-history`** tag, which holds the 49 commits this branch was squashed
  from — including the three that pre-registered the landscape parameters before the landscape
  existed, which `README.md` cites by SHA. **Do not delete that tag**; those claims stop being
  checkable without it.
