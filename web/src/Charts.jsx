// Three charts, drawn as SVG from JSON. No charting library, for the same
// reason core/ has no scipy: the page is meant to be read.
//
// Two of them are about *this project* and read its own artifacts: the
// cumulative best it has observed, and the calibration of its last scored
// round. The third is the evaluator's benchmark -- twenty simulated campaigns
// per arm on a landscape whose ground truth we own -- and it is drawn on the
// template surfaces as the template's validation, never on the project's own
// axes. A project cannot be compared against a random baseline it never ran,
// and a chart that appears to forecast a campaign from a simulation is the
// overclaim this build exists to avoid.

import { n, pct } from "./lib.jsx";

const PAD = { t: 10, r: 12, b: 26, l: 38 };

function scales({ w, h, xs, ys, minSpan = 0, nice = false, pad = PAD }) {
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (y1 - y0 < minSpan) {
    const mid = (y0 + y1) / 2;
    y0 = mid - minSpan / 2;
    y1 = mid + minSpan / 2;
  }
  const padY = (y1 - y0) * 0.08 || 0.5;
  let lo = y0 - padY, hi = y1 + padY;
  if (nice) {
    // Snap the frame out to the tick grid, so the line has a tick above it
    // and one below it rather than ending in the padding.
    const step = tickStep(hi - lo, 5);
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;
  }
  return {
    x: (v) => pad.l + ((v - x0) / (x1 - x0 || 1)) * (w - pad.l - pad.r),
    y: (v) => h - pad.b - ((v - lo) / (hi - lo || 1)) * (h - pad.t - pad.b),
    lo, hi, x0, x1,
  };
}

function tickStep(span, count) {
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || mag * 10;
}

function ticks(lo, hi, count = 4) {
  const step = tickStep(hi - lo, count);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

function Swatch({ colour, dash }) {
  return (
    <svg width="20" height="6" aria-hidden="true" style={{ marginRight: 6 }}>
      <line x1="0" x2="20" y1="3" y2="3" stroke={colour} strokeWidth="1.8"
            strokeDasharray={dash || undefined} />
    </svg>
  );
}

const ARMS = [
  { key: "guided", colour: "var(--c-guided)", label: "model-guided, offsets corrected" },
  { key: "guided_naive", colour: "var(--c-naive)", dash: "5 3",
    label: "model-guided, measurements pooled naively" },
  { key: "random", colour: "var(--c-random)", dash: "2 3",
    label: "random from the feasible pool" },
];

// Both axes are named here and on no other chart, because this is the one a
// reader meets before they have read anything else about the project: a bare
// `pKD` over six unlabelled integers does not say that the line is a running
// maximum or that the numbers underneath are rounds.
const PROOF_PAD = { ...PAD, b: 42, l: 42 };

export function ProofChart({ campaign, width = 430, height = 262 }) {
  if (!campaign) return null;
  const rounds = campaign.summary.guided.per_round.map((r) => r.round);
  const series = ARMS.map((arm) => ({
    ...arm,
    points: campaign.summary[arm.key].per_round.map((r) => ({
      round: r.round, ...r.best_observed,
    })),
  }));
  const ys = [
    ...series.flatMap((s) => s.points.flatMap((p) => [p.q1, p.q3, p.median])),
    campaign.threshold_pkd,
  ];
  const s = scales({ w: width, h: height, xs: rounds, ys, pad: PROOF_PAD });
  const line = (pts, key) =>
    pts.map((p, i) => `${i ? "L" : "M"}${s.x(p.round)},${s.y(p[key])}`).join(" ");
  const band = (pts) =>
    [...pts.map((p, i) => `${i ? "L" : "M"}${s.x(p.round)},${s.y(p.q3)}`),
     ...[...pts].reverse().map((p) => `L${s.x(p.round)},${s.y(p.q1)}`), "Z"].join(" ");

  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label="cumulative best observed affinity by round">
        {ticks(s.lo, s.hi).map((t) => (
          <g key={t}>
            <line className="grid-line" x1={PROOF_PAD.l} x2={width - PROOF_PAD.r}
                  y1={s.y(t)} y2={s.y(t)} />
            <text x={PROOF_PAD.l - 6} y={s.y(t) + 3} textAnchor="end">{t.toFixed(1)}</text>
          </g>
        ))}
        <line className="axis" x1={PROOF_PAD.l} x2={width - PROOF_PAD.r}
              y1={height - PROOF_PAD.b} y2={height - PROOF_PAD.b} />
        {rounds.map((r) => (
          <text key={r} x={s.x(r)} y={height - PROOF_PAD.b + 13} textAnchor="middle">{r}</text>
        ))}
        <text x={(PROOF_PAD.l + width - PROOF_PAD.r) / 2} y={height - 6} textAnchor="middle">
          experimental round
        </text>
        <line x1={PROOF_PAD.l} x2={width - PROOF_PAD.r} y1={s.y(campaign.threshold_pkd)}
              y2={s.y(campaign.threshold_pkd)} stroke="var(--ink)" strokeWidth="1"
              strokeDasharray="1 3" opacity="0.5" />
        <text x={width - PROOF_PAD.r} y={s.y(campaign.threshold_pkd) - 4} textAnchor="end">
          {campaign.threshold_amendment?.length ? "amended threshold " : "threshold "}
          {n(campaign.threshold_pkd, 2)}
        </text>
        {series.map((sr) => (
          <path key={sr.key} d={band(sr.points)} fill={sr.colour} opacity="0.11" />
        ))}
        {series.map((sr) => (
          <path key={sr.key} d={line(sr.points, "median")} fill="none" stroke={sr.colour}
                strokeWidth="1.6" strokeDasharray={sr.dash || undefined} />
        ))}
        <text x={11} y={(height - PROOF_PAD.b + PROOF_PAD.t) / 2}
              transform={`rotate(-90 11 ${(height - PROOF_PAD.b + PROOF_PAD.t) / 2})`}
              textAnchor="middle">cumulative best observed, pKD</text>
      </svg>
      <div className="legend">
        {series.map((sr) => (
          <span key={sr.key}><Swatch colour={sr.colour} dash={sr.dash} />{sr.label}</span>
        ))}
      </div>
      <p className="tiny faint" style={{ marginTop: 6 }}>
        Each line is the median of {campaign.n_seeds} seeds; the band around it is the
        interquartile range. Higher is tighter binding.
      </p>
    </div>
  );
}

/** This project's own line: the best value it held at the end of each round
 *  that has reported, read from its snapshots through `core.reconcile.pool`.
 *  `target` is drawn only if the template declares one. */
export function ProgressChart({ progress, target, width = 430, height = 244 }) {
  if (!progress || !progress.length) return null;
  const rounds = progress.map((p) => p.round);
  const xs = rounds.length > 1 ? rounds : [rounds[0], rounds[0] + 1];
  const ys = [...progress.map((p) => p.best_observed),
              ...(target === undefined || target === null ? [] : [target])];
  const s = scales({ w: width, h: height, xs, ys, minSpan: 1.0, nice: true });
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label="this project's cumulative best observed affinity by round">
        {ticks(s.lo, s.hi).map((t) => (
          <g key={t}>
            <line className="grid-line" x1={PAD.l} x2={width - PAD.r} y1={s.y(t)} y2={s.y(t)} />
            <text x={PAD.l - 6} y={s.y(t) + 3} textAnchor="end">{t.toFixed(1)}</text>
          </g>
        ))}
        <line className="axis" x1={PAD.l} x2={width - PAD.r}
              y1={height - PAD.b} y2={height - PAD.b} />
        {xs.map((r) => (
          <text key={r} x={s.x(r)} y={height - PAD.b + 13} textAnchor="middle">{r}</text>
        ))}
        {target !== undefined && target !== null && (
          <>
            <line x1={PAD.l} x2={width - PAD.r} y1={s.y(target)} y2={s.y(target)}
                  stroke="var(--ink)" strokeWidth="1" strokeDasharray="1 3" opacity="0.5" />
            <text x={width - PAD.r} y={s.y(target) - 4} textAnchor="end">
              target {n(target, 2)}
            </text>
          </>
        )}
        <path d={progress.map((p, i) =>
          `${i ? "L" : "M"}${s.x(p.round)},${s.y(p.best_observed)}`).join(" ")}
              fill="none" stroke="var(--c-guided)" strokeWidth="1.8" />
        {progress.map((p) => (
          <g key={p.round}>
            <circle cx={s.x(p.round)} cy={s.y(p.best_observed)} r="3.4"
                    fill={p.flagged ? "var(--flag)" : "var(--paper)"}
                    stroke={p.flagged ? "var(--flag)" : "var(--c-guided)"} strokeWidth="1.8" />
            {p.flagged && (
              <text x={s.x(p.round) + 8} y={s.y(p.best_observed) + 14}
                    fill="var(--flag)">flagged</text>
            )}
          </g>
        ))}
        <text x={11} y={(height - PROOF_PAD.b + PROOF_PAD.t) / 2}
              transform={`rotate(-90 11 ${(height - PROOF_PAD.b + PROOF_PAD.t) / 2})`}
              textAnchor="middle">cumulative best observed, pKD</text>
      </svg>
    </div>
  );
}

export function CalibrationChart({ evaluation, width = 430, height = 244 }) {
  if (!evaluation || !evaluation.per_design || !evaluation.per_design.length) return null;
  const pts = evaluation.per_design;
  const z = 1.2816; // the 80% central interval evaluate_prior scored against
  const ys = pts.flatMap((p) => [p.observed, p.pred_mean - z * p.pred_sd,
                                 p.pred_mean + z * p.pred_sd]);
  const xs = pts.map((p) => p.pred_mean);
  const lo = Math.min(...ys, ...xs), hi = Math.max(...ys, ...xs);
  const s = scales({ w: width, h: height, xs: [lo, hi], ys: [lo, hi] });
  const cal = evaluation.calibration;
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label="predicted against observed for the previous batch">
        {ticks(s.lo, s.hi).map((t) => (
          <g key={t}>
            <line className="grid-line" x1={PAD.l} x2={width - PAD.r} y1={s.y(t)} y2={s.y(t)} />
            <text x={PAD.l - 6} y={s.y(t) + 3} textAnchor="end">{t.toFixed(1)}</text>
            <text x={s.x(t)} y={height - PAD.b + 13} textAnchor="middle">{t.toFixed(1)}</text>
          </g>
        ))}
        <line className="axis" x1={PAD.l} x2={width - PAD.r}
              y1={height - PAD.b} y2={height - PAD.b} />
        <line x1={s.x(s.lo)} y1={s.y(s.lo)} x2={s.x(s.hi)} y2={s.y(s.hi)}
              stroke="var(--ink)" strokeDasharray="2 3" opacity="0.45" />
        {pts.map((p) => (
          <line key={`i${p.design_id}`} x1={s.x(p.pred_mean)} x2={s.x(p.pred_mean)}
                y1={s.y(p.pred_mean - z * p.pred_sd)} y2={s.y(p.pred_mean + z * p.pred_sd)}
                stroke="var(--line)" strokeWidth="1.4" />
        ))}
        {pts.map((p) => (
          <circle key={p.design_id} cx={s.x(p.pred_mean)} cy={s.y(p.observed)} r="2.8"
                  fill={p.inside_interval ? "var(--accent)" : "var(--flag)"}
                  opacity={p.inside_interval ? 0.75 : 0.95} />
        ))}
        <text x={width - PAD.r} y={height - 4} textAnchor="end">predicted pKD</text>
      </svg>
      <div className="legend">
        <span><Swatch colour="var(--accent)" />inside the 80% interval</span>
        <span><Swatch colour="var(--flag)" />outside it</span>
      </div>
      <p className="tiny faint" style={{ marginTop: 6 }}>
        Realized coverage {pct(cal.realized_coverage, 1)} against a nominal{" "}
        {pct(cal.nominal_coverage, 0)} over {cal.residuals.n} designs, in the frame the
        snapshot records. Vertical bars are each design's own interval.
      </p>
    </div>
  );
}
