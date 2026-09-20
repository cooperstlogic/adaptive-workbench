// What a round did, read back out of the artifacts it wrote.
//
// The centre column normally renders this browser's command log: every chip
// is something that ran in this tab, with the output it printed. A round that
// ran before the tab was opened has no log here — the shipped campaign's
// first three rounds ran on a laptop six weeks ago — and the column for them
// was a title and a composer. The round was proposed, signed for, ordered,
// returned, scored and fitted, and every one of those moments is in a file
// with a hash; this lays them out.
//
// **It is a record, not a transcript.** No command chip appears here, because
// no command ran in this tab, and nothing in it is written as though someone
// said it. The numbers are the ones the artifacts hold, each resolving in the
// Notebook tab to the `core/` function behind it where there is one — and
// carrying no source where the value was computed inside a pipeline script
// rather than by a function of its own. The files are named at the end.
//
// The one turn on the right is the approval, because a person gave it. The
// record says who, and the Batch tab shows it; the turn is theirs and does
// not name them.

import Turn from "./Turn.jsx";
import { Fig } from "./Briefing.jsx";
import { dayMonth, n, pct, signed } from "./lib.jsx";

const list = (xs) => xs.join(xs.length > 2 ? ", " : " and ");

function Proposed({ s, ctx }) {
  const c = s.composition;
  return (
    <Turn who="workbench">
      {s.mode === "seed" ? (
        <p>
          Round {ctx.round} had no fit to select from, so the batch is the template's{" "}
          <span className="mono">{s.policy || "seed"}</span> policy: {s.n} wells over the
          editable window, out of {s.n_feasible?.toLocaleString()} designs that passed the
          declared constraints of {s.n_enumerated?.toLocaleString()} enumerated.
        </p>
      ) : (
        <p>
          The optimizer proposed {s.n} wells for round {ctx.round} — {c.control} control,{" "}
          {c.replicate} replicate, {c.exploration} exploration and {c.pick} fresh picks —
          from the <span className="mono">{s.model_winner}</span> fit of round{" "}
          {s.from_round}, out of {s.n_feasible?.toLocaleString()} feasible designs.
          {s.incumbent && <> The best observed at selection was{" "}
            <b><Fig fig={s.incumbent} onTrace={ctx.onTrace} /></b>.</>}
        </p>
      )}
    </Turn>
  );
}

function Approved({ s }) {
  return (
    <Turn who="you">
      <p>
        {s.status === "approved"
          ? `Approve and send ${s.n} wells`
          : `Submit ${s.n} wells unreviewed`}
        {s.overrides.length > 0 && `, striking ${s.overrides.length}`}
        {s.note && <> “{s.note}”</>}
      </p>
    </Turn>
  );
}

function Submitted({ s, ctx }) {
  return (
    <Turn who="workbench">
      <p>
        Signed, submitted as <span className="mono">{s.round_id}</span> and ordered. The
        registry minted {s.n_samples} sample ids across{" "}
        {s.plates.length === 1 ? "plate" : "plates"} {list(s.plates)}, on assay{" "}
        {s.assay_version}
        {s.at && <>, {dayMonth(s.at)}</>}.
      </p>
      {s.order && (
        <button className="chip download" onClick={() => ctx.onDownload(s.order)}>
          ↓ round_{String(ctx.round).padStart(3, "0")}_order.csv
          <span className="tiny faint">{s.n_samples} rows · no value column</span>
        </button>
      )}
    </Turn>
  );
}

function Returned({ s }) {
  return (
    <Turn who="workbench">
      <p>
        They came back: {s.rows} rows over {s.samples} samples, {s.n_failed} well
        {s.n_failed === 1 ? "" : "s"} failed, {s.n_censored} value
        {s.n_censored === 1 ? "" : "s"} censored below the detection limit, {s.n_ok} of{" "}
        {s.designs} designs reconciled. Replicates came back as separate rows and were
        averaged over usable reads only.
      </p>
    </Turn>
  );
}

function Scored({ s, ctx }) {
  const r = ctx.round;
  return (
    <Turn who="workbench">
      {!s.scored_against_a_model ? (
        <p>
          Round {r} was chosen without a model, so there was nothing to score it against.
          {s.best && <> Best this round <b><Fig fig={s.best} onTrace={ctx.onTrace} /></b>.</>}
        </p>
      ) : s.flagged ? (
        <p>
          And round {r} <b>flagged</b>. Its {s.n_compared} fresh designs came back a mean{" "}
          <span className="num">{signed(s.statistic.value)}</span> pKD from where the model
          put them, against a trigger of{" "}
          <span className="num">{n(s.trigger.value, 2)}</span>
          {s.coverage && <> and coverage{" "}
            <span className="num">{pct(s.coverage.value, 0)}</span> against a nominal{" "}
            {pct(s.nominal_coverage, 0)}</>}. The assay version is {s.assay_version} and the
          project {s.known_version_offset === null
            ? "had never characterized it" : "had an offset on record for it"}.
        </p>
      ) : (
        <p>
          Round {r} did not flag: mean signed residual{" "}
          <span className="num">{signed(s.statistic.value)}</span> pKD over {s.n_compared}{" "}
          fresh designs, inside the trigger of{" "}
          <span className="num">{n(s.trigger.value, 2)}</span>
          {s.coverage && <>, coverage <span className="num">{pct(s.coverage.value, 0)}</span>{" "}
            against a nominal {pct(s.nominal_coverage, 0)}</>}.
          {s.best && <> Best this round <b><Fig fig={s.best} onTrace={ctx.onTrace} /></b>
            {s.gain && <>, <span className="num">{signed(s.gain.value)}</span> pKD on the
              incumbent</>}.</>}
        </p>
      )}
    </Turn>
  );
}

function Frame({ s }) {
  return (
    <Turn who="workbench">
      <p>
        The frame moved <span className="num">{signed(s.offset.value)}</span> pKD under
        authority <span className="mono">{s.authority}</span>
        {s.n_bridge ? <>, off a {s.n_bridge}-design bridge</> : null}.{" "}
        <span className="mono">import_round.py</span> checked that authority before it moved
        anything.
      </p>
    </Turn>
  );
}

function Fitted({ s, ctx }) {
  const names = Object.keys(s.recipes);
  const loser = names.find((k) => k !== s.winner);
  return (
    <Turn who="workbench">
      <p>
        Fitted on {s.n_observations} observations:{" "}
        <span className="mono">{s.winner}</span> won on held-out negative log predictive
        density, <span className="num">{n(s.recipes[s.winner].nlpd)}</span>
        {loser && <> against <span className="mono">{loser}</span>'s{" "}
          <span className="num">{n(s.recipes[loser].nlpd)}</span></>}.
        {s.next_round && <> Round {s.next_round}'s batch was selected from it.</>}
      </p>
    </Turn>
  );
}

const STEPS = { proposed: Proposed, approved: Approved, submitted: Submitted,
                returned: Returned, scored: Scored, frame: Frame, fitted: Fitted };

export default function History({ history, phase, ctx, reads }) {
  if (!history) return null;
  const steps = history.steps.filter((s) => s.phase === phase);
  if (!steps.length) return null;
  return (
    <>
      {steps.map((s, i) => {
        const Step = STEPS[s.step];
        return Step ? <Step key={`${s.step}-${i}`} s={s} ctx={ctx} /> : null;
      })}
      {reads && (
        <p className="tiny faint" style={{ margin: "-4px 0 14px" }}>
          Read from{" "}
          {history.reads.map((r, i) => (
            <span key={r}>{i > 0 && ", "}<span className="mono">{r}</span></span>
          ))}
          . Round {history.round} ran before this browser opened; nothing above it ran here.
        </p>
      )}
    </>
  );
}
