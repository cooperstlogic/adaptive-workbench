// The centre column for a round session.
//
// A session is a unit of work; this is the kind a round starts. What the
// conversation produces is a typed decision rather than prose, and two things
// are deliberately visible. The **tool calls are real**: every chip below is
// a command that ran against your copy of the project in this browser, with
// the output it printed. And the **ruling is not in the composer**: decisions
// are buttons, questions are asks.
//
// **The round goes to a laboratory on the way through.** Approving signs the
// batch, submits it and writes the order file the lab would receive — and
// then stops. Whether the results are back is a separate question, asked
// under the composer, answered by the registry, and refused the first time
// with the date it is expected. That is the least believable moment in the
// old build repaired: approving designs used to produce measured data in one
// click and about a second, and to an audience who have run assays that
// undercut everything around it.
//
// What the turns say is what ran and what came back. They do not say why the
// interface is shaped the way it is; that reasoning lives here and in
// DECISIONS.md, and a turn that recites it is a turn in the way of the round.

import { useState } from "react";
import Briefing from "./Briefing.jsx";
import Composer from "./Composer.jsx";
import Turn from "./Turn.jsx";
import {
  ACTION_LABEL, Badge, CentreHead, Hash, VERBS, dayMonth, n, pct, signed,
} from "./lib.jsx";

function Tool({ entry, defaultOpen }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const refused = entry.refused;
  return (
    <div className={`tool${refused ? " refused" : ""}`}>
      <button className="tool-head" onClick={() => setOpen(!open)}>
        <span className="tick">{entry.code === 0 ? "●" : refused ? "⊘" : "✕"}</span>
        <span className="grow">
          <span className="small">{entry.label}</span>
          <div className="tool-cmd">{entry.command}</div>
        </span>
        <span className="faint tiny">{open ? "hide" : "output"}</span>
      </button>
      {open && (
        <div className="tool-out">
          {entry.messages && <pre className="code">{entry.messages}</pre>}
          {entry.output && (
            <pre className="code" style={{ marginTop: entry.messages ? 8 : 0 }}>
              {entry.output}
            </pre>
          )}
          {!entry.output && !entry.messages && <pre className="code">(no output)</pre>}
        </div>
      )}
    </div>
  );
}

// The template's own list, with the two arguments that change what a test
// answers. run_diagnostic refuses any name outside objectives.json.
const DIAGNOSTICS = [
  { test: "offset_from_controls", label: "offset_from_controls", args: {} },
  { test: "residual_by_plate", label: "residual_by_plate", args: {} },
  { test: "replicate_concordance", label: "replicate_concordance", args: {} },
  { test: "residual_by_mutation_class", label: "residual_by_mutation_class --by position",
    args: { by: "position" } },
  { test: "residual_by_mutation_class", label: "… --by n_mutations",
    args: { by: "n_mutations" } },
  { test: "calibration_by_region", label: "calibration_by_region", args: {} },
  { test: "calibration_by_region", label: "… --offset bridge", args: { offset: "bridge" } },
];

export default function Session({ ctx, stored, suggestions }) {
  const {
    view, round, roundView, decision, log, busy, error, sessionId,
    onApprove, onDiagnose, onDiagnostic, onRule, onAdvance, onContinue,
    onAsk, onDownload, drops,
  } = ctx;
  const [verdict, setVerdict] = useState(null);
  const [note, setNote] = useState("");
  const [request, setRequest] = useState(view.objectives.diagnostics[4]);
  const [by, setBy] = useState("d.webster");

  const stage = roundView.status;
  const lab = roundView.lab;

  // Every command this round ran, in the order it ran, split at the moments
  // that matter: the submission, the arrival, the proposal, the ruling.
  const mine = log.filter((e) => e.round === round);
  const submittedAt = mine.find((e) => e.tool === "submit")?.n ?? Infinity;
  const importedAt = mine.find((e) => e.tool === "import_round")?.n ?? Infinity;
  const proposedAt = mine.find((e) => e.tool === "record_decision")?.n ?? Infinity;
  const ruledAt = mine.find((e) => e.command.includes("--rule"))?.n ?? Infinity;

  const selectionSteps = mine.filter((e) =>
    ["generate_candidates", "select_batch"].includes(e.tool) && e.n < submittedAt
    && !e.command.includes("--approved-by"));
  const sendSteps = mine.filter((e) => e.n >= submittedAt - 1 && e.n <= submittedAt + 1
    && ["select_batch", "submit", "export"].includes(e.tool));
  const waitSteps = mine.filter((e) => e.tool === "status"
    || (e.tool === "pull" && e.refused));
  const arriveSteps = mine.filter((e) => e.n >= importedAt - 1 && e.n <= importedAt + 1
    && ["pull", "import_round", "evaluate_prior"].includes(e.tool) && !e.refused);
  const decisionSteps = mine.filter((e) => e.tool === "run_diagnostic"
    || (e.n >= proposedAt && e.n <= ruledAt));
  const afterSteps = mine.filter((e) => e.n > ruledAt && e.n !== Infinity);

  // Every ask made in this session, read back from it. The one that asked
  // the laboratory is rendered where the results landed rather than at the
  // bottom, because that ask *is* the arrival -- it is the call that caused
  // it. The rest sit at the end of the stream, in the order they were asked.
  const turns = stored?.turns || [];
  const arrival = [...turns].reverse().find((t) => t.answer.kind === "arrival"
    && t.answer.ready);
  const pending = turns.filter((t) => t !== arrival);

  return (
    <>
      <CentreHead title={`Round ${round} · ${stage}`}
                  sub={`${view.project.lead.name} ${view.project.lead.chain} → ${
                    view.project.target} · ${view.n_designs} designs · assay ${
                    roundView.assay_version || "not yet run"}`}>
        {roundView.flagged && <Badge kind="flag">flagged</Badge>}
        {roundView.at_lab && <Badge kind="attn">at the lab</Badge>}
      </CentreHead>
      <div className="centre-inner thread">
        {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

        {stage === "awaiting approval" && (
          <Turn who="workbench">
            <p>
              The optimizer has proposed {roundView.batch.n} wells for round {round} —{" "}
              {roundView.batch.composition.control} control,{" "}
              {roundView.batch.composition.replicate} replicate,{" "}
              {roundView.batch.composition.exploration} exploration and{" "}
              {roundView.batch.composition.pick} fresh picks — from the{" "}
              {roundView.batch.model_winner} fit of round {round - 1}. Unsigned, it hashes to{" "}
              <Hash value={roundView.batch.hash} />.
            </p>
            {selectionSteps.map((e) => <Tool key={e.n} entry={e} />)}
            <p className="small muted">
              Review it in the Batch tab; strike anything you do not want and the override is
              recorded with your note. Approving submits the batch and writes the lab's order.
            </p>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn primary" disabled={busy} onClick={() => onApprove(by)}>
                {busy ? <span className="busy" /> : null}
                {drops.length
                  ? `Approve ${roundView.batch.n - drops.length} of ${roundView.batch.n} wells`
                  : `Approve and send ${roundView.batch.n} wells`}
              </button>
              <input className="field" style={{ width: 150 }} value={by}
                     onChange={(e) => setBy(e.target.value)} aria-label="approver" />
            </div>
          </Turn>
        )}

        {sendSteps.length > 0 && (
          <Turn who="workbench">
            <p className="small">
              Signed, submitted, and the order written. The registry minted the construct and
              sample identifiers and laid the wells out across its plates.
            </p>
            {sendSteps.map((e) => <Tool key={e.n} entry={e} />)}
            {roundView.order && (
              <button className="chip download" onClick={() => onDownload(roundView.order)}>
                ↓ round_{String(round).padStart(3, "0")}_order.csv
                <span className="tiny faint">
                  {roundView.submission?.n_samples || 48} rows · no value column
                </span>
              </button>
            )}
            {roundView.at_lab && (
              <p style={{ marginTop: 10 }}>
                Round {round} is <b>at the lab</b>
                {lab?.expected && <> — submitted {dayMonth(lab.submitted)}, expected{" "}
                  {dayMonth(lab.expected)}</>}.
              </p>
            )}
          </Turn>
        )}

        {waitSteps.length > 0 && (
          <Turn who="workbench">
            <p className="small">Asked the registry. Not back yet.</p>
            {waitSteps.map((e) => <Tool key={e.n} entry={e} />)}
          </Turn>
        )}

        {roundView.at_lab && (
          <Turn who="workbench">
            <p>
              {waitSteps.length
                ? "Ask again when you think it has had time."
                : "Nothing to do until it reports."}
            </p>
          </Turn>
        )}

        {arriveSteps.length > 0 && (
          <Turn who="workbench">
            <p className="small">
              Pulled, reconciled against the designs we submitted, and scored against what
              the model predicted for them.
            </p>
            {arriveSteps.map((e) => <Tool key={e.n} entry={e} />)}
          </Turn>
        )}

        {/* The answer to the ask, where the ask landed. If nobody asked -- a
            round imported before this session was opened -- the round's own
            record says the same thing, from the snapshot rather than from a
            turn. Never both. */}
        {arrival && (
          <>
            <Turn who="you"><p>{arrival.question}</p></Turn>
            <Turn who="claude"><Briefing data={arrival.answer} ctx={ctx} /></Turn>
          </>
        )}

        {arriveSteps.length > 0 && !arrival && (
          <Turn who="claude">
            {roundView.reconciliation && (
              <p>
                They are back. {roundView.reconciliation.rows} rows,{" "}
                {roundView.reconciliation.n_failed} well
                {roundView.reconciliation.n_failed === 1 ? "" : "s"} failed,{" "}
                {roundView.reconciliation.n_censored} value
                {roundView.reconciliation.n_censored === 1 ? "" : "s"} censored below the
                detection limit, {roundView.reconciliation.n_ok} of{" "}
                {roundView.reconciliation.designs} designs reconciled. Replicates came back as
                separate rows and were averaged over usable reads only — averaging a
                censored read into a real number would invent a measurement.
              </p>
            )}
            {roundView.anomaly && (
              roundView.flagged ? (
                <p>
                  And round {round} is <b>flagged</b>. Its {roundView.anomaly.n_compared} fresh
                  designs came back a mean{" "}
                  <span className="num">{signed(roundView.anomaly.mean_signed_residual)}</span>{" "}
                  pKD from where the model put them, against a trigger of{" "}
                  <span className="num">{n(roundView.anomaly.trigger_abs_pkd, 2)}</span>. The
                  assay version is {roundView.anomaly.assay_version} and the project has{" "}
                  {roundView.anomaly.known_version_offset === null
                    ? "never characterized it" : "an offset on record for it"}.
                  {" "}The flag is a threshold; what it means is not, and the same statistic is
                  tripped by an assay shift and by a real result.
                </p>
              ) : (
                <p>
                  Round {round} did not flag: mean signed residual{" "}
                  <span className="num">{signed(roundView.anomaly.mean_signed_residual)}</span>{" "}
                  pKD over {roundView.anomaly.n_compared} fresh designs, inside the trigger of{" "}
                  <span className="num">{n(roundView.anomaly.trigger_abs_pkd, 2)}</span>
                  {roundView.calibration && <> and coverage{" "}
                    <span className="num">
                      {pct(roundView.calibration.realized_coverage, 0)}</span></>}.
                  Nothing to decide.
                </p>
              )
            )}
          </Turn>
        )}

        {stage === "imported" && !roundView.flagged && (
          <Turn who="workbench">
            <button className="btn primary" disabled={busy} onClick={onContinue}>
              {busy ? <span className="busy" /> : null} Fit round {round} and propose round{" "}
              {round + 1}
            </button>
          </Turn>
        )}

        {roundView.flagged && !decision && (
          <Turn who="claude">
            <p>
              Two readings fit this first look and they take opposite actions: the assay moved,
              or the designs really are worse than predicted. Telling them apart means
              conditioning on the designs this round shares with earlier ones, because those
              are the same molecules measured twice.
            </p>
            {onDiagnose ? (
              <>
                <button className="btn primary" disabled={busy} onClick={onDiagnose}>
                  {busy ? <span className="busy" /> : null} Run the diagnosis
                </button>
                <p className="tiny faint" style={{ marginTop: 8 }}>
                  Replays the recorded diagnosis; every test is re-run against this copy of
                  the round.
                </p>
              </>
            ) : (
              <>
                <p className="small muted">No diagnosis is recorded for this round.</p>
                <div className="row wrap" style={{ marginTop: 10 }}>
                  {DIAGNOSTICS.map((d) => (
                    <button key={d.label} className="btn small" disabled={busy}
                            onClick={() => onDiagnostic(d.test, d.args)}>
                      {d.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </Turn>
        )}

        {decisionSteps.length > 0 && (
          <Turn who="claude">
            {decisionSteps.map((e) => <Tool key={e.n} entry={e} />)}
          </Turn>
        )}

        {decision && (
          <Turn who="claude">
            <p>
              {decision.hypotheses.length} hypotheses, each resting on a named test from the
              template's list.
            </p>
            <ul className="small" style={{ paddingLeft: 18, margin: "0 0 10px" }}>
              {decision.hypotheses.map((h) => (
                <li key={h.id} style={{ marginBottom: 3 }}>
                  <b className="mono">{h.id}</b> {h.claim}{" "}
                  <Badge kind={h.reading === "supported" ? "ok"
                    : h.reading === "partially supported" ? "flag" : ""}>{h.reading}</Badge>
                </li>
              ))}
            </ul>
            <p>
              Recommendation: <b>{ACTION_LABEL[decision.recommendation.action]}</b>, confidence{" "}
              {decision.recommendation.confidence}. The rationale, the alternatives and the{" "}
              <i>if_wrong</i> line are in the Decision tab.
            </p>
          </Turn>
        )}

        {decision && decision.status === "open" && (
          <Turn who="you">
            <div className="verbs">
              {VERBS.map((v) => (
                <button key={v.id} className="verb" aria-pressed={verdict === v.id}
                        onClick={() => setVerdict(v.id)}>
                  <b>{v.label}</b><span>{v.blurb}</span>
                </button>
              ))}
            </div>
            {verdict === "more_evidence_requested" && (
              <div className="row" style={{ marginTop: 10 }}>
                <span className="small muted">test to run</span>
                <select className="field" style={{ width: "auto" }} value={request}
                        onChange={(e) => setRequest(e.target.value)}>
                  {view.objectives.diagnostics.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
            )}
            <textarea className="field" style={{ marginTop: 10 }} rows={2}
                      placeholder="your reason, your modification, or your ask"
                      value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="row" style={{ marginTop: 10 }}>
              <input className="field" style={{ width: 150 }} value={by}
                     onChange={(e) => setBy(e.target.value)} aria-label="ruling by" />
              <button className="btn primary" disabled={!verdict || busy}
                      onClick={() => onRule(verdict, by, note,
                        verdict === "more_evidence_requested" ? request : null)}>
                {busy ? <span className="busy" /> : null} Rule
              </button>
            </div>
          </Turn>
        )}

        {decision && decision.status === "ruled" && (
          <Turn who="you">
            <p>
              <b>{decision.ruling.verdict.replace(/_/g, " ")}</b> by {decision.ruling.by}.
              {decision.ruling.note && <> “{decision.ruling.note}”</>}
            </p>
            {stage === "flagged, ruled" && !roundView.model && (
              <button className="btn primary" disabled={busy} onClick={onAdvance}>
                {busy ? <span className="busy" /> : null} Act on the ruling and propose round{" "}
                {round + 1}
              </button>
            )}
          </Turn>
        )}

        {afterSteps.length > 0 && (
          <Turn who="workbench">
            {afterSteps.map((e) => <Tool key={e.n} entry={e} />)}
            {roundView.frame?.offset_applied ? (
              <p>
                The frame moved by{" "}
                <span className="num">{signed(roundView.frame.offset_applied)}</span> pKD under
                authority <span className="mono">{roundView.frame.authority}</span>, and{" "}
                <span className="mono">import_round.py</span> checked that record before it
                moved anything: the authority has to exist, be ruled, and recommend the action
                being taken.
              </p>
            ) : null}
          </Turn>
        )}

        {pending.map((t, i) => (
          <div key={i}>
            <Turn who="you"><p>{t.question}</p></Turn>
            <Turn who={t.answer.kind === "arrival" ? "claude" : "workbench"}>
              <Briefing data={t.answer} ctx={ctx} />
            </Turn>
          </div>
        ))}

        <Composer suggestions={suggestions} busy={busy}
                  placeholder={`Ask about round ${round}…`}
                  onAsk={(key, forRound) => onAsk(key, forRound, sessionId)} />
      </div>
    </>
  );
}
