// The right-hand artifact panel: five tabs over the project's own records.
//
// Nothing here computes. Every figure on screen was read out of a JSON file
// that a `core/` function wrote, and every figure that came from a named
// function is a button that opens the Notebook tab on it.

import { Fragment, useEffect, useState } from "react";
import { ProofChart, CalibrationChart } from "./Charts.jsx";
import {
  ACTION_LABEL, Badge, Empty, Hash, KV, SYNTHETIC, Trace, n, pct, shortHash, signed, when,
} from "./lib.jsx";

export const TABS = ["Batch", "Decision", "Progress", "Objectives", "Notebook"];

export default function Panel({ tab, setTab, ctx }) {
  return (
    <aside className="panel">
      <div className="panel-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" className="panel-tab" aria-selected={tab === t}
                  onClick={() => setTab(t)}>
            {t}
            {t === "Decision" && ctx.decision?.status === "open" && " ●"}
          </button>
        ))}
      </div>
      <div className="panel-body" role="tabpanel">
        {tab === "Batch" && <BatchTab ctx={ctx} />}
        {tab === "Decision" && <DecisionTab ctx={ctx} />}
        {tab === "Progress" && <ProgressTab ctx={ctx} />}
        {tab === "Objectives" && <ObjectivesTab ctx={ctx} />}
        {tab === "Notebook" && <NotebookTab ctx={ctx} />}
      </div>
    </aside>
  );
}

/* --- Batch ---------------------------------------------------------------- */

const SLOT_BADGE = {
  control: ["", "control"],
  replicate: ["", "replicate"],
  exploration: ["attn", "exploration"],
  pick: [null, null],
};

function BatchTab({ ctx }) {
  const { batch, designs, round, onTrace, drops, setDrops, dropNotes, setDropNotes } = ctx;
  const [open, setOpen] = useState(null);
  if (!batch) return <Empty>No batch selected for this round yet.</Empty>;

  const mut = (id) => (designs[id]?.mutations || []).join(" · ") || "parent";
  const approved = batch.approval.status === "approved";

  return (
    <div className="stack">
      <div className="spread">
        <h3>Round {round} batch</h3>
        <Badge kind={approved ? "ok" : "attn"}>
          {approved ? `approved by ${batch.approval.by}` : "unreviewed"}
        </Badge>
      </div>
      <KV rows={[
        ["wells", `${batch.slots.length} = ${batch.composition.control} control, `
          + `${batch.composition.replicate} replicate, ${batch.composition.exploration} `
          + `exploration, ${batch.composition.pick} fresh picks`],
        ["model", batch.model_winner || "none yet; seed branch"],
        ["incumbent", batch.incumbent === null ? "—"
          : <span className="num">{n(batch.incumbent)} pKD</span>],
        ["batch hash", <Hash value={batch.hash} />],
        ["from", <span className="tiny">
          pool <Hash value={batch.inputs.pool} />, model <Hash value={batch.inputs.model_run} />,
          {" "}objectives <Hash value={batch.inputs.objectives} />
        </span>],
      ]} />
      {!approved && (
        <p className="note">
          Struck designs are recorded as overrides with your note, by the same script that
          chose them. Approving re-runs selection with your name on it.
        </p>
      )}
      <table className="grid">
        <thead>
          <tr>
            {!approved && <th style={{ width: 22 }} />}
            <th>design</th>
            <th>mutations</th>
            <th className="r">pred</th>
            <th className="r">± sd</th>
            <th className="r">EI</th>
            <th>slot</th>
          </tr>
        </thead>
        <tbody>
          {batch.slots.map((s) => {
            const [kind, label] = SLOT_BADGE[s.slot] || [null, s.slot];
            const struck = drops.includes(s.design_id);
            return (
              <Fragment key={s.design_id}>
                <tr style={struck ? { opacity: 0.45 } : undefined}>
                  {!approved && (
                    <td>
                      <input type="checkbox" checked={!struck} aria-label={`keep ${s.design_id}`}
                             onChange={() => setDrops(struck
                               ? drops.filter((d) => d !== s.design_id)
                               : [...drops, s.design_id])} />
                    </td>
                  )}
                  <td>
                    <button type="button" className="trace"
                            onClick={() => setOpen(open === s.design_id ? null : s.design_id)}>
                      {s.design_id}
                    </button>
                  </td>
                  <td className="tiny">{mut(s.design_id)}</td>
                  <td className="r">
                    <Trace onTrace={onTrace} source="core.surrogate.predict"
                           label={`predicted pKD for ${s.design_id}`} value={s.pred_mean}
                           inputs={{ model_run: batch.inputs.model_run, pool: batch.inputs.pool }}>
                      {n(s.pred_mean)}
                    </Trace>
                  </td>
                  <td className="r num faint">{n(s.pred_sd)}</td>
                  <td className="r">
                    <Trace onTrace={onTrace} source="core.acquisition.expected_improvement"
                           label={`expected improvement for ${s.design_id}`}
                           value={s.expected_improvement}
                           inputs={{ model_run: batch.inputs.model_run }}>
                      {n(s.expected_improvement, 4)}
                    </Trace>
                  </td>
                  <td>
                    {label ? <Badge kind={kind}>{label}</Badge> : null}
                    {s.extrapolation && <Badge kind="flag">extrapolating</Badge>}
                  </td>
                </tr>
                {open === s.design_id && (
                  <tr>
                    <td colSpan={approved ? 6 : 7} style={{ background: "var(--line-soft)" }}>
                      <div className="stack">
                        <p className="small" style={{ margin: 0 }}>{s.rationale}</p>
                        <KV rows={[
                          ["plate", s.plate_planned],
                          ["hydrophobicity", <span className="num">
                            {n(s.computed.hydrophobicity)}</span>],
                          ["liabilities introduced", <span className="num">
                            {s.computed.liability_count}</span>],
                          ["bridge", s.bridge ? "yes — measured in an earlier round" : "no"],
                        ]} />
                        {!approved && (
                          <input className="field" placeholder="override note, if you strike it"
                                 value={dropNotes[s.design_id] || ""}
                                 onChange={(e) => setDropNotes({
                                   ...dropNotes, [s.design_id]: e.target.value })} />
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <p className="tiny faint">
        Hydrophobicity and liability counts are computed, not measured. Affinity is
        predicted by the model and simulated by the oracle.
      </p>
    </div>
  );
}

/* --- Decision ------------------------------------------------------------- */

const SCALAR = (v) => v === null || ["number", "boolean", "string"].includes(typeof v);

function ResultBlock({ result, source, inputs, onTrace }) {
  const scalars = Object.entries(result).filter(([k, v]) =>
    SCALAR(v) && !["note", "test", "scored_excludes", "scope", "round"].includes(k));
  const groups = Object.entries(result).filter(([, v]) => v && typeof v === "object");
  return (
    <div className="stack">
      {result.note && <p className="small muted" style={{ margin: 0 }}>{result.note}</p>}
      <table className="grid">
        <tbody>
          {scalars.map(([k, v]) => (
            <tr key={k}>
              <td className="muted">{k.replace(/_/g, " ")}</td>
              <td className="r">
                {typeof v === "number" ? (
                  <Trace onTrace={onTrace} source={source} label={k} value={v} inputs={inputs}>
                    {Number.isInteger(v) ? v : n(v, 6)}
                  </Trace>
                ) : <span className="tiny">{String(v)}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {groups.map(([k, v]) => (
        <details key={k}>
          <summary className="small muted">{k.replace(/_/g, " ")}</summary>
          <pre className="code">{JSON.stringify(v, null, 1)}</pre>
        </details>
      ))}
    </div>
  );
}

const READING = {
  supported: "ok", "partially supported": "flag", "not supported": "", inconclusive: "",
};

function DecisionTab({ ctx }) {
  const { decision, onTrace } = ctx;
  if (!decision) {
    return <Empty>
      No decision record for this round. One is written when a round is flagged and the
      diagnosis is proposed.
    </Empty>;
  }
  const rec = decision.recommendation;
  return (
    <div className="stack">
      <div className="spread">
        <h3>decision_{String(decision.round).padStart(3, "0")}</h3>
        <Badge kind={decision.status === "ruled" ? "ok" : "attn"}>{decision.status}</Badge>
      </div>
      <p className="small">{decision.trigger}</p>
      <KV rows={[
        ["record", <Hash value={decision.hash} />],
        ["inputs", <span className="tiny">
          snapshot <Hash value={decision.inputs.snapshot} />, batch{" "}
          <Hash value={decision.inputs.batch} />, model <Hash value={decision.inputs.model_run} />
        </span>],
        ["passes", decision.n_passes],
      ]} />
      <p className="note">{decision.provenance_note}</p>

      <h4 style={{ marginTop: 6 }}>Hypotheses</h4>
      {decision.hypotheses.map((h) => (
        <details key={h.id} className="card" style={{ padding: 12 }}>
          <summary>
            <span className="row wrap" style={{ display: "inline-flex" }}>
              <b className="mono">{h.id}</b>
              <Badge kind={READING[h.reading]}>{h.reading}</Badge>
              <span className="tiny faint">{h.diagnostic}</span>
            </span>
            <div className="small" style={{ marginTop: 4 }}>{h.claim}</div>
          </summary>
          <div className="stack" style={{ marginTop: 10 }}>
            {h.reasoning && <p className="small" style={{ margin: 0 }}>{h.reasoning}</p>}
            <ResultBlock result={h.result} source={h.source} inputs={h.inputs}
                         onTrace={onTrace} />
            <p className="tiny faint">
              {h.source} · snapshot <Hash value={h.inputs.snapshot} /> · batch{" "}
              <Hash value={h.inputs.batch} />
            </p>
          </div>
        </details>
      ))}

      {decision.ad_hoc?.length > 0 && (
        <>
          <h4 style={{ marginTop: 6 }}>Ad hoc analysis</h4>
          <p className="tiny faint">
            One-off, unversioned, written for this round. Evidence a human reads; never an
            input to a code path.
          </p>
          {decision.ad_hoc.map((a, i) => (
            <details key={i} className="card" style={{ padding: 12 }}>
              <summary className="small">{a.question}</summary>
              <div className="stack" style={{ marginTop: 10 }}>
                <pre className="code">{a.code}</pre>
                <pre className="code">{a.stdout}</pre>
              </div>
            </details>
          ))}
        </>
      )}

      <h4 style={{ marginTop: 6 }}>Recommendation</h4>
      <div className="card">
        <div className="spread">
          <b>{ACTION_LABEL[rec.action] || rec.action}</b>
          <Badge>confidence {rec.confidence}</Badge>
        </div>
        <Para text={rec.rationale} />
        <details style={{ marginTop: 8 }}>
          <summary className="small muted">alternatives considered</summary>
          <Para text={rec.alternative_considered} small />
        </details>
        <h4 className="small" style={{ marginTop: 12 }}>If this is wrong</h4>
        <Para text={rec.if_wrong} small />
      </div>

      {decision.ruling && (
        <div className="card">
          <div className="spread">
            <b>{decision.ruling.verdict.replace(/_/g, " ")}</b>
            <span className="tiny faint">
              {decision.ruling.by} · {when(decision.ruling.at)}
            </span>
          </div>
          {decision.ruling.requested && (
            <p className="small">requested: <span className="mono">
              {decision.ruling.requested}</span></p>
          )}
          {decision.ruling.note && <p className="small">{decision.ruling.note}</p>}
        </div>
      )}
      <p className="synthetic">{SYNTHETIC}</p>
    </div>
  );
}

function Para({ text, small }) {
  return (
    <div className={small ? "small" : undefined}>
      {String(text || "").split(/\n\n+/).map((p, i) => (
        <p key={i} style={{ marginTop: i ? 8 : 6, marginBottom: 0 }}>{p}</p>
      ))}
    </div>
  );
}

/* --- Progress -------------------------------------------------------------- */

function ProgressTab({ ctx }) {
  const { campaign, view, evaluation, onTrace } = ctx;
  const yours = view.progress;
  const best = yours.length ? yours[yours.length - 1] : null;
  const unruled = view.rounds.find((r) => r.status === "flagged, ruling pending");
  return (
    <div className="stack">
      <h3>Cumulative best observed</h3>
      <ProofChart campaign={campaign} yours={yours} />
      {unruled && (
        <p className="note">
          Your line falls at round {unruled.round}, and that is the finding rather than a
          drawing error. The round re-measured the incumbent on an assay version the
          project has never characterized, and pooling the two reads without a correction
          drags the project's best observed value down with it. Rule on round{" "}
          {unruled.round} and it comes back.
        </p>
      )}
      {best && (
        <KV rows={[
          ["your best so far", <span className="num">{n(best.best_observed)} pKD after round{" "}
            {best.round}</span>],
          ["threshold", <span className="num">{n(campaign?.threshold_pkd, 3)} pKD — {" "}
            {campaign?.threshold_provenance}</span>],
          ["designs measured", <span className="num">{best.n_measured}</span>],
        ]} />
      )}
      <p className="synthetic">{SYNTHETIC}</p>

      <h3 style={{ marginTop: 10 }}>Calibration of the last scored round</h3>
      {evaluation
        ? <>
            <CalibrationChart evaluation={evaluation} />
            <KV rows={[
              ["round", evaluation.round],
              ["coverage", <Trace onTrace={onTrace} source="core.surrogate.z_for_central"
                                  label="realized coverage of the 80% interval"
                                  value={evaluation.calibration.realized_coverage}
                                  inputs={evaluation.inputs}>
                {pct(evaluation.calibration.realized_coverage, 1)}</Trace>],
              ["mean signed residual", <span className="num">
                {signed(evaluation.calibration.residuals.mean_signed)} pKD</span>],
              ["at fit, held out", pct(evaluation.calibration.held_out_coverage_at_fit, 1)],
              ["best this round", <span className="num">
                {n(evaluation.improvement.best_this_round)} pKD</span>],
              ["gain over incumbent", <span className="num">
                {signed(evaluation.improvement.gain_over_incumbent)} pKD</span>],
            ]} />
            <p className="tiny faint">{evaluation.calibration.frame_note}</p>
          </>
        : <Empty>No round has been scored yet.</Empty>}
    </div>
  );
}

/* --- Objectives ------------------------------------------------------------ */

function ObjectivesTab({ ctx }) {
  const o = ctx.view.objectives;
  const p = ctx.view.project;
  return (
    <div className="stack">
      <div className="spread">
        <h3>Objectives</h3>
        <Badge>version {o.version} · read-only</Badge>
      </div>
      <p className="note">
        Declared by the template when the project was created, and enforced in code before
        any model runs. Amending this changes what every past round meant, so it is a
        versioned act and not a setting.
      </p>
      <KV rows={[
        ["lead", `${p.lead.name} ${p.lead.chain}`],
        ["target", p.target],
        ["template", `${p.template.id} ${p.template.version}`],
        ["editable region", <span className="num">{o.editable_region.join("–")} (Kabat)</span>],
        ["mutation budget", <span className="num">{o.constraints.max_mutations}</span>],
        ["forbidden motifs", <span className="mono">
          {o.constraints.forbidden_motifs.join(", ")}</span>],
        ["batch", `${o.batch.size} wells — ${o.batch.controls} controls, `
          + `${o.batch.replicates} replicates, ${o.batch.exploration_slots} exploration`],
        ["recipes", o.model_recipes.join(", ")],
        ["objectives hash", <Hash value={o.hash} />],
      ]} />
      <h4>Properties</h4>
      <table className="grid">
        <thead>
          <tr><th>name</th><th>direction</th><th className="r">threshold</th><th>source</th></tr>
        </thead>
        <tbody>
          {o.objectives.map((ob) => (
            <tr key={ob.name}>
              <td>{ob.name}</td>
              <td className="muted">{ob.direction}</td>
              <td className="r num">{ob.threshold === undefined ? "—" : n(ob.threshold, 3)}</td>
              <td>
                <Badge kind={ob.source === "measured" ? "attn" : ""}>{ob.source}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="tiny faint">
        Affinity is measured by the assay. The other two are deterministic calculations over
        the sequence, which is why the optimizer treats them as constraints rather than as
        things to predict.
      </p>
      <h4>Anomaly flag</h4>
      <KV rows={[
        ["statistic", <span className="mono">{o.anomaly_flag.statistic}</span>],
        ["trigger", <span className="num">{n(o.anomaly_flag.trigger_abs_pkd, 2)} pKD</span>],
        ["scope", o.anomaly_flag.scope.replace(/_/g, " ")],
      ]} />
      <p className="tiny faint">{o.anomaly_flag.note}</p>
      <h4>Permitted diagnostics</h4>
      <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
        {o.diagnostics.map((d) => <li key={d} className="mono">{d}</li>)}
      </ul>
      <p className="tiny faint">
        The agent chooses which of these to run and in what order. It cannot name one that
        is not on this list.
      </p>
    </div>
  );
}

/* --- Notebook -------------------------------------------------------------- */

function NotebookTab({ ctx }) {
  const { traced, lineage, onTrace } = ctx;
  const [copied, setCopied] = useState(false);
  useEffect(() => { setCopied(false); }, [traced?.source]);

  if (!traced) {
    return (
      <div className="stack">
        <h3>Notebook</h3>
        <p className="small">
          Click any figure in the batch table or the decision record. This tab shows the{" "}
          <code>core/</code> function that produced it, its source as loaded into this
          browser, and the hashes of what it was given.
        </p>
        <p className="note">
          Claude Science ships a background reviewer that flags untraceable numbers. The
          claim here is narrower and structural: the host versions the <i>skill</i>, and
          nothing versions the <i>number</i> back to the function and the input hash that
          made it. A template makes an untraceable number impossible to write.
        </p>
      </div>
    );
  }
  return (
    <div className="stack">
      <div className="spread">
        <h3>Notebook</h3>
        <button className="btn small" onClick={() => onTrace(null)}>clear</button>
      </div>
      <KV rows={[
        ["value", <span className="num">{typeof traced.value === "number"
          ? n(traced.value, 6) : String(traced.value)}</span>],
        ["field", traced.label],
        ["function", <span className="mono">{traced.source}</span>],
        lineage && ["file", <span className="mono">{lineage.file}:{lineage.first_line}</span>],
        lineage && ["file sha256", <Hash value={lineage.sha256} />],
        traced.args && Object.keys(traced.args).length
          ? ["arguments", <span className="mono">{JSON.stringify(traced.args)}</span>] : null,
      ]} />
      {traced.inputs && (
        <>
          <h4 className="small">Inputs, hashed</h4>
          <table className="grid">
            <tbody>
              {Object.entries(traced.inputs).map(([k, v]) => (
                <tr key={k}>
                  <td className="muted">{k}</td>
                  <td className="mono tiny">{v ? shortHash(v) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {lineage?.error && <p className="err">{lineage.error}</p>}
      {lineage?.source && (
        <>
          <div className="spread">
            <h4 className="small">Source, as loaded in this browser</h4>
            <button className="btn small" onClick={() => {
              navigator.clipboard?.writeText(lineage.source); setCopied(true);
            }}>{copied ? "copied" : "copy"}</button>
          </div>
          <pre className="code">{lineage.source}</pre>
        </>
      )}
    </div>
  );
}
