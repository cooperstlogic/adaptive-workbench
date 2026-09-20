// Formatting, the names the product wears, and the three or four pieces every
// panel needs.

// The product is Claude Science; this is what a project becomes once a
// template is applied to it. Only the template's *display* title changes --
// `antibody-affinity-maturation` is the id written into project.json, named
// by decision records and read by check.py, and it is carried unchanged.
export const APP = "Shannon Science";
export const APP_STAGE = "Beta";
export const TEMPLATE_TITLES = {
  "antibody-affinity-maturation": "Adaptive antibody optimization",
  "enzyme-thermostability": "Enzyme thermostability",
};
export const templateTitle = (t) =>
  TEMPLATE_TITLES[t?.id || t] || t?.title || String(t?.id || t || "");

// The two models the function accepts, and what the picker calls them. The
// ids are the API's; the function refuses any other.
export const MODELS = [
  { id: "claude-sonnet-5", label: "Sonnet 5" },
  { id: "claude-haiku-4-5-20251001", label: "Haiku 4.5" },
];
export const MODEL_LABEL = Object.fromEntries(MODELS.map((m) => [m.id, m.label]));

/** What a project is called on screen: the molecule and its target. */
export function projectTitle(p) {
  if (!p) return "";
  if (p.kind === "blank") return p.title || p.id;
  const lead = p.lead?.name || p.project?.lead?.name;
  const target = p.target || p.project?.target;
  if (!lead) return p.id;
  return `${lead[0].toUpperCase()}${lead.slice(1)} → ${target}`;
}


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

export function dayMonth(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
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

// The title bar across the top of the centre column: what the session is
// called, one line of context under it, and anything that belongs beside the
// name. The column beneath it holds the stream and pins the composer to the
// bottom, so an empty session is a title and a composer and nothing else.
export function CentreHead({ title, sub, children }) {
  return (
    <div className="centre-head">
      <div className="row wrap" style={{ gap: 8 }}>
        <h2>{title}</h2>
        {children}
      </div>
      {sub && <p className="small muted" style={{ margin: "1px 0 0" }}>{sub}</p>}
    </div>
  );
}

// The one-word label beside an affinity number, and what it means when a
// reader hovers it. CLAUDE.md failure mode 3: the word "synthetic" in the same
// breath as the number. The word is the whole label; the explanation is the
// tooltip and the README, not a paragraph on the page.
export const SYNTHETIC_TIP =
  "The landscape is generated and the assay is an oracle replaying values with noise. "
  + "This shows the decision loop converging; it does not show that the method finds "
  + "better antibodies.";
