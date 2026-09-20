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
// name -- `lead` before it, `aside` at the far end. The column beneath it
// holds the stream and pins the composer to the bottom, so an empty session
// is a title and a composer and nothing else.
export function CentreHead({ title, sub, lead, aside, children }) {
  return (
    <div className="centre-head">
      <div className="row wrap" style={{ gap: 8 }}>
        {lead}
        <h2>{title}</h2>
        {children}
        {aside}
      </div>
      {sub && <p className="small muted" style={{ margin: "1px 0 0" }}>{sub}</p>}
    </div>
  );
}

// The glyph on both side toggles, the host's: a frame with a pane marked off
// at one side, and that pane filled when `filled`. One drawing, so the two
// states of a toggle differ only in the fill and the two toggles differ only
// in the side; the font's box characters gave each a different weight.
function PaneGlyph({ side, filled }) {
  const x = side === "left" ? 6.2 : 9.8;
  const pane = side === "left"
    ? "M6.2 2.2H3.9A2.2 2.2 0 0 0 1.7 4.4v7.2a2.2 2.2 0 0 0 2.2 2.2h2.3z"
    : "M9.8 2.2h2.3a2.2 2.2 0 0 1 2.2 2.2v7.2a2.2 2.2 0 0 1-2.2 2.2H9.8z";
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
         strokeWidth="1.4" aria-hidden="true">
      {filled && <path d={pane} fill="currentColor" stroke="none" />}
      <rect x="1.7" y="2.2" width="12.6" height="11.6" rx="2.2" />
      <path d={`M${x} 2.2v11.6`} />
    </svg>
  );
}

// The one control over the rail: the same button at the right end of the
// rail's header while the rail is open, and at the left end of the centre
// column's title bar while it is hidden. Hidden means gone -- the whole rail,
// not a strip of its icons -- which is what the host does. `lead` marks the
// title bar's copy, which is only drawn when there is no rail to hold it.
// Where the button sits already says which state it is in, so its pane is
// never filled.
export function RailToggle({ rail, lead }) {
  if (!rail || (lead && !rail.hidden)) return null;
  return (
    <button className="rail-toggle" onClick={rail.toggle}
            title={rail.hidden ? "Show the sidebar" : "Hide the sidebar"}>
      <PaneGlyph side="left" />
    </button>
  );
}

// The one control over the artifact panel: it sits at the right end of the
// title bar, and it is the same button whether the panel is a column beside
// the conversation or, under the narrow breakpoint, a sheet over it. It stays
// where it is in both states, so the pane is filled while the panel is open.
export function PanelToggle({ panel }) {
  if (!panel) return null;
  return (
    <button className="glyph wide panel-toggle" aria-pressed={panel.open}
            title={panel.open ? "Hide the artifact panel" : "Show the artifact panel"}
            onClick={panel.toggle}>
      <PaneGlyph side="right" filled={panel.open} /> Artifacts
    </button>
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
