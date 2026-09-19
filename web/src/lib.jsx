// Formatting and the three or four pieces every panel needs.

export const shortHash = (h) => (h ? String(h).replace(/^sha256:/, "").slice(0, 12) : "—");

export const n = (v, d = 3) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(d);

export const signed = (v, d = 3) =>
  v === null || v === undefined ? "—" : (v >= 0 ? "+" : "") + Number(v).toFixed(d);

export const pct = (v, d = 0) =>
  v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(d)}%`;

export function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function elapsed(iso) {
  if (!iso) return "";
  const days = Math.round((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 21) return `${days}d ago`;
  return `${Math.round(days / 7)}w ago`;
}

export const ACTION_LABEL = {
  apply_offset_correction: "apply offset correction",
  drop_wells: "drop wells",
  refit_only: "refit only",
  no_action: "no action",
};

export const VERBS = [
  { id: "accepted", label: "Accept", blurb: "the recommended action runs, naming this record" },
  { id: "accepted_with_modification", label: "Accept with modification",
    blurb: "the action runs, and your note is part of the record" },
  { id: "more_evidence_requested", label: "Request more evidence",
    blurb: "names a test and hands the work back; nothing runs yet" },
  { id: "rejected", label: "Reject", blurb: "nothing runs; the reason is recorded" },
];

export function Badge({ kind, children }) {
  return <span className={`badge${kind ? ` ${kind}` : ""}`}>{children}</span>;
}

export function Hash({ value, title }) {
  return (
    <span className="mono faint" title={title || value}>
      {shortHash(value)}
    </span>
  );
}

// A number a reader can walk back to the function that produced it. Clicking
// one opens the Notebook tab on it -- decision 107, rendered rather than
// argued.
export function Trace({ onTrace, source, label, value, args, inputs, children }) {
  if (!onTrace || !source) return <span className="num">{children}</span>;
  return (
    <button
      type="button"
      className="trace"
      title={`${source} — open in Notebook`}
      onClick={() => onTrace({ source, label, value, args, inputs })}
    >
      {children}
    </button>
  );
}

export function KV({ rows }) {
  return (
    <dl className="kv">
      {rows.filter(Boolean).map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Empty({ children }) {
  return <p className="muted small" style={{ margin: "6px 0" }}>{children}</p>;
}

export const SYNTHETIC =
  "Synthetic. The landscape is generated, the LIMS is a mock and the assay is an "
  + "oracle replaying values with noise. This shows the decision loop converging; it "
  + "does not show that the method finds better antibodies.";
