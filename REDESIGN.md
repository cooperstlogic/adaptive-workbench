# Redesign of the web app — the plan, and what was built from it

**Status: built. All eight blocks landed; `check.py` went from 147 invariants to 160 with
no existing one relaxed. The settled items are now `DECISIONS.md` decisions 122 to 133,
which is the record — this file is kept as the reasoning behind them.**

Three things resolved differently from the draft, and none of them changed a claim:

- **Section 13's open questions.** The four blank-project titles drafted in section 5 were
  taken as written. The round graph **kept its own route**, `#/p/<id>/rounds`, as sections
  3 and 6 assumed: a route can be linked, and the rail item holding it is the single new
  item in a rail of host items, which is the argument.
- **`#/new` and `#/templates` render the same screen**, because picking a template is the
  first thing you do on it. Both routes are live.
- **The configuration screen shows the antibody at 120 aa, not 119.** It reads
  `template.json` rather than a number in this document, and 120 is what the file says.

One thing the draft did not anticipate: the project-creation cap needed a way out, so the
new-project screen lists projects made in this browser with a **remove** control. The
remedy lives where the refusal happens rather than as a destructive button on the main
path.

This plan sits between phase 6 (done) and phase 7 (the live agent in the centre column).
It changes *where things live, what they are called, what a session is, and how a round
gets from approval to data*. It does not change `core/`, the landscape, the threshold, any
published number, or the science of the round loop.

**It amends four documents** — see section 11. The user's latest word governs where this
contradicts `CLAUDE.md`, `SPEC.md` or a settled decision.

---

## 1. What is wrong now

The current first load gives a visitor, at once: a wireframe banner; a left rail branded
**Adaptive workbench** whose five host items open essays in the centre column; a centre
column headed *Good afternoon* trying to be a home page; and a right-hand artifact panel
already showing **Round 4's 48-well batch table**, for a round nobody has opened.

1. **There is no home.** The home screen is a block *inside* the project shell, so the
   three-column chrome — including the artifact panel — is drawn around it.
2. **There is no project boundary.** The rail reads `Adaptive workbench / demo-trastuzumab`,
   so the product name and the project name are one object.
3. **The name makes the wrong claim.** The product is Claude Science; the *template* is what
   turns a project into a workbench.
4. **The lab is instantaneous.** Approving a batch produces measured data in one click and
   about a second. Section 8.

## 2. Naming

| Thing | Now | Proposed |
| --- | --- | --- |
| The app | Adaptive workbench | **Shannon Science** (`Beta` beneath) |
| Tab title | Adaptive Optimization Workbench | Shannon Science |
| The template, displayed | Antibody affinity maturation | **Adaptive antibody optimization** |
| The template, machine name | `antibody-affinity-maturation` | unchanged |
| The project | `demo-trastuzumab` in the brand slot | **Trastuzumab → HER2**, id in mono beneath |
| Centre-column speakers | You / Workbench / Claude | **You / Shannon / Claude** |
| The whole optimization cycle | — | **campaign**; `Rounds` stays the rail primitive |

Only the template's **display title** changes. `id` and `version` are written into
`project.json`, named by decision records and read by `check.py`; `title` is carried
nowhere.

**The wireframe banner is removed** (supersedes decision 60; see section 11). The
inline `synthetic` tags beside affinity numbers stay — that is `CLAUDE.md` failure mode 3,
a different rule and a four-word label rather than a banner.

## 3. Two shells, not one

**Shell A — Home.** Full-bleed, centred, ~1200px. No rail, no artifact panel.

**Shell B — Project.** Rail + centre + right panel, scoped to one project. The user's
second reference shot confirms the rail header is the *project* (back arrow, name,
chevron, collapse icon) and that New / Search / Customize / Files / Compute are
project-scoped items.

```
#/                        home
#/new                     new-project sheet
#/templates               template gallery
#/p/<id>                  project — redirects to the last natural interaction
#/p/<id>/s/new            a new, empty session
#/p/<id>/s/<session-id>   a session (round session or ad-hoc)
#/p/<id>/rounds           the round graph
```

## 4. What a session is

**A session is a unit of work inside a project. A new round starts a new session, and a
person can start an ad-hoc one at any time.** Both kinds share the rail list and home's
*Recent sessions*, which is what the reference screenshot shows — *Diagnose Round 4…* is a
round session, *List Designs Registry Connector* is ad-hoc.

This amends `SPEC.md` ("a session is a round"), and the amendment is where the thesis gets
demonstrated rather than asserted:

> **Demo beat.** Open a project you have never opened. Click `+ New`. Ask *where are we?*
> Back comes: six rounds, best observed 11.837 pKD (synthetic), round 2 flagged and ruled,
> round 4 flagged and waiting on you, the frame moved −1.014 pKD under `decision_002`,
> winning recipe `ridge_onehot`. Every figure is read from an artifact on disk and
> resolves in the Notebook tab to the `core/` function that produced it. The same question
> in a chat product gets a summary of the transcript, because there is no state to read.

**How it answers.** Until phase 7 there is no live model, so a new session offers
contextual suggested asks and each is answered by a **briefing assembled in `wb_driver`
from project artifacts** — deterministic, no model, every number traced. Phase 7 puts the
live model in the same seat and free text starts working. Decision 62's one-surface,
two-sources pattern applied to status rather than diagnosis.

**Suggested asks are contextual, in the composer, on every session** — not a button
elsewhere on the page, because a row of suggestions under the composer is the host's own
pattern. What is offered depends on where the round is: a round at the lab offers *have
round 4's results come back?*; a flagged round offers *why did this flag?*; a settled
project offers *where are we?* and *what's waiting on me?*

**This gives the build a clean rule: decisions are buttons, questions are asks.** Approval
and the four ruling verbs stay typed controls outside the composer — that is decision 65's
whole point, and the reason the approval primitive is not a chat interrupt. Everything
that only *reads* state — status, why a round flagged, whether the lab has reported —
belongs in the composer. The composer therefore stops being decorative in this redesign:
suggested asks work deterministically today, and free text starts working in phase 7.

## 5. Home

**Header.** `Shannon Science` in a system serif, `Beta` beneath, and inline in accent
`1 waiting on you · running in your browser`. Right: search (disabled), **Templates**,
`+ New project`.

**Needs you card.** Left column. `Round 4 — ruling pending`, project subtitle, status line,
`Needs you` pill, elapsed right-aligned.

**Projects.** The demo project plus four blank ones with plausible research titles, so the
list reads like a real workspace:

- *Cross-assay bridging: SPR against BLI on the 2024 panel*
- *Developability triage, Q3 lead set*
- *Plate-effect postmortem — HT-SPR run 118*
- *Literature scan: DG isomerization in CDR-H3*

They are one-shot analyses rather than campaigns, which is the contrast we want: clicking
one opens the empty chat interface, and that is what a project is without a template.

**Recent sessions.** Right column, both session kinds interleaved by recency.

## 6. A project opens where you left off

| Project state | Opens on |
| --- | --- |
| A round is flagged and unruled | that round's session, at the ruling |
| A batch is awaiting approval | that round's session, at the approval |
| A round is at the lab | that round's session, at the results check |
| Everything settled | the most recent session |
| A blank project | a new, empty session |

The round graph is one click away in the rail. It is a view, not a lobby.

## 7. Creating a project

### Blank project

Opens the chat interface from the user's second reference shot: rail header
`←  <name>  ⌄  ▤`; New / Search / Customize / Files / Compute; `No sessions yet`; settings
gear bottom-left. Centre: `New session`, empty, composer pinned to the bottom with
placeholder `Ask anything — @ for artifacts, # for sessions, / for skills, ⌘K to search…`,
`+` and a tools glyph left, a **working model picker** and a mic right. The picker lists
Opus 5 (selectable), Sonnet 5 and Haiku 4.5 (shown, not selectable).

**Blank projects never touch Python.** `project.load()` requires `project.json`,
`objectives.json`, `designs.json` and `rounds.json`; a project with no template has none of
them, which is the point rather than a limitation. They live in `localStorage`.

**They are the control arm** for decision 108 ("no project instantiation from a
declaration", graded *survives, but under-tested*). A blank project beside a templated one,
both created live in the same interface, converts it from assertion to demonstration.

### From a template

The gallery lists **Adaptive antibody optimization** (v1.1.0) and **Enzyme thermostability**
(stub, disabled). Picking the live one opens a configuration screen that is mostly
**locked**, which is the argument rather than a shortcut:

| Field | State | Value |
| --- | --- | --- |
| Project name | editable | `trastuzumab-affinity-2` |
| Template | locked | Adaptive antibody optimization · v1.1.0 |
| Input antibody | locked | trastuzumab VH, 119 aa, CDR-H3 highlighted |
| Target | locked | HER2 |
| Editable region | locked | VH 99–107 · `GGDGFYAM` |
| Constraints | locked | ≤ 2 mutations · forbidden `NG`, `DG`, `C` |
| Objectives | locked | affinity ↑ · hydrophobicity ≤ 0.55 · liabilities = 0 |
| Source data | locked | Registry (LIMS) · Bioprovider — both connected |
| Assay | locked | SPR · 24-well plates, 2 per round |
| Model selection | locked | `ridge_onehot` + `gp_pca64` — competed, lowest held-out NLPD wins |
| Batch policy | locked | 48 wells · 2 control · 2 replicate · 2 exploration |
| Round 1 policy | locked | single-mutant scan · `ADKSLW` |
| Diagnostics | locked | the five from the template |
| Team | editable | `d.webster` |

Everything locked is **read from `template.json`**, so the screen renders the declaration
rather than disabling a form. Caption: *none of this is configured here — the template
declares it, and the constraints are enforced in code before any model runs.* A few
plausible fields (assay platform, plate format) are mock and the app does not say so.

Create runs three real commands in Pyodide, visibly:

```
python init_project.py --template antibody-affinity-maturation --name <name> ...
python skills/adaptive-optimization/scripts/generate_candidates.py --project projects/<name> --round 1
python skills/adaptive-optimization/scripts/select_batch.py --project projects/<name> --round 1
```

**`init_project.py` is already the CLI's path** — `main(argv)` from decision 71, paths
resolved relative to its own file, and the bundle mirrors the repo layout. One line in
`web/bundle.py`'s `CODE` list and the browser instantiates through the same code.

Two details, neither needing UI copy: the **read seed differs per created project**
(derived from the name, so campaign two is not a replay of campaign one — read noise, not a
landscape parameter, and `demo-trastuzumab` is untouched); and **`localStorage` is ~5MB**,
so created templated projects are capped and the save failure `saveOverlay()` already
returns is surfaced.

## 8. The lab round trip — export, then wait, then check

**The problem.** `approve()` currently runs `select_batch` → `submit_batch` →
`pull_assay_results` → `import_round` → `evaluate_prior` in one click, so approving designs
produces measured data in about a second. That is the least believable thing in the build,
and to an audience of people who have run assays it undercuts everything around it.

**The fix: one approval becomes two moments with a lab between them.**

**Moment 1 — approve, submit, export.**

1. `select_batch --approved-by <name>` — the signature, as today.
2. `registry: submit_batch` — the registry mints construct and sample ids and lays 48 wells
   across two 24-well plates, as today.
3. `registry: export_submission` — **new**. Writes the order file the lab would receive:
   `construct_id, sample_id, design_id, round, plate, sequence, assay_version`. The centre
   column gets a **Download `round_004_order.csv`** chip that hands the visitor the real
   file out of the Pyodide filesystem, and the artifact panel gets an entry for it.

The round's status becomes **at the lab**. Nothing else happens.

**Moment 2 — check whether the data has arrived.**

The session ends with the agent saying the round is in flight. The only affordance is a
contextual suggested ask under the composer — *have round 4's results come back?* — which
calls one new registry tool:

4. `registry: check_run_status` — **new**. Returns `running` or `complete`, the assay
   version, when it was submitted and when it is expected.

The answer is binary. The first ask comes back **not ready**, with the expected date, and
`pull_assay_results` refuses while the round is running. The second comes back ready — and
**that is where the agent earns its place**, because the arrival is the first moment there
is anything to say: 96 rows across two plates on assay v1.2, three wells failed, two values
censored below the detection limit, 46 of 48 designs reconciled. Then `import_round` and
`evaluate_prior` run as the continuation of that answer, and the anomaly verdict lands in
the same turn.

**How the staggering works, and why it costs no invariant.** `lims.py`'s round record
already carries `status`, `submitted`, `samples` and `rows`; `status` is simply hardcoded
`"complete"`. `submit_batch` gains a `stagger` argument, off by default. Off, the record is
byte-identical to what it writes today and the CLI is completely unaffected. On, the record
is written `status: "running"` with an explicit, commented `release_on_check: 1`, and
`check_run_status` counts asks and releases the round once it is passed. A record with no
`release_on_check` key is complete — so every existing store, every existing round, and
`check.py`'s six-round CLI campaign are untouched. The cross-surface byte-identity claim
survives, which is load-bearing. The release schedule is a demo device and reads as one in
the source, which is the right place for it to be obvious.

**The refusal is a feature.** `registry_server.py`'s docstring says *every refusal in this
file is deliberate … so every one of them says what it refused and why.* "R4 is still
running: 24 of 48 wells reported, R4P2 queued" belongs in that list beside "a round already
submitted" and "a construct that does not exist."

**What the connectors gain.** Two read-only tools on the registry — `export_submission`
and `check_run_status` — both of which a real LIMS unambiguously owns. That strengthens
rather than dilutes the tool-list answer to *does this replace the LIMS*: the workbench
still cannot author a sample, design a plate or write a result. `bundle.py`'s requirements
table and `SKILL.md`'s step sequence both need the two new tools added.

**A related fix worth taking here.** The rail currently dates rounds 1 through 4 as
*today*, because that is when the demo project was generated — which visibly contradicts
the six-week campaign the pitch rests on. `web/bundle.py` should re-date the shipped
project's round entries to span roughly six weeks, and the turnaround the registry reports
should agree with that spacing. This touches `rounds.json`'s `updated` fields only, which
`check.py` already excludes from byte-identity as "the times the graph was rewritten".

> **Stage risk, recorded.** A presenter asks and is told no. That is the point, but it has
> to read as informative rather than broken, so the answer names the expected date and the
> ask stays offered. If it feels bad in rehearsal, `stagger` is one flag away from off.

## 9. What this costs

| Block | Work | Cuttable |
| --- | --- | --- |
| 1 | Hash router; split `App.jsx` into home shell and project shell | No |
| 2 | Home rebuilt to the reference layout; rename throughout; banner removed | No |
| 3 | `wb_driver` project-parameterised; `projects()`, `create_project()`, per-project store | No |
| 4 | New-project flow: blank (UI-only) + locked template configuration screen | No |
| 5 | Session model: round + ad-hoc sessions, the status briefing, contextual asks | No — the thesis |
| 6 | Blank-project chat interface to the reference shot, working model picker | No — the control arm |
| 7 | Lab round trip: `export_submission`, `check_run_status`, release-on-ask, the two-moment flow | No — the user asked |
| 8 | Rail rework, round graph as a view, re-dated history, docs, `check.py` invariants | Partly |

`CLAUDE.md` names this risk: *the shell has no natural stopping point … if it is eating
phase 7, ship it uglier.* Block 8 is where polish lives and is what gets cut first. Block 7
is the one block here that is not interface work, and it is the one I would protect
hardest after block 1, because it is the difference between a demo an assay scientist
believes and one they do not.

## 10. New invariants for `check.py`

All existing invariants must still pass untouched. Three worth adding:

1. A project instantiated in the browser from the template is **byte-identical** to one the
   CLI instantiates — the checkable form of decision 108. Needs a `--created` flag on
   `init_project.py` so the timestamp can be pinned.
2. The registry **refuses a pull on a round still running** and names what is missing.
3. The export file contains **no measured value** — it is an order, not a result. Its rows
   match the submission's samples exactly.

## 11. Documents this amends

Per the user: *if anything I'm telling you now contradicts `CLAUDE.md` or other docs, take
my most recent word and update the docs.*

| Document | Change |
| --- | --- |
| `CLAUDE.md` | Failure mode 1 — "label it stubbed **in the UI**" narrows to the README and the staged table; the prototype framing is stated once there. Failure mode 3 untouched |
| `DECISIONS.md` | New block. Supersedes **60** (wireframe label on the page). Amends **59** (a session is a round → a session is a unit of work). Records the lab round trip, the locked configuration screen, blank projects as the control arm for **108**, and the Shannon Science naming |
| `SPEC.md` | Web app section: two shells, session model, landing rule, new-project flow, the export-and-check round trip. The staged table gains the rows the banner used to carry |
| `SKILL.md` | Step sequence gains `export_submission` and `check_run_status`, so the skill and the browser describe the same lab |
| `README.md` | Build status; the staged table becomes where the honesty claim lives |

## 12. Settled in draft 4

- **Turnaround is display-level for live rounds.** No simulated dates are written into
  project artifacts. Only the *shipped* history is re-dated, in `bundle.py`, so the rail
  shows a campaign spanning weeks instead of four rounds all stamped today.
- **The results check is binary**, not partial by plate. Not ready, or ready — and ready is
  where the agent has something to say.
- **No `Check for results` button.** A suggested ask under the composer, which is the
  host's pattern, and which follows the rule in section 4: decisions are buttons, questions
  are asks.

## 13. Still open

1. Names for the blank projects are drafted in section 5 but not settled.
2. Whether the round graph keeps its own route (`#/p/<id>/rounds`) or becomes a tab in the
   artifact panel. A route is more visible; a tab is less chrome.
3. Nothing else. Say the word and block 1 starts.
