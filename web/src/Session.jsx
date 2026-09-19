// The centre column: a round's session.
//
// In Claude Science the centre is a conversation and the rail lists chat
// threads named after what was asked. Here the centre is still a conversation
// and the rail still lists sessions -- but a session is a round, and what the
// conversation produces is a typed decision rather than prose.
//
// Two things are deliberately visible. The **tool calls are real**: every
// chip below is a command that ran against your copy of the project in this
// browser, with the output it printed. And the **ruling is not in the
// composer**: the composer is here because the host has one, and it is
// explicitly not where the decision goes.

import { useState } from "react";
import { ACTION_LABEL, Badge, Hash, VERBS, n, pct, signed } from "./lib.jsx";

function Tool({ entry, defaultOpen }) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div className="tool">
      <button className="tool-head" onClick={() => setOpen(!open)}>
        <span className="tick">{entry.code === 0 ? "●" : "✕"}</span>
        <span className="grow">
          <span className="small">{entry.label}</span>
          <div className="tool-cmd">{entry.command}</div>
        </span>
        <span className="faint tiny">{open ? "hide" : "output"}</span>
      </button>
      {entry.note && !open && <div className="tool-note">{entry.note}</div>}
      {open && (
        <div className="tool-out">
          {entry.note && <p className="tiny faint" style={{ marginTop: 0 }}>{entry.note}</p>}
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

function Turn({ who, children }) {
  const label = { you: ["Y", "You"], workbench: ["W", "Workbench"],
                  claude: ["C", "Claude"] }[who];
  return (
    <div className="msg">
      <div className="msg-who">
        <span className="dot">{label[0]}</span>
        <span>{label[1]}</span>
      </div>
      <div className="msg-body">{children}</div>
    </div>
  );
}

export default function Session({ ctx }) {
  const {
    view, round, roundView, decision, log, busy, error,
    onApprove, onDiagnose, onDiagnostic, onRule, onAdvance, onContinue, drops,
  } = ctx;
  const [verdict, setVerdict] = useState(null);
  const [note, setNote] = useState("");
  const [request, setRequest] = useState(view.objectives.diagnostics[4]);
  const [by, setBy] = useState("d.webster");

  const stage = roundView.status;

  // Every command this round ran, in the order it ran, split at the two moments
  // that matter: the proposal and the ruling.
  const mine = log.filter((e) => e.round === round);
  const proposedAt = mine.find((e) => e.tool === "record_decision")?.n ?? Infinity;
  const ruledAt = mine.find((e) => e.command.includes("--rule"))?.n ?? Infinity;
  const selectionSteps = mine.filter((e) =>
    ["generate_candidates", "select_batch"].includes(e.tool) && e.n < proposedAt
    && !e.command.includes("--approved-by"));
  const approvalSteps = mine.filter((e) => e.n < proposedAt
    && e.tool !== "run_diagnostic" && !selectionSteps.includes(e));
  const decisionSteps = mine.filter((e) => e.tool === "run_diagnostic"
    || (e.n >= proposedAt && e.n <= ruledAt));
  const afterSteps = mine.filter((e) => e.n > ruledAt);

  return (
    <div className="centre-inner">
      <div className="spread" style={{ marginBottom: 14 }}>
        <div>
          <h2>Round {round} · {stage}</h2>
          <p className="small muted" style={{ margin: "2px 0 0" }}>
            {view.project.lead.name} {view.project.lead.chain} → {view.project.target} ·{" "}
            {view.n_designs} designs · assay {roundView.assay_version || "not yet run"}
          </p>
        </div>
        {roundView.flagged && <Badge kind="flag">flagged</Badge>}
      </div>

      {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

      {stage === "awaiting approval" && (
        <Turn who="workbench">
          <p>
            The optimizer has proposed {roundView.batch.n} wells for round {round} —{" "}
            {roundView.batch.composition.control} control,{" "}
            {roundView.batch.composition.replicate} replicate,{" "}
            {roundView.batch.composition.exploration} exploration and{" "}
            {roundView.batch.composition.pick} fresh picks — from the{" "}
            {roundView.batch.model_winner} fit of round {round - 1}. Nobody has signed it, so
            it hashes to <Hash value={roundView.batch.hash} /> on any machine that selects it
            from this state.
          </p>
          {selectionSteps.map((e) => <Tool key={e.n} entry={e} />)}
          <p className="small muted">
            Review it in the Batch tab. Strike anything you do not want; the override is
            recorded with your note by the same script that chose it.
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

      {approvalSteps.length > 0 && (
        <Turn who="workbench">
          <p className="small">
            Sent to the registry, pulled back, reconciled against the designs we submitted.
          </p>
          {approvalSteps.map((e) => <Tool key={e.n} entry={e} />)}
          {roundView.anomaly && (
            roundView.flagged ? (
              <p>
                Round {round} is <b>flagged</b>. Its {roundView.anomaly.n_compared} fresh
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
                Nothing to decide. Declining to act is a judgment too, and it is recorded as
                one.
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
              <p className="small muted">
                The diagnosis below was written by Claude Code in the hour-5 gate, given only
                the skill and the two connectors. Running it here re-runs every test against
                your copy of the round and writes the numbers it gets — no figure in the
                record is carried across.
              </p>
              <button className="btn primary" disabled={busy} onClick={onDiagnose}>
                {busy ? <span className="busy" /> : null} Run the diagnosis
              </button>
              <p className="tiny faint" style={{ marginTop: 8 }}>
                Phase 7 puts a live model in this seat, choosing the sequence as the numbers
                come back. What runs today is the recorded sequence with the evidence
                recomputed.
              </p>
            </>
          ) : (
            <>
              <p className="small muted">
                No recorded diagnosis exists for this round, and there is no live model in
                this build to write one — that is phase 7. What you can do is what the agent
                does first: run the tests. Each is read-only, each returns numbers and never
                a verdict, and none of them can write project state.
              </p>
              <div className="row wrap" style={{ marginTop: 10 }}>
                {DIAGNOSTICS.map((d) => (
                  <button key={d.label} className="btn small" disabled={busy}
                          onClick={() => onDiagnostic(d.test, d.args)}>
                    {d.label}
                  </button>
                ))}
              </div>
              <p className="tiny faint" style={{ marginTop: 8 }}>
                Composing what they say into a recommendation a person can rule on is the
                part a pipeline cannot do, and it is the part phase 7 puts a model in.
                Until then this round stays open, which is the correct state for it.
              </p>
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
            <i>if_wrong</i> line are in the Decision tab — that field is the one a sceptical
            scientist reads first, and the writer refuses a record without it.
          </p>
        </Turn>
      )}

      {decision && decision.status === "open" && (
        <Turn who="you">
          <p className="small muted">
            No action is taken until a named person rules. Four verbs, each bound to a code
            path.
          </p>
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
          {verdict === "more_evidence_requested" && (
            <p className="tiny faint" style={{ marginTop: 8 }}>
              This is the one beat a pipeline cannot imitate, because what happens next
              depends on what you asked for. The second pass lands in phase 7.
            </p>
          )}
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

      <div className="composer" style={{ marginTop: 20 }}>
        <textarea className="field" rows={2} disabled
                  placeholder="Ask about this round…" />
        <p className="tiny faint" style={{ margin: "6px 0 0" }}>
          The composer is here because the host has one, and the decision deliberately does
          not go through it. Claude Science's approval primitive is an untyped chat
          interrupt; the panel above is four verbs bound to code paths, with hashed evidence
          and an <i>if_wrong</i> line. The composer itself is wired up in phase 7.
        </p>
      </div>
    </div>
  );
}
