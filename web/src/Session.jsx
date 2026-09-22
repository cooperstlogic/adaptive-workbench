// The centre column for a round session.
//
// A session is a unit of work; this is the kind a round starts. What the
// conversation produces is a typed decision rather than prose, and two things
// are deliberately visible. The **tool calls are real**: every chip below is
// a command that ran against your copy of the project in this browser, with
// the output it printed. And the **ruling is not in the composer**: decisions
// are buttons, questions are asks.
//
// **The column is one stream, in the order things happened.** Every block is
// anchored to the command log: what the workbench says about a submission
// sits at the submit command's `n`, an ask sits at the log's length when it
// was asked (`after_n`, stamped by the driver on every kind of turn), and the
// one thing still pending -- the approval, the lab control, the ruling -- is
// always last, directly above the composer. Nothing renders above something
// that happened before it. Your own actions are bubbles on the right, where
// they happened, the way the record shows an approval for a round that ran
// elsewhere; the button that took the action is gone and the bubble is what
// is left of it.
//
// **The round goes to a laboratory on the way through.** Approving signs the
// batch, submits it and writes the order file the lab would receive — and
// then stops. Whether the results are back is a separate call to the
// registry, a button beside the lab control rather than a question in the
// composer because the model cannot reach the registry; it is refused the
// first time with the date it is expected, and the answer is the briefing
// the driver assembles from what came back.
//
// **The agent sits in this column, and only its turns carry a badge.** A
// flagged round is diagnosed by a model in the centre seat when one is
// available, or by stepping the committed record through the same stream
// with every test re-run here, and the badge over the turn says which.
// Everything else in the column — what ran, what came back, what the record
// says — is the workbench's own prose, with nothing over it. Your side is
// the bubble on the right: what you asked, what you approved, and how you
// ruled. The four verbs stay outside the composer; `more_evidence_requested`
// hands the work back to whichever source produced the pass being ruled on.
//
// What the turns say is what ran and what came back. They do not say why the
// interface is shaped the way it is; that reasoning lives here and in
// README.md, and a turn that recites it is a turn in the way of the round.

import { Fragment, useEffect, useState } from "react";
import AgentStream, { agentBadge } from "./AgentStream.jsx";
import Briefing from "./Briefing.jsx";
import Composer from "./Composer.jsx";
import History from "./History.jsx";
import Tool from "./Tool.jsx";
import Turn from "./Turn.jsx";
import { recordedPushback } from "./agent.js";
import {
  ACTION_LABEL, Badge, CentreHead, Hash, PanelToggle, RailToggle, VERBS, dayMonth, n, pct,
  signed,
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

// What each verb takes once it is pressed, and what its button says gets
// recorded. `record_decision.py --rule` refuses a modification or a rejection
// with no note, so those two wait for one; a push-back is named for its test.
const RULING = {
  accepted: { ask: "a note for the record, optional", commit: "Accept the recommendation" },
  accepted_with_modification: { ask: "what changes", required: true,
                                commit: "Accept with this modification" },
  more_evidence_requested: { ask: "why, optional" },
  rejected: { ask: "why — the agent works from this next", required: true,
              commit: "Reject the recommendation" },
};

// What the word beside the lab control means, as a tooltip and nowhere else.
// The button moves the simulated laboratory's clock; it moves nothing else,
// and the sentence that says so belongs here rather than on the page.
const LAB_TIP =
  "The laboratory is an oracle replaying a generated landscape. This says the assay has "
  + "finished, now, instead of on the date the registry named; the values were measured "
  + "when the batch was submitted and do not change.";

// Where a block sits in the stream when no command anchors it. The record of
// a round that ran elsewhere is before anything this tab logged; a turn
// stored without a position is after everything it logged; and what is
// pending is last of all. Log positions are the entries' `n`, from 1.
const PAST = -1;
const LATE = Number.MAX_SAFE_INTEGER;
const NOW = Infinity;

/** What an amendment would move, and what it costs. Numbers from the writer. */
function Amendment({ am }) {
  return (
    <p>
      And asks to move <span className="mono">{am.field}</span> from{" "}
      <span className="num">{am.from}</span> to <span className="num">{am.to}</span>:{" "}
      {am.why}{" "}
      <span className="faint small">
        {am.effects.pool_changes
          ? `${am.effects.feasible_before.toLocaleString()} feasible candidates would become `
            + am.effects.feasible_after.toLocaleString()
          : `${am.effects.fresh_picks} of the batch's wells would go to fresh designs`}
        , and it is bounded {am.bounds.low}–{am.bounds.high}.
      </span>
    </p>
  );
}

/** A live question and its answer, as the composer's free text produces them. */
function AskTurn({ turn, log, live, ctx }) {
  return (
    <>
      <Turn who="you"><p title={turn.label ? turn.question : undefined}>{turn.label || turn.question}</p></Turn>
      <Turn who="claude" badge={agentBadge(turn)}>
        <AgentStream turn={turn} log={log} live={live} ctx={ctx} />
      </Turn>
    </>
  );
}

export default function Session({ ctx, stored, history }) {
  const {
    view, round, roundView, decision, log, busy, acting, error, sessionId, batch,
    onApprove, onDiagnostic, onRule, onAdvance, onContinue, onRelease,
    onAsk, onDownload, drops,
    live, model, setModel, agentTurn, agentBusy, hasReplay, proposal,
    onDiagnoseLive, onReplay, onPushbackLive, onAskLive,
  } = ctx;
  const [verdict, setVerdict] = useState(null);
  const [note, setNote] = useState("");
  const [amendTo, setAmendTo] = useState("");
  const [request, setRequest] = useState(view.objectives.diagnostics[4]);

  const stage = roundView.status;
  const lab = roundView.lab;
  const canLive = !!(live && live.live);
  // A spinner sits on the button whose command is running and on no other.
  // The agent's is the stream's own indicator, so its buttons only spin for
  // the instant before the turn is in the column.
  const spin = (name) => (acting === name ? <span className="busy" /> : null);
  const starting = agentBusy && !agentTurn ? <span className="busy" /> : null;
  // A round this browser ran has a log, and the log is the story. A round
  // that ran before the tab was opened has none, and its artifacts are.
  const ranHere = log.some((e) => e.round === round);
  const record = ranHere ? null : history;

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
  // The arrival's commands, unless an agent turn is already showing them:
  // `check_lab_results` runs the same four and renders them in its own turn.
  const arriveSteps = mine.filter((e) => e.n >= importedAt - 2 && e.n <= importedAt + 1
    && ["status", "pull", "import_round", "evaluate_prior"].includes(e.tool) && !e.refused
    && !agentNs.has(e.n));
  const importedHere = mine.some((e) => e.tool === "import_round");
  // The clock, moved by hand. It is a command like any other and it shows as
  // one, under the bubble that asked for it.
  const releaseSteps = mine.filter((e) => e.tool === "release");
  // Tests run by hand, from the buttons, rather than by an agent turn.
  const manualSteps = mine.filter((e) =>
    (e.tool === "run_diagnostic" || e.kind === "adhoc") && !agentNs.has(e.n));
  // What ran once the round was settled: after the last ruling, or after the
  // arrival's own scoring when nothing was ruled. Either way it is the fit
  // and whatever the ruling authorized before it.
  const settledAt = rulings.length ? lastRuledAt : importedAt + 1;
  const afterSteps = mine.filter((e) => e.n > settledAt && e.n !== Infinity
    && !["run_diagnostic", "record_decision"].includes(e.tool) && e.kind !== "adhoc");

  // Every ask made in this session, read back from it. The ones that asked
  // the laboratory carry the registry's chips with them, because each *is* a
  // call to the registry: a check logs a status and a pull, so the i-th
  // refused ask made the i-th refused pull and the status just before it,
  // and the ask that succeeded made the pull that imported.
  const turns = storedTurns.filter((t) => t.kind !== "agent");
  const arrival = [...turns].reverse().find((t) => t.answer.kind === "arrival"
    && t.answer.ready);
  const refusedAsks = turns.filter((t) => t.answer.kind === "arrival" && !t.answer.ready);
  const refusedPulls = mine.filter((e) => e.tool === "pull" && e.refused && !agentNs.has(e.n));
  const refusedSteps = refusedAsks.map((t, i) => {
    const pull = refusedPulls[i];
    return pull ? mine.filter((e) => (e.n === pull.n - 1 && e.tool === "status")
      || e.n === pull.n) : [];
  });
  // Registry calls no ask in this session accounts for: a round checked from
  // another session, or from the harness.
  const placed = new Set([...refusedSteps.flat(), ...arriveSteps].map((e) => e.n));
  const waitSteps = mine.filter((e) => (e.tool === "status"
    || (e.tool === "pull" && e.refused)) && !placed.has(e.n) && !agentNs.has(e.n));
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
  // Follow the stream: while a turn is in flight, as the host's column does,
  // and when a command lands, because what it produced is at the end.
  useEffect(() => {
    const el = document.querySelector(".centre");
    if (el) el.scrollTop = el.scrollHeight;
  }, [agentTurn, log.length]);
  useEffect(() => {
    if (verdict === "more_evidence_requested" && recorded && !note && replaying && !canLive) {
      setNote(recorded.note || "");
    }
  }, [verdict, recorded, note, replaying, canLive]);

  // The amendment the open recommendation proposes, if it proposes one. It is
  // the only thing a ruling carries a number for, and the number starts where
  // the agent put it: pressing *accept with modification* is how you move it,
  // so the field is pre-filled with what would happen if you did not.
  const amendment = openPass ? (openPass.recommendation || {}).amendment : null;
  useEffect(() => {
    if (amendment) setAmendTo(String(amendment.to));
  }, [amendment && amendment.field, amendment && amendment.to]);
  const amendDialled = !!amendment && verdict === "accepted_with_modification"
    && amendTo.trim() !== "" && Number(amendTo) !== amendment.to;
  const amendValid = !amendment || verdict !== "accepted_with_modification"
    || amendTo.trim() === "" || (Number.isFinite(Number(amendTo))
      && Number(amendTo) >= amendment.bounds.low && Number(amendTo) <= amendment.bounds.high);

  const ready = !!verdict && !(RULING[verdict].required && !note.trim()) && amendValid;
  const rule = async () => {
    const req = verdict === "more_evidence_requested" ? request : null;
    const rec = await onRule(verdict, note, req, amendDialled ? Number(amendTo) : null);
    setVerdict(null);
    setNote("");
    if (!rec || rec.status !== "awaiting_evidence") return;
    // The push-back: the work goes back to whichever source made the pass. A
    // live one continues the session's transcript when the page still holds it.
    const prior = lastDiagnosis;
    const ruling = { verdict: "more_evidence_requested", by: rec.ruling.by, note,
                     requested: req };
    if (canLive && (!prior || prior.mode === "live" || !hasReplay)) {
      onPushbackLive(ruling);
    } else if (hasReplay) {
      const next = (proposal.passes || []).find((p) => p.pass === rec.n_passes + 1);
      if (next && next.answering === req) onReplay(next.pass);
      else if (canLive) onPushbackLive(ruling);
    }
  };

  const Chips = ({ entries }) => entries.map((e) => <Tool key={e.n} entry={e} />);

  /* the stream --------------------------------------------------------------
     Each block goes in with the log position it belongs to, and the list is
     sorted once. A command sits at its `n`. A turn sits just after the entry
     it was made after. A bubble that caused a command sits just before that
     command -- and after any turn made in the same gap, because a question
     asked while a batch waited was asked before the batch was approved. A
     block with no anchor keeps the order it is added in. The sort is stable. */
  const items = [];
  const put = (at, key, node) => items.push({ at, key, node });
  const turnAt = (t) => (t.after_n == null ? LATE : t.after_n + 0.5);
  const before = (n) => n - 0.25;
  const askAt = (t, chips) => (chips && chips.length ? before(chips[0].n) : turnAt(t));

  put(PAST, "history-before",
      <History history={record} phase="before" ctx={ctx}
               reads={!record?.steps.some((x) => x.phase === "after")} />);

  // The proposal stays in the stream once it is approved, because the bubble
  // that approved it needs something to answer; the hash is quoted only while
  // the batch is unsigned, since signing changes it. A round whose record
  // came from elsewhere has the same sentence from History instead.
  //
  // A seed round gets the sentence History gives it, for the same reason: it
  // came from the template's policy and not from a fit, so there is no model
  // to name and no round before it to have fit -- and its composition is
  // three zeroes and a total, because `seed_batch` fills every slot with a
  // pick.
  const pending = stage === "awaiting approval";
  const fromRecord = !!(record && record.steps.length);
  if (roundView.batch && !fromRecord && (pending || sendSteps.length > 0)) {
    const proposed = pending ? "has proposed" : "proposed";
    const hashed = pending && (
      <> Unsigned, it hashes to <Hash value={roundView.batch.hash} />.</>
    );
    put(selectionSteps.length ? selectionSteps[0].n : PAST, "proposed", (
      <Turn who="workbench">
        {roundView.batch.mode === "seed" ? (
          <p>
            Round {round} {pending ? "has" : "had"} no fit to select from, so the optimizer{" "}
            {proposed} {roundView.batch.n} wells from the template's{" "}
            <span className="mono">{batch?.policy?.round1_policy || "seed"}</span> policy,
            all of them fresh picks.{hashed}
          </p>
        ) : (
          <p>
            The optimizer {proposed} {roundView.batch.n} wells for
            round {round} — {roundView.batch.composition.control} control,{" "}
            {roundView.batch.composition.replicate} replicate,{" "}
            {roundView.batch.composition.exploration} exploration and{" "}
            {roundView.batch.composition.pick} fresh picks — from the{" "}
            {roundView.batch.model_winner} fit of round {round - 1}.{hashed}
          </p>
        )}
        {(batch?.policy_overrides || []).length > 0 && (
          // The batch on screen is not the one the declaration would have
          // produced, so the line that describes it says so and says what was
          // asked for instead.
          <p className="small">
            Re-composed on request:{" "}
            {batch.policy_overrides.map((o) => (
              <span key={o.field}>
                <span className="mono">{o.field}</span>{" "}
                <span className="num">{o.from}</span> → <span className="num">{o.to}</span>
              </span>
            )).reduce((a, b) => [a, ", ", b])}
            {batch.policy_overrides[0].note && <> — “{batch.policy_overrides[0].note}”</>}.
            This batch only; <span className="mono">objectives.json</span> is unchanged.
          </p>
        )}
        <Chips entries={selectionSteps} />
      </Turn>
    ));
  }
  if (pending) {
    put(NOW, "approve", (
      <Turn who="workbench">
        <p className="small muted">
          Review it in the Batch tab; strike anything you do not want and the override is
          recorded with your note. Approving submits the batch and writes the lab's order.
        </p>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn primary" disabled={busy} onClick={onApprove}>
            {spin("approve")}
            {drops.length
              ? `Approve ${roundView.batch.n - drops.length} of ${roundView.batch.n} wells`
              : `Approve and send ${roundView.batch.n} wells`}
          </button>
        </div>
      </Turn>
    ));
  }

  if (sendSteps.length > 0) {
    // The approval, as the record holds it: whether it was signed, and what was
    // struck. Who signed is in the record and on the Batch tab; a turn on the
    // right is yours and does not name you.
    const approval = roundView.batch?.approval || {};
    const overrides = batch?.overrides || [];
    put(before(sendSteps[0].n), "approved", (
      <Turn who="you">
        <p>
          {approval.status === "approved"
            ? `Approve and send ${roundView.batch.n} wells`
            : `Submit ${roundView.batch.n} wells unreviewed`}
          {overrides.length > 0 && `, striking ${overrides.length}`}
        </p>
      </Turn>
    ));
    put(sendSteps[0].n, "sent", (
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
    ));
  }

  refusedAsks.forEach((t, i) => put(askAt(t, refusedSteps[i]), `refused-${i}`, (
    <>
      <Turn who="you"><p>{t.question}</p></Turn>
      {refusedSteps[i].length > 0 && (
        <Turn who="workbench"><Chips entries={refusedSteps[i]} /></Turn>
      )}
      <Turn who="workbench"><Briefing data={t.answer} ctx={ctx} /></Turn>
    </>
  )));

  if (waitSteps.length > 0) {
    put(waitSteps[0].n, "wait", (
      <Turn who="workbench">
        <p className="small">Asked the registry. Not back yet.</p>
        <Chips entries={waitSteps} />
      </Turn>
    ));
  }

  // The registry check: the one call in this column that is not a decision.
  // It is a button because the model cannot make it, and it is the same
  // `ask` the driver answers with a briefing, so the turn it leaves is a
  // question and its answer.
  const askRegistry = (
    <button className="btn small" disabled={busy}
            onClick={() => onAsk("results_back", round, sessionId)}>
      {spin("ask")} Ask the registry
    </button>
  );

  if (roundView.at_lab) {
    put(NOW, "at-lab", (
      <Turn who="workbench">
        {!(refusedAsks.length || waitSteps.length) && (
          <p>Nothing here moves until the assay reports.</p>
        )}
        <div className="row wrap" style={{ marginTop: 10 }}>
          {askRegistry}
          <button className="btn small" disabled={busy} onClick={onRelease}>
            {spin("release")} Have the lab report now
          </button>
          <span className="tag-syn" title={LAB_TIP}>simulated</span>
        </div>
      </Turn>
    ));
  }

  // The release is a command like any other and stays in the stream once the
  // round has been pulled.
  if (releaseSteps.length > 0) {
    put(before(releaseSteps[0].n), "released", (
      <>
        <Turn who="you"><p>Have the lab report now</p></Turn>
        <Turn who="workbench"><Chips entries={releaseSteps} /></Turn>
      </>
    ));
  }

  // The lab has reported and nobody has pulled it. Before the release control
  // existed this state lasted as long as one call, because the ask that
  // released the round also imported it; now a person can stand in it, and
  // the way out is the same call.
  if (roundView.reported) {
    put(NOW, "reported", (
      <Turn who="workbench">
        <p>
          The registry has round {round}: {lab?.n_rows || 0} rows across{" "}
          {lab?.n_samples || 0} samples on assay {lab?.assay_version}
          {lab?.released_by && <> — reported early, by {lab.released_by}</>}. Nothing is
          imported until it is asked for.
        </p>
        <div className="row wrap" style={{ marginTop: 10 }}>{askRegistry}</div>
      </Turn>
    ));
  }

  // The answer to the ask, where the ask landed. If nobody asked -- a round
  // imported before this session was opened -- the round's own record says
  // the same thing, from the snapshot rather than from a turn. Never both.
  const arriveChips = arriveSteps.length > 0 && (
    <Turn who="workbench">
      <p className="small">
        Pulled, reconciled against the designs we submitted, and scored against what
        the model predicted for them.
      </p>
      <Chips entries={arriveSteps} />
    </Turn>
  );
  if (arrival) {
    put(askAt(arrival, arriveSteps), "arrival", (
      <>
        <Turn who="you"><p>{arrival.question}</p></Turn>
        {arriveChips}
        <Turn who="workbench"><Briefing data={arrival.answer} ctx={ctx} /></Turn>
      </>
    ));
  } else if (arriveSteps.length > 0) {
    put(arriveSteps[0].n, "arrive-steps", arriveChips);
  }

  if (importedHere && !arrival) {
    put(importedAt, "imported", (
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
    ));
  }

  if (stage === "imported" && !roundView.flagged) {
    put(NOW, "continue", (
      <Turn who="workbench">
        <button className="btn primary" disabled={busy} onClick={onContinue}>
          {spin("continue")} Fit round {round} and propose round{" "}
          {round + 1}
        </button>
      </Turn>
    ));
  }

  // A flagged round with no diagnosis yet: the choice of who diagnoses it. A
  // model when one is seated; the record when there is one to step; the
  // five tests by hand otherwise.
  if (roundView.flagged && !decision && !lastDiagnosis) {
    put(NOW, "diagnose", (
      <Turn who="workbench">
        <p>
          Two readings fit this first look and they take opposite actions: the assay moved,
          or the designs really are worse than predicted. The shared designs are the same
          molecules measured twice, and they are where telling them apart starts.
        </p>
        <div className="row wrap" style={{ marginTop: 10 }}>
          {canLive && (
            <button className="btn primary" disabled={busy} onClick={onDiagnoseLive}>
              {starting} Diagnose round {round}
            </button>
          )}
          {hasReplay && (
            <button className={`btn${canLive ? "" : " primary"}`} disabled={busy}
                    onClick={() => onReplay(1)}>
              {canLive ? null : starting} Replay the recorded diagnosis
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
    ));
  }

  if (manualSteps.length > 0) {
    put(manualSteps[0].n, "manual", <Turn who="workbench"><Chips entries={manualSteps} /></Turn>);
  }

  // The passes, in order: who diagnosed, the writer recording it, and who
  // ruled. Each is its own block, so a question asked between the proposal
  // and the ruling sits between them. A pass in flight, or one that stopped
  // before the writer recorded it, comes after the passes the record holds.
  [
    ...passes.map((p, i) => ({ p, i, passNo: p.pass,
      turn: [...diagnoses].reverse().find((t) => Number(t.pass) === p.pass) || null })),
    ...diagnoses.filter((t) => Number(t.pass) > passes.length)
      .map((turn, k) => ({ p: null, i: passes.length + k, passNo: turn.pass, turn })),
  ].forEach(({ p, i, passNo, turn }) => {
    const streaming = !!(turn && agentTurn && turn.id === agentTurn.id);
    const chip = p ? proposals[i] : null;
    const key = `${passNo}-${turn ? turn.id : "record"}`;
    if (turn) {
      put(turnAt(turn), `${key}-turn`, (
        <Turn who="claude" badge={agentBadge(turn)}>
          <AgentStream turn={turn} log={log} live={streaming} ctx={ctx} />
        </Turn>
      ));
    }
    if (!p) return;
    const recordAt = chip ? chip.n : turn ? turnAt(turn) : PAST;
    put(recordAt, `${key}-record`, (
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
        {p.recommendation.amendment && <Amendment am={p.recommendation.amendment} />}
      </Turn>
    ));
    if (p.ruling) {
      put(rulings[i] ? before(rulings[i].n) : recordAt, `${key}-ruling`, (
        <>
          <Turn who="you">
            <p>
              <b>{p.ruling.verdict.replace(/_/g, " ")}</b>
              {p.ruling.requested && <> — run <span className="mono">
                {p.ruling.requested.diagnostic}</span></>}
              {p.ruling.modified && <> — <span className="mono">
                {p.ruling.modified.field}</span> at{" "}
                <span className="num">{p.ruling.modified.to}</span> and not{" "}
                <span className="num">{p.ruling.modified.proposed}</span></>}.
              {p.ruling.note && <> “{p.ruling.note}”</>}
            </p>
          </Turn>
          {rulings[i] && <Turn who="workbench"><Tool entry={rulings[i]} /></Turn>}
        </>
      ));
    }
  });

  if (decision && decision.status === "awaiting_evidence" && !agentBusy
      && !diagnoses.some((t) => Number(t.pass) === decision.n_passes + 1
                                && t.status !== "stopped")) {
    put(NOW, "awaiting-evidence", (
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
    ));
  }

  if (decision && decision.status === "open" && !agentBusy) {
    put(NOW, "verbs", (
      <Turn who="workbench">
        <div className="verbs">
          {VERBS.map((v) => (
            <button key={v.id} className="verb" aria-pressed={verdict === v.id}
                    onClick={() => setVerdict(verdict === v.id ? null : v.id)}>
              <b>{v.label}</b><span>{v.blurb}</span>
            </button>
          ))}
        </div>
        {verdict && (
          // The pressed verb opens one line: what it takes, and a button that
          // says what gets recorded. The line is not there until a verb is,
          // so the only box under the stream at rest is the composer.
          <form className="ruling"
                onSubmit={(e) => { e.preventDefault(); if (ready && !busy) rule(); }}>
            {verdict === "more_evidence_requested" && (lockedRequest ? (
              <span className="mono small"
                    title="the recorded push-back; a live session could ask for any test">
                {lockedRequest} <span className="faint">· recorded</span>
              </span>
            ) : (
              <select className="field" value={request}
                      onChange={(e) => setRequest(e.target.value)}>
                {view.objectives.diagnostics.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            ))}
            {amendment && verdict === "accepted_with_modification" && (
              // The one number a ruling carries. Typed, bounded by what the
              // writer will take, and beside the note rather than inside it,
              // because a modification stated in prose is one no code path
              // can act on.
              <label className="mono small amend">
                {amendment.field}
                <input className="field num-field" type="number" step="any" autoFocus
                       min={amendment.bounds.low} max={amendment.bounds.high}
                       value={amendTo} onChange={(e) => setAmendTo(e.target.value)} />
                <span className="faint">{amendment.bounds.low}–{amendment.bounds.high}</span>
              </label>
            )}
            <input className="field" autoFocus={!(amendment && verdict === "accepted_with_modification")}
                   placeholder={RULING[verdict].ask}
                   value={note} onChange={(e) => setNote(e.target.value)} />
            <button type="submit" className="btn primary" disabled={!ready || busy}>
              {spin("rule")}
              {verdict === "more_evidence_requested"
                ? <>Ask for <span className="mono">{request}</span></>
                : amendment && verdict === "accepted_with_modification" && amendDialled
                  ? <>Accept with <span className="mono">{amendment.field.split(".").pop()}
                    </span> at {amendTo}</>
                  : RULING[verdict].commit}
            </button>
          </form>
        )}
      </Turn>
    ));
  }

  if (decision && decision.status === "ruled" && stage === "flagged, ruled" && !roundView.model) {
    put(NOW, "advance", (
      <Turn who="workbench">
        <button className="btn primary" disabled={busy} onClick={onAdvance}>
          {spin("advance")} Act on the ruling and propose round{" "}
          {round + 1}
        </button>
      </Turn>
    ));
  }

  put(PAST, "history-after", <History history={record} phase="after" ctx={ctx} reads />);

  if (afterSteps.length > 0) {
    // The button that settled the round, as the bubble it left behind.
    put(before(afterSteps[0].n), "acted", (
      <Turn who="you">
        <p>
          {rulings.length
            ? `Act on the ruling and propose round ${round + 1}`
            : `Fit round ${round} and propose round ${round + 1}`}
        </p>
      </Turn>
    ));
    put(afterSteps[0].n, "after", (
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
    ));
  }

  tail.forEach((t, i) => put(
    t.kind === "agent" ? turnAt(t) : askAt(t, []), t.id || `ask-${i}`,
    t.kind === "agent"
      ? <AskTurn turn={t} log={log} live={!!(agentTurn && agentTurn.id === t.id)} ctx={ctx} />
      : (
        <>
          <Turn who="you"><p>{t.question}</p></Turn>
          <Turn who="workbench"><Briefing data={t.answer} ctx={ctx} /></Turn>
        </>
      ),
  ));

  items.sort((a, b) => a.at - b.at);

  return (
    <>
      <CentreHead title={`Round ${round} · ${stage}`}
                  sub={`${view.project.lead.name} ${view.project.lead.chain} → ${
                    view.project.target} · ${view.n_designs} designs · assay ${
                    roundView.assay_version || "not yet run"}`}
                  lead={<RailToggle rail={ctx.rail} lead />}
                  aside={<PanelToggle panel={ctx.panel} />}>
        {roundView.flagged && <Badge kind="flag">flagged</Badge>}
        {roundView.at_lab && <Badge kind="attn">at the lab</Badge>}
      </CentreHead>
      <div className="centre-inner thread">
        {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

        {items.map((it) => <Fragment key={it.key}>{it.node}</Fragment>)}

        <Composer key={sessionId} busy={busy} live={live} model={model} setModel={setModel}
                  placeholder={`Ask about round ${round}…`}
                  onSend={(text, chosen, label) => onAskLive(text, chosen, label)} />
      </div>
    </>
  );
}
