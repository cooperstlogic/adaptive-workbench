// Two charts, drawn as SVG from JSON. No charting library, for the same reason
// core/ has no scipy: the page is meant to be read.

import { n, pct } from "./lib.jsx";

const PAD = { t: 10, r: 12, b: 26, l: 38 };

function scales({ w, h, xs, ys }) {
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const padY = (y1 - y0) * 0.08 || 0.5;
  const lo = y0 - padY, hi = y1 + padY;
  return {
    x: (v) => PAD.l + ((v - x0) / (x1 - x0 || 1)) * (w - PAD.l - PAD.r),
    y: (v) => h - PAD.b - ((v - lo) / (hi - lo || 1)) * (h - PAD.t - PAD.b),
    lo, hi, x0, x1,
  };
}

function ticks(lo, hi, count = 4) {
  const span = hi - lo;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || mag * 10;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

const ARMS = [
  { key: "guided", colour: "var(--c-guided)", label: "model-guided, offsets corrected" },
  { key: "guided_naive", colour: "var(--c-naive)", dash: "5 3",
    label: "model-guided, measurements pooled naively" },
  { key: "random", colour: "var(--c-random)", dash: "2 3",
    label: "random from the feasible pool" },
];

export function ProofChart({ campaign, yours, width = 430, height = 244 }) {
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
    ...(yours || []).map((p) => p.best_observed),
  ];
  const s = scales({ w: width, h: height, xs: rounds, ys });
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
            <line className="grid-line" x1={PAD.l} x2={width - PAD.r} y1={s.y(t)} y2={s.y(t)} />
            <text x={PAD.l - 6} y={s.y(t) + 3} textAnchor="end">{t.toFixed(1)}</text>
          </g>
        ))}
        <line className="axis" x1={PAD.l} x2={width - PAD.r}
              y1={height - PAD.b} y2={height - PAD.b} />
        {rounds.map((r) => (
          <text key={r} x={s.x(r)} y={height - PAD.b + 13} textAnchor="middle">{r}</text>
        ))}
        <line x1={PAD.l} x2={width - PAD.r} y1={s.y(campaign.threshold_pkd)}
              y2={s.y(campaign.threshold_pkd)} stroke="var(--ink)" strokeWidth="1"
              strokeDasharray="1 3" opacity="0.5" />
        <text x={width - PAD.r} y={s.y(campaign.threshold_pkd) - 4} textAnchor="end">
          threshold {n(campaign.threshold_pkd, 2)}
        </text>
        {series.map((sr) => (
          <path key={sr.key} d={band(sr.points)} fill={sr.colour} opacity="0.11" />
        ))}
        {series.map((sr) => (
          <path key={sr.key} d={line(sr.points, "median")} fill="none" stroke={sr.colour}
                strokeWidth="1.6" strokeDasharray={sr.dash || undefined} />
        ))}
        {yours && yours.length > 1 && (
          <>
            <path d={yours.map((p, i) =>
              `${i ? "L" : "M"}${s.x(p.round)},${s.y(p.best_observed)}`).join(" ")}
                  fill="none" stroke="var(--ink)" strokeWidth="1.8" />
            {yours.map((p) => (
              <circle key={p.round} cx={s.x(p.round)} cy={s.y(p.best_observed)} r="3"
                      fill="var(--paper)" stroke="var(--ink)" strokeWidth="1.6" />
            ))}
          </>
        )}
        <text x={PAD.l - 30} y={PAD.t + 4} transform={`rotate(-90 ${PAD.l - 30} ${PAD.t + 4})`}
              textAnchor="end">pKD</text>
      </svg>
      <div className="legend">
        {series.map((sr) => (
          <span key={sr.key}>
            <i style={{ background: sr.colour }} />{sr.label}
          </span>
        ))}
        {yours && yours.length > 1 && (
          <span><i style={{ background: "var(--ink)" }} />this project, in your browser</span>
        )}
      </div>
      <p className="tiny faint" style={{ marginTop: 6 }}>
        Median of {campaign.n_seeds} seeds per arm, band is the interquartile range.
        Your own line is one campaign, not a distribution.
      </p>
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
        <span><i style={{ background: "var(--accent)" }} />inside the 80% interval</span>
        <span><i style={{ background: "var(--flag)" }} />outside it</span>
      </div>
      <p className="tiny faint" style={{ marginTop: 6 }}>
        Realized coverage {pct(cal.realized_coverage, 1)} against a nominal{" "}
        {pct(cal.nominal_coverage, 0)} over {cal.residuals.n} designs, in the frame the
        snapshot records. Vertical bars are each design's own interval.
      </p>
    </div>
  );
}
