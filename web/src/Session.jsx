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
// with the date it is expected.
//
// **The agent sits in this column, and only its turns carry a badge.** A
// flagged round is diagnosed by a model in the centre seat when one is
// available, or by stepping the committed record through the same stream
// with every test re-run here, and the badge over the turn says which.
// Everything else in the column — what ran, what came back, what the record
// says — is the workbench's own prose, with nothing over it. Your side is
// the bubble on the right: what you asked, and how you ruled. The four verbs
// stay outside the composer; `more_evidence_requested` hands the work back
// to whichever source produced the pass being ruled on.
//
// What the turns say is what ran and what came back. They do not say why the
// interface is shaped the way it is; that reasoning lives here and in
// DECISIONS.md, and a turn that recites it is a turn in the way of the round.

import { useEffect, useState } from "react";
import AgentStream, { agentBadge } from "./AgentStream.jsx";
import Briefing from "./Briefing.jsx";
import Composer from "./Composer.jsx";
import Tool from "./Tool.jsx";
import Turn from "./Turn.jsx";
import { recordedPushback } from "./agent.js";
import {
  ACTION_LABEL, Badge, CentreHead, Hash, VERBS, dayMonth, n, pct, signed,
} from "./lib.jsx";

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

/** A live question and its answer, as the composer's free text produces them. */
function AskTurn({ turn, log, live, ctx }) {
  return (
    <>
      <Turn who="you"><p>{turn.label || turn.question}</p></Turn>
      <Turn who="claude" badge={agentBadge(turn)}>
        <AgentStream turn={turn} log={log} live={live} ctx={ctx} />
      </Turn>
    </>
  );
}

export default function Session({ ctx, stored, suggestions }) {
  const {
    view, round, roundView, decision, log, busy, error, sessionId,
    onApprove, onDiagnostic, onRule, onAdvance, onContinue,
    onAsk, onDownload, drops,
    live, model, setModel, agentTurn, agentBusy, hasReplay, proposal,
    onDiagnoseLive, onReplay, onPushbackLive, onAskLive,
  } = ctx;
  const [verdict, setVerdict] = useState(null);
  const [note, setNote] = useState("");
  const [request, setRequest] = useState(view.objectives.diagnostics[4]);
  const [by, setBy] = useState("d.webster");

  const stage = roundView.status;
  const lab = roundView.lab;
  const canLive = !!(live && live.live);

  // The agent turns stored in this session, with the one in flight taking the
  // place of its stored copy. Diagnoses are placed by pass; asks in order.
  const storedTurns = stored?.turns || [];
  const agentTurns = storedTurns
    .filter((t) => t.kind === "agent")
    .map((t) => (agentTurn && agentTurn.id === t.id ? agentTurn : t));
  if (agentTurn && !agentTurns.some((t) => t.id === agentTurn.id)) agentTurns.push(agentTurn);
  const diagnoses = agentTurns.filter((t) => t.task === "diagnose");
  const agentNs = new Set(agentTurns.flatMap((t) => t.steps.filter((s) => s.type === "tool")
    .map((s) => s.n)));
  const lastDiagnosis = diagnoses[diagnoses.length - 1] || null;

  // Every command this round ran, in the order it ran, split at the moments
  // that matter: the submission, the arrival, the proposal, the ruling.
  const mine = log.filter((e) => e.round === round);
  const submittedAt = mine.find((e) => e.tool === "submit")?.n ?? Infinity;
  const importedAt = mine.find((e) => e.tool === "import_round")?.n ?? Infinity;
  const proposals = mine.filter((e) => e.tool === "record_decision"
    && e.command.includes("--propose"));
  const rulings = mine.filter((e) => e.tool === "record_decision" && e.command.includes("--rule"));
  const lastRuledAt = rulings.length ? rulings[rulings.length - 1].n : Infinity;

  const selectionSteps = mine.filter((e) =>
    ["generate_candidates", "select_batch"].includes(e.tool) && e.n < submittedAt
    && !e.command.includes("--approved-by"));
  const sendSteps = mine.filter((e) => e.n >= submittedAt - 1 && e.n <= submittedAt + 1
    && ["select_batch", "submit", "export"].includes(e.tool));
  const arriveSteps = mine.filter((e) => e.n >= importedAt - 2 && e.n <= importedAt + 1
    && ["status", "pull", "import_round", "evaluate_prior"].includes(e.tool) && !e.refused);
  // Tests run by hand, from the buttons, rather than by an agent turn.
  const manualSteps = mine.filter((e) =>
    (e.tool === "run_diagnostic" || e.kind === "adhoc") && !agentNs.has(e.n));
  const afterSteps = mine.filter((e) => e.n > lastRuledAt && e.n !== Infinity
    && !["run_diagnostic", "record_decision"].includes(e.tool) && e.kind !== "adhoc");

  // Every ask made in this session, read back from it. The ones that asked
  // the laboratory are rendered where they happened rather than at the
  // bottom, because each *is* a call to the registry: a check logs a status
  // and a pull, so the i-th refused ask made the i-th refused pull and the
  // status just before it, and the ask that succeeded made the pull that
  // imported. The rest sit at the end of the stream, in the order asked.
  const turns = storedTurns.filter((t) => t.kind !== "agent");
  const arrival = [...turns].reverse().find((t) => t.answer.kind === "arrival"
    && t.answer.ready);
  const refusedAsks = turns.filter((t) => t.answer.kind === "arrival" && !t.answer.ready);
  const refusedPulls = mine.filter((e) => e.tool === "pull" && e.refused);
  const refusedSteps = refusedAsks.map((t, i) => {
    const pull = refusedPulls[i];
    return pull ? mine.filter((e) => (e.n === pull.n - 1 && e.tool === "status")
      || e.n === pull.n) : [];
  });
  // Registry calls no ask in this session accounts for: a round checked from
  // another session, or from the harness.
  const placed = new Set([...refusedSteps.flat(), ...arriveSteps].map((e) => e.n));
  const waitSteps = mine.filter((e) => (e.tool === "status"
    || (e.tool === "pull" && e.refused)) && !placed.has(e.n));
  const tail = storedTurns
    .filter((t) => t !== arrival && !refusedAsks.includes(t)
      && !(t.kind === "agent" && t.task === "diagnose"))
    .map((t) => (agentTurn && agentTurn.id === t.id ? agentTurn : t));
  if (agentTurn && agentTurn.task !== "diagnose" && !tail.some((t) => t.id === agentTurn.id)) {
    tail.push(agentTurn);
  }

  // The recorded push-back, when the ruling is being made on a replayed pass:
  // the request is the recorded one, because the replay can only answer that.
  const passes = decision?.passes || [];
  const openPass = passes.length && !passes[passes.length - 1].ruling
    ? passes[passes.length - 1] : null;
  const replaying = !!(lastDiagnosis && lastDiagnosis.mode === "replay");
  const recorded = openPass && hasReplay ? recordedPushback(proposal, openPass.pass) : null;
  const lockedRequest = replaying && !canLive && recorded ? recorded.requested : null;
  useEffect(() => {
    if (lockedRequest) setRequest(lockedRequest);
  }, [lockedRequest]);
  // Follow the stream while a turn is in flight, as the host's column does.
  useEffect(() => {
    if (!agentTurn) return;
    const el = document.querySelector(".centre");
    if (el) el.scrollTop = el.scrollHeight;
  }, [agentTurn]);
  useEffect(() => {
    if (verdict === "more_evidence_requested" && recorded && !note && replaying && !canLive) {
      setNote(recorded.note || "");
    }
  }, [verdict, recorded, note, replaying, canLive]);

  const rule = async () => {
    const req = verdict === "more_evidence_requested" ? request : null;
    const rec = await onRule(verdict, by, note, req);
    setVerdict(null);
    setNote("");
    if (!rec || rec.status !== "awaiting_evidence") return;
    // The push-back: the work goes back to whichever source made the pass. A
    // live one continues the session's transcript when the page still holds it.
    const prior = lastDiagnosis;
    const ruling = { verdict: "more_evidence_requested", by, note, requested: req };
    if (canLive && (!prior || prior.mode === "live" || !hasReplay)) {
      onPushbackLive(ruling);
    } else if (hasReplay) {
      const next = (proposal.passes || []).find((p) => p.pass === rec.n_passes + 1);
      if (next && next.answering === req) onReplay(next.pass);
      else if (canLive) onPushbackLive(ruling);
    }
  };

  const Chips = ({ entries }) => entries.map((e) => <Tool key={e.n} entry={e} />);

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
            <Chips entries={selectionSteps} />
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
            <Chips entries={sendSteps} />
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

        {refusedAsks.map((t, i) => (
          <div key={`refused-${i}`}>
            <Turn who="you"><p>{t.question}</p></Turn>
            {refusedSteps[i].length > 0 && (
              <Turn who="workbench"><Chips entries={refusedSteps[i]} /></Turn>
            )}
            <Turn who="workbench"><Briefing data={t.answer} ctx={ctx} /></Turn>
          </div>
        ))}

        {waitSteps.length > 0 && (
          <Turn who="workbench">
            <p className="small">Asked the registry. Not back yet.</p>
            <Chips entries={waitSteps} />
          </Turn>
        )}

        {roundView.at_lab && refusedAsks.length === 0 && (
          <Turn who="workbench">
            <p>
              {waitSteps.length
                ? "Ask again when you think it has had time."
                : "Nothing to do until it reports."}
            </p>
          </Turn>
        )}

        {/* The answer to the ask, where the ask landed. If nobody asked -- a
            round imported before this session was opened -- the round's own
            record says the same thing, from the snapshot rather than from a
            turn. Never both. */}
        {arrival && <Turn who="you"><p>{arrival.question}</p></Turn>}

        {arriveSteps.length > 0 && (
          <Turn who="workbench">
            <p className="small">
              Pulled, reconciled against the designs we submitted, and scored against what
              the model predicted for them.
            </p>
            <Chips entries={arriveSteps} />
          </Turn>
        )}

        {arrival && <Turn who="workbench"><Briefing data={arrival.answer} ctx={ctx} /></Turn>}

        {arriveSteps.length > 0 && !arrival && (
          <Turn who="workbench">
            {roundView.reconciliation && (
              <p>
                They are back. {roundView.reconciliation.rows} rows,{" "}
                {roundView.reconciliation.n_failed} well
                {roundView.reconciliation.n_failed === 1 ? "" : "s"} failed,{" "}
                {roundView.reconciliation.n_censored} value
                {roundView.reconciliation.n_censored === 1 ? "" : "s"} censored below the
                detection limit, {roundView.reconciliation.n_ok} of{" "}
                {roundView.reconciliation.designs} designs reconciled. Replicates came back as
                separate rows and were averaged over usable reads only.
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

        {/* A flagged round with no diagnosis yet: the choice of who diagnoses
            it. A model when one is seated; the record when there is one to
            step; the five tests by hand otherwise. */}
        {roundView.flagged && !decision && !lastDiagnosis && (
          <Turn who="workbench">
            <p>
              Two readings fit this first look and they take opposite actions: the assay moved,
              or the designs really are worse than predicted. The shared designs are the same
              molecules measured twice, and they are where telling them apart starts.
            </p>
            <div className="row wrap" style={{ marginTop: 10 }}>
              {canLive && (
                <button className="btn primary" disabled={busy} onClick={onDiagnoseLive}>
                  {busy ? <span className="busy" /> : null} Diagnose round {round}
                </button>
              )}
              {hasReplay && (
                <button className={`btn${canLive ? "" : " primary"}`} disabled={busy}
                        onClick={() => onReplay(1)}>
                  {busy && !canLive ? <span className="busy" /> : null} Replay the recorded diagnosis
                </button>
              )}
            </div>
            {!canLive && !hasReplay && (
              <div className="row wrap" style={{ marginTop: 10 }}>
                {DIAGNOSTICS.map((d) => (
                  <button key={d.label} className="btn small" disabled={busy}
                          onClick={() => onDiagnostic(d.test, d.args)}>
                    {d.label}
                  </button>
                ))}
              </div>
            )}
            {!canLive && hasReplay && (
              <p className="tiny faint" style={{ marginTop: 8 }}>
                Live session unavailable — {(live && live.reason) || "no function reachable"}.
              </p>
            )}
          </Turn>
        )}

        {manualSteps.length > 0 && (
          <Turn who="workbench"><Chips entries={manualSteps} /></Turn>
        )}

        {/* The passes, in order: who diagnosed, the writer recording it, and
            who ruled. A pass in flight, or one that stopped before the writer
            recorded it, renders after the passes the record holds. */}
        {[
          ...passes.map((p, i) => ({ p, i, passNo: p.pass,
            turn: [...diagnoses].reverse().find((t) => Number(t.pass) === p.pass) || null })),
          ...diagnoses.filter((t) => Number(t.pass) > passes.length)
            .map((turn, k) => ({ p: null, i: passes.length + k, passNo: turn.pass, turn })),
        ].map(({ p, i, passNo, turn }) => {
          const streaming = !!(turn && agentTurn && turn.id === agentTurn.id);
          const chip = p ? proposals[i] : null;
          return (
            <div key={`${passNo}-${turn ? turn.id : "record"}`}>
              {turn && (
                <Turn who="claude" badge={agentBadge(turn)}>
                  <AgentStream turn={turn} log={log} live={streaming} ctx={ctx} />
                </Turn>
              )}
              {p && (
                <Turn who="workbench">
                  {chip && <Tool entry={chip} />}
                  <p>
                    {p.hypotheses.length} hypotheses, each resting on a named test from the
                    template's list.
                  </p>
                  <ul className="small" style={{ paddingLeft: 18, margin: "0 0 10px" }}>
                    {p.hypotheses.map((h) => (
                      <li key={h.id} style={{ marginBottom: 3 }}>
                        <b className="mono">{h.id}</b> {h.claim}{" "}
                        <Badge kind={h.reading === "supported" ? "ok"
                          : h.reading === "partially supported" ? "flag" : ""}>{h.reading}</Badge>
                      </li>
                    ))}
                  </ul>
                  <p>
                    Recommendation: <b>{ACTION_LABEL[p.recommendation.action]}</b>, confidence{" "}
                    {p.recommendation.confidence}. The rationale, the alternatives and the{" "}
                    <i>if_wrong</i> line are in the Decision tab.
                  </p>
                </Turn>
              )}
              {p && p.ruling && (
                <>
                  <Turn who="you">
                    <p>
                      <b>{p.ruling.verdict.replace(/_/g, " ")}</b> by {p.ruling.by}
                      {p.ruling.requested && <> — run <span className="mono">
                        {p.ruling.requested.diagnostic}</span></>}.
                      {p.ruling.note && <> “{p.ruling.note}”</>}
                    </p>
                  </Turn>
                  {rulings[i] && <Turn who="workbench"><Tool entry={rulings[i]} /></Turn>}
                </>
              )}
            </div>
          );
        })}

        {decision && decision.status === "awaiting_evidence" && !agentBusy
          && !diagnoses.some((t) => Number(t.pass) === decision.n_passes + 1
                                    && t.status !== "stopped") && (
          <Turn who="workbench">
            <p className="small">
              Waiting on {decision.ruling?.requested?.diagnostic}.
            </p>
            <div className="row wrap">
              {canLive && (
                <button className="btn primary" disabled={busy}
                        onClick={() => onPushbackLive({
                          verdict: "more_evidence_requested", by: decision.ruling.by,
                          note: decision.ruling.note,
                          requested: decision.ruling.requested.diagnostic,
                        })}>
                  Answer it live
                </button>
              )}
              {hasReplay && (proposal.passes || []).some((x) => x.pass === decision.n_passes + 1
                && x.answering === decision.ruling.requested.diagnostic) && (
                <button className="btn" disabled={busy}
                        onClick={() => onReplay(decision.n_passes + 1)}>
                  Replay the recorded answer
                </button>
              )}
            </div>
          </Turn>
        )}

        {decision && decision.status === "open" && !agentBusy && (
          <Turn who="workbench">
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
                {lockedRequest ? (
                  <span className="mono small" title="the recorded push-back; a live session could ask for any test">
                    {lockedRequest} <span className="faint">· recorded</span>
                  </span>
                ) : (
                  <select className="field" style={{ width: "auto" }} value={request}
                          onChange={(e) => setRequest(e.target.value)}>
                    {view.objectives.diagnostics.map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                )}
              </div>
            )}
            <textarea className="field" style={{ marginTop: 10 }} rows={2}
                      placeholder="your reason, your modification, or your ask"
                      value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="row" style={{ marginTop: 10 }}>
              <input className="field" style={{ width: 150 }} value={by}
                     onChange={(e) => setBy(e.target.value)} aria-label="ruling by" />
              <button className="btn primary" disabled={!verdict || busy} onClick={rule}>
                {busy ? <span className="busy" /> : null} Rule
              </button>
            </div>
          </Turn>
        )}

        {decision && decision.status === "ruled" && stage === "flagged, ruled" && !roundView.model && (
          <Turn who="workbench">
            <button className="btn primary" disabled={busy} onClick={onAdvance}>
              {busy ? <span className="busy" /> : null} Act on the ruling and propose round{" "}
              {round + 1}
            </button>
          </Turn>
        )}

        {afterSteps.length > 0 && (
          <Turn who="workbench">
            <Chips entries={afterSteps} />
            {roundView.frame?.offset_applied ? (
              <p>
                The frame moved by{" "}
                <span className="num">{signed(roundView.frame.offset_applied)}</span> pKD under
                authority <span className="mono">{roundView.frame.authority}</span>;{" "}
                <span className="mono">import_round.py</span> checked that record before it
                moved anything.
              </p>
            ) : null}
          </Turn>
        )}

        {tail.map((t, i) => (
          t.kind === "agent"
            ? <AskTurn key={t.id || i} turn={t} log={log}
                       live={!!(agentTurn && agentTurn.id === t.id)} ctx={ctx} />
            : (
              <div key={i}>
                <Turn who="you"><p>{t.question}</p></Turn>
                <Turn who="workbench"><Briefing data={t.answer} ctx={ctx} /></Turn>
              </div>
            )
        ))}

        <Composer suggestions={suggestions} busy={busy}
                  live={live} model={model} setModel={setModel}
                  placeholder={`Ask about round ${round}…`}
                  onAsk={(key, forRound) => onAsk(key, forRound, sessionId)}
                  onSend={(text, chosen, label) => onAskLive(text, chosen, label)} />
      </div>
    </>
  );
}
