// A briefing: the answer to a question about the project, rendered.
//
// **This is where the thesis stops being an assertion.** Open a project you
// have never opened, ask *where are we?*, and back comes the state of the
// campaign — how many rounds, what the best observed value is, which rounds
// flagged and which were ruled, how far the frame has moved and under whose
// authority, which recipe is winning. Every one of those figures was read
// from an artifact on disk, and every one of them resolves in the Notebook
// tab to the `core/` function that produced it. The same question in a chat
// product gets a summary of the transcript, because there is no state to read.
//
// Nothing here computes and nothing here is a model's sentence. `wb_driver`
// assembles typed figures; this file lays them out. Which is the same
// division decision 62 drew for the diagnosis, applied to status.
//
// An answer reports. It says what the state is and where it was read from;
// it does not explain why the workbench is built to have that state.

import { Badge, Empty, SYNTHETIC_TIP, Trace, n, signed } from "./lib.jsx";

/** One number, with the function behind it attached. */
function Fig({ fig, onTrace, digits = 3 }) {
  if (!fig || fig.value === null || fig.value === undefined) return <span>—</span>;
  const body = `${digits === 0 ? fig.value : Number(fig.value).toFixed(digits)}${
    fig.unit ? ` ${fig.unit}` : ""}`;
  return (
    <>
      <Trace onTrace={onTrace} source={fig.source} label={fig.label} value={fig.value}
             inputs={{ read_from: fig.artifact }}>
        {body}
      </Trace>
      {fig.synthetic && (
        <span className="tag-syn" title={SYNTHETIC_TIP}>synthetic</span>
      )}
    </>
  );
}

function Reads({ reads }) {
  if (!reads || !reads.length) return null;
  return (
    <p className="tiny faint" style={{ marginTop: 10 }}>
      Read from{" "}
      {reads.map((r, i) => (
        <span key={r}>{i > 0 && ", "}<span className="mono">{r}</span></span>
      ))}
.
    </p>
  );
}

export default function Briefing({ data, ctx }) {
  const { onTrace } = ctx;
  if (!data) return null;

  if (data.kind === "status") {
    return (
      <>
        <p>
          {data.n_rounds} round{data.n_rounds === 1 ? "" : "s"}, {data.n_designs} designs,{" "}
          {data.n_measured} measured. Best observed{" "}
          <b><Fig fig={data.best_observed} onTrace={onTrace} /></b>.
        </p>
        <table className="grid" style={{ marginTop: 4 }}>
          <thead><tr><th>round</th><th>where it is</th><th>flag</th></tr></thead>
          <tbody>
            {data.rounds.map((r) => (
              <tr key={r.round}>
                <td className="mono">{r.round}</td>
                <td>{r.status}</td>
                <td>
                  {r.flagged && <Badge kind="flag">flagged</Badge>}
                  {r.verdict && <> <Badge kind="ok">{r.verdict.replace(/_/g, " ")}</Badge></>}
                  {r.at_lab && <Badge>at the lab</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.frame_moves.length > 0 && (
          <p style={{ marginTop: 10 }}>
            The measurement frame has moved{" "}
            {data.frame_moves.map((m, i) => (
              <span key={m.round}>
                {i > 0 && ", "}
                <Trace onTrace={onTrace} source={m.offset.source} label={m.offset.label}
                       value={m.offset.value}>
                  {signed(m.offset.value)}
                </Trace>{" "}pKD at round {m.round} under{" "}
                <span className="mono">{m.authority}</span>
              </span>
            ))}
.
          </p>
        )}
        {data.model_winner && (
          <p>
            The winning recipe is <span className="mono">{data.model_winner}</span>, on
            lowest held-out negative log predictive density against{" "}
            <span className="mono">gp_pca64</span>.
          </p>
        )}
        <Reads reads={data.reads} />
      </>
    );
  }

  if (data.kind === "waiting") {
    if (!data.items.length) {
      return (
        <>
          <p>Nothing. Every round is imported, ruled where it needed ruling, and fitted.</p>
          <Reads reads={data.reads} />
        </>
      );
    }
    return (
      <>
        <p>{data.items.length} thing{data.items.length === 1 ? "" : "s"}:</p>
        <ul className="small" style={{ paddingLeft: 18, margin: "0 0 8px" }}>
          {data.items.map((w) => (
            <li key={`${w.round}-${w.kind}`} style={{ marginBottom: 4 }}>
              <b>Round {w.round}</b> — {w.kind}. <span className="muted">{w.detail}</span>
            </li>
          ))}
        </ul>
        <Reads reads={data.reads} />
      </>
    );
  }

  if (data.kind === "flag") {
    return (
      <>
        <p>
          Round {data.round}'s fresh designs came back a mean{" "}
          <b><Fig fig={data.statistic} onTrace={onTrace} /></b> from where the model put
          them, over {data.n_compared} designs, against a trigger of{" "}
          <Fig fig={data.trigger} onTrace={onTrace} digits={2} /> — so it{" "}
          {data.flagged ? "flagged" : "did not flag"}. The assay version is{" "}
          {data.assay_version} and the project{" "}
          {data.known_version_offset === null
            ? "has never characterized it" : "has an offset on record for it"}.
        </p>
        <p>
          An assay shift and a real activity cliff trip this statistic identically. Telling
          them apart means conditioning on the designs this round shares with earlier ones,
          because those are the same molecules measured twice.
        </p>
        {data.policy_note && <p className="note">{data.policy_note}</p>}
        <Reads reads={data.reads} />
      </>
    );
  }

  if (data.kind === "template") {
    const c = data.constraints;
    return (
      <>
        <p>
          <span className="mono">{data.template.id}</span> v{data.template.version}, hashed
          into this project's <span className="mono">objectives.json</span> at{" "}
          <span className="mono faint">{String(data.objectives_hash).slice(7, 19)}</span>.
          It declares:
        </p>
        <ul className="small" style={{ paddingLeft: 18, margin: "0 0 8px" }}>
          <li>editable region VH {data.editable_region[0]}–{data.editable_region[1]},
            at most {c.max_mutations} mutations, forbidden{" "}
            <span className="mono">{(c.forbidden_motifs || []).join(", ")}</span></li>
          <li>{data.objectives.map((o) => `${o.name} ${
            o.direction === "maximize" ? "↑" : "↓"}${
            o.threshold !== undefined ? ` ≤ ${o.threshold}` : ""}`).join(" · ")}</li>
          <li>{data.batch.size} wells: {data.batch.controls} control,{" "}
            {data.batch.replicates} replicate, {data.batch.exploration_slots} exploration</li>
          <li>recipes <span className="mono">{data.recipes.join(", ")}</span>, competed
            every round</li>
          <li>{data.diagnostics.length} diagnostics, and{" "}
            <span className="mono">run_diagnostic.py</span> refuses any name outside this
            list</li>
          <li>a round flags at{" "}
            {n(data.anomaly_flag.trigger_abs_pkd, 2)} pKD of{" "}
            <span className="mono">{data.anomaly_flag.statistic}</span> over{" "}
            {data.anomaly_flag.scope.replace(/_/g, " ")}</li>
        </ul>
        <Reads reads={data.reads} />
      </>
    );
  }

  if (data.kind === "arrival") {
    if (!data.ready) {
      return (
        <>
          <p>
            <b>Not yet.</b> Round {data.round} went to the lab on{" "}
            {String(data.submitted || "").slice(0, 10)} and the registry expects it{" "}
            {String(data.expected || "").slice(0, 10)}.
          </p>
          {data.refusal && (
            <pre className="code" style={{ marginBottom: 9 }}>{data.refusal}</pre>
          )}
          <p className="small muted">Ask again when it has had time.</p>
          <Reads reads={data.reads} />
        </>
      );
    }
    return (
      <>
        <p>
          <b>They are back.</b> {data.rows} rows across {data.plates.join(" and ")} on assay{" "}
          {data.assay_version}, {data.n_failed} well{data.n_failed === 1 ? "" : "s"} failed,{" "}
          {data.n_censored} value{data.n_censored === 1 ? "" : "s"} censored below the
          detection limit, {data.n_ok} of {data.designs} designs reconciled
          {data.unreconciled === 0
            ? " with nothing left over"
            : `, ${data.unreconciled} rows unreconciled`}.
        </p>
        <p>
          {data.flagged ? <>And round {data.round} <b>flagged</b>: </> : <>Round {data.round}{" "}
            did not flag — </>}
          its {data.n_compared} fresh designs came back a mean{" "}
          <b><Fig fig={data.statistic} onTrace={onTrace} /></b> from where the model put
          them, against a trigger of{" "}
          <Fig fig={data.trigger} onTrace={onTrace} digits={2} />. The assay version is{" "}
          {data.assay_version} and the project{" "}
          {data.known_version_offset === null
            ? "has never characterized it" : "has an offset on record for it"}.
        </p>
        <p className="small muted">
          {data.flagged ? "Deciding what it means is next." : "Nothing to decide."}
        </p>
        <Reads reads={data.reads} />
      </>
    );
  }

  if (data.kind === "lab") {
    if (data.status === "running") {
      return (
        <>
          <p>
            Not yet. Round {data.round} went to the lab on{" "}
            {String(data.submitted || "").slice(0, 10)} and is expected{" "}
            {String(data.expected || "").slice(0, 10)}.
          </p>
          <Reads reads={data.reads} />
        </>
      );
    }
    return (
      <>
        <p>Round {data.round} has reported. {data.note}</p>
        <Reads reads={data.reads} />
      </>
    );
  }

  return <Empty>{data.detail || "Nothing to say about that yet."}</Empty>;
}
