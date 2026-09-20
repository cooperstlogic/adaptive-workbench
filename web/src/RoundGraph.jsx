// Rounds: the one primitive added to the rail, and the thing rounds.json has
// nowhere to render today.
//
// Gap 106 of the phase-5b audit. The host's rail lists chat threads named
// after what was asked — *Diagnose Round 4…*, *Run evaluate_prior.py Round
// 3*. A six-week campaign is not a list of questions; it is a graph running
// recommendation → tested constructs → returned evidence → diagnosis →
// updated model → next batch, with a content hash at every edge. This view is
// that graph, read straight out of rounds.json. It does not say so: the chips
// carry the hashes, and the page is the graph.

import { Badge, Empty, elapsed, n, pct, signed, when } from "./lib.jsx";

const LINKS = [
  ["pool", "candidates enumerated and filtered"],
  ["batch", "wells chosen and approved"],
  ["snapshot", "what the lab returned, reconciled"],
  ["evaluation", "predictions scored against it"],
  ["decision", "the judgment call and its ruling"],
  ["model", "the refit that carries it forward"],
];

export default function RoundGraph({ ctx, onOpenRound }) {
  const { view } = ctx;
  return (
    <div className="centre-inner">
      <div className="spread">
        <div>
          <h2>Rounds</h2>
          <p className="small muted" style={{ margin: "2px 0 0" }}>
            {view.project.id} · {view.rounds.length} rounds · read from{" "}
            <span className="mono">rounds.json</span>
          </p>
        </div>
      </div>

      <p className="tiny faint" style={{ margin: "10px 0 18px" }}>
        Dates are simulated, like the affinities.
      </p>

      <div className="graph">
        {view.rounds.map((r) => (
          <div className="graph-round" key={r.round}>
            <div className="graph-spine">
              <span className={`graph-pin${r.flagged ? " flag" : ""}`
                + `${r.status === "flagged, ruling pending" ? " open" : ""}`} />
              <div className="graph-when">
                {when(r.updated)}
                <div>{elapsed(r.updated)}</div>
              </div>
            </div>
            <div className="graph-card">
              <button className="row wrap" style={{ border: 0, background: "none", padding: 0 }}
                      onClick={() => onOpenRound(r.round)}>
                <b>Round {r.round}</b>
                <span className="muted small">{r.status}</span>
                {r.flagged && <Badge kind="flag">flagged</Badge>}
                {r.verdict && <Badge kind="ok">{r.verdict.replace(/_/g, " ")}</Badge>}
                {r.assay_version && <Badge>assay {r.assay_version}</Badge>}
              </button>

              <p className="small muted" style={{ margin: "5px 0 0" }}>
                {r.batch && <>{r.batch.n} wells from{" "}
                  {r.batch.model_winner || "the template's round-1 policy"}</>}
                {r.improvement && <> · best{" "}
                  <span className="num">{n(r.improvement.best_this_round)}</span> pKD</>}
                {r.calibration && <> · coverage{" "}
                  <span className="num">{pct(r.calibration.realized_coverage, 0)}</span></>}
                {r.anomaly && r.flagged && <> · residual{" "}
                  <span className="num">{signed(r.anomaly.mean_signed_residual)}</span> pKD</>}
              </p>

              {r.frame?.offset_applied ? (
                <p className="tiny faint" style={{ margin: "4px 0 0" }}>
                  frame moved <span className="num">
                    {signed(r.frame.offset_applied)}</span> pKD under{" "}
                  <span className="mono">{r.frame.authority}</span>
                </p>
              ) : null}

              <div className="chain">
                {LINKS.map(([key, title]) => {
                  const ref = r.refs[key];
                  return (
                    <span key={key} className={`chip${ref ? " on" : ""}`} title={title}>
                      {key}
                      {ref ? <b className="h">{ref.hash.replace("sha256:", "").slice(0, 8)}</b>
                           : <b className="h">—</b>}
                    </span>
                  );
                })}
              </div>
              {r.model && (
                <p className="tiny faint" style={{ margin: "6px 0 0" }}>
                  {r.model.winner} won the bake-off on {r.model.n_observations} observations
                  {Object.entries(r.model.recipes).map(([name, m]) => (
                    <span key={name}> · {name} nlpd <span className="num">
                      {n(m.nlpd, 3)}</span></span>
                  ))}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
      {!view.rounds.length && <Empty>No rounds yet.</Empty>}
    </div>
  );
}
