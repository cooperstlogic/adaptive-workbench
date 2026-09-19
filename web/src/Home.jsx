// The home screen, in the host's own grammar: one card waiting on you, the
// projects you have, the sessions you were in, and a way to start another.
//
// Claude Science's home has a "waiting on you" queue whose items are chat
// interrupts. This one has the same slot carrying a typed decision, which is
// the whole argument compressed into a card.

import { useEffect, useState } from "react";
import { Badge, Empty, Hash, elapsed, n, signed } from "./lib.jsx";

export default function Home({ ctx, onOpenRound, onOpenGraph, onNewProject }) {
  const { view } = ctx;
  const rounds = [...view.rounds].reverse();
  const needs = view.needs_you;
  const latest = view.progress.at(-1);

  return (
    <div className="centre-inner">
      <h1 style={{ fontSize: 26, marginBottom: 4 }}>Good afternoon</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        {view.project.lead.name} {view.project.lead.chain} → {view.project.target},{" "}
        {view.rounds.length} rounds, {view.n_designs} designs.
      </p>

      <h3 style={{ marginTop: 26, marginBottom: 8 }}>
        {needs ? "1 waiting on you" : "Nothing waiting on you"}
      </h3>
      {needs ? (
        <button className="card card-attention"
                style={{ display: "block", width: "100%", textAlign: "left" }}
                onClick={() => onOpenRound(needs.round)}>
          <div className="spread">
            <b>{needs.headline}</b>
            <Badge kind="attn">Needs you</Badge>
          </div>
          <p className="small muted" style={{ margin: "6px 0 0" }}>{needs.detail}</p>
          <p className="tiny faint" style={{ margin: "8px 0 0" }}>
            {needs.kind === "ruling"
              ? "A typed decision with hashed evidence, an if_wrong line, and four verbs "
                + "bound to code paths. Not a chat interrupt."
              : "48 wells chosen by expected improvement under the template's constraints. "
                + "Strike what you do not want; the override is recorded."}
          </p>
        </button>
      ) : (
        <Empty>Every round is ruled and fitted.</Empty>
      )}

      <div className="spread" style={{ marginTop: 28, marginBottom: 8 }}>
        <h3>Projects</h3>
        <button className="btn small" onClick={onNewProject}>+ New project</button>
      </div>
      <div className="card">
        <div className="spread">
          <div>
            <b>{view.project.id}</b>
            <p className="small muted" style={{ margin: "2px 0 0" }}>
              {view.project.template.id} {view.project.template.version} · team{" "}
              {view.project.team.join(", ")}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="num">{latest ? `${n(latest.best_observed)} pKD` : "—"}</div>
            <div className="tiny faint">best observed, synthetic</div>
          </div>
        </div>
        <div className="chain">
          <span className="chip">designs <b className="num">{view.n_designs}</b></span>
          <span className="chip">rounds <b className="num">{view.rounds.length}</b></span>
          <span className="chip">flagged{" "}
            <b className="num">{view.rounds.filter((r) => r.flagged).length}</b></span>
          <button className="chip" onClick={onOpenGraph}>open the round graph →</button>
        </div>
      </div>

      <h3 style={{ marginTop: 28, marginBottom: 8 }}>Recent rounds</h3>
      <div className="stack">
        {rounds.map((r) => (
          <button key={r.round} className="card"
                  style={{ display: "block", width: "100%", textAlign: "left", padding: 13 }}
                  onClick={() => onOpenRound(r.round)}>
            <div className="spread">
              <span className="row wrap">
                <b>Round {r.round}</b>
                <span className="muted small">{r.status}</span>
                {r.flagged && <Badge kind="flag">flagged</Badge>}
                {r.verdict && <Badge kind="ok">{r.verdict.replace(/_/g, " ")}</Badge>}
              </span>
              <span className="tiny faint">{elapsed(r.updated)}</span>
            </div>
            <p className="tiny faint" style={{ margin: "5px 0 0" }}>
              {r.batch ? <>batch <Hash value={r.batch.hash} /> · {r.batch.n} wells</> : "—"}
              {r.anomaly && <> · mean signed residual{" "}
                <span className="num">{signed(r.anomaly.mean_signed_residual)}</span> pKD</>}
              {r.assay_version && <> · assay {r.assay_version}</>}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

/* --- the template gallery, and what a project needs before it can run ------ */

export function Gallery({ onClose }) {
  const [templates, setTemplates] = useState(null);
  const [reqs, setReqs] = useState(null);
  const [picked, setPicked] = useState(null);
  const base = `${import.meta.env.BASE_URL}workbench`;

  useEffect(() => {
    Promise.all([
      fetch(`${base}/templates/antibody-affinity-maturation/template.json`).then((r) => r.json()),
      fetch(`${base}/templates/enzyme-thermostability/template.json`).then((r) => r.json()),
      fetch(`${base}/reference/requirements.json`).then((r) => r.json()),
    ]).then(([a, b, q]) => { setTemplates([a, b]); setReqs(q); });
  }, [base]);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="spread">
          <h2>New project</h2>
          <button className="btn small" onClick={onClose}>close</button>
        </div>
        <p className="small muted">
          A template is a declaration, not a prompt. It carries the objectives schema, the
          constraint ruleset enforced in code, the permitted recipes and diagnostics, and
          the batch policy — so what a project means does not depend on how well someone
          phrased a request.
        </p>

        {!templates ? <Empty>loading…</Empty> : (
          <div className="tiles" style={{ marginTop: 14 }}>
            {templates.map((t) => {
              const stub = t.status === "stub";
              return (
                <button key={t.id} className="tile" aria-disabled={stub}
                        aria-pressed={picked === t.id}
                        onClick={() => !stub && setPicked(picked === t.id ? null : t.id)}>
                  <div className="spread">
                    <b>{t.title}</b>
                    {stub ? <Badge kind="flag">stub</Badge> : <Badge>v{t.version}</Badge>}
                  </div>
                  <p className="small muted" style={{ margin: "6px 0 0" }}>{t.description}</p>
                  {!stub && (
                    <div className="chain">
                      <span className="chip">{t.objectives.length} objectives</span>
                      <span className="chip">≤{t.constraints.max_mutations} mutations</span>
                      <span className="chip">{t.batch.size} wells</span>
                      <span className="chip">{t.diagnostics.length} diagnostics</span>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {picked && templates && (
          <div className="card" style={{ marginTop: 14 }}>
            <h4>What instantiating it writes</h4>
            <ul className="small" style={{ paddingLeft: 18, margin: "6px 0 0" }}>
              <li><span className="mono">objectives.json</span> — the properties, thresholds,
                editable region, mutation budget and batch policy, versioned</li>
              <li><span className="mono">rounds.json</span> — the empty round graph</li>
              <li><span className="mono">designs.json</span> — the parent, and nothing else yet</li>
              <li><span className="mono">project.json</span> — lead, target, team and the
                connectors this project reads from</li>
            </ul>
            <p className="tiny faint" style={{ marginTop: 8 }}>
              Creating a second project is not wired up in this build: the demo runs one
              campaign and a second empty directory proves nothing the first does not. The
              declaration above is what the argument rests on, and it is read from the
              template file itself.
            </p>
          </div>
        )}

        {reqs && (
          <>
            <h4 style={{ marginTop: 18 }}>What it needs before a round can run</h4>
            <p className="small muted" style={{ marginTop: 4 }}>{reqs.note}</p>
            <table className="grid" style={{ marginTop: 8 }}>
              <thead>
                <tr><th>needs</th><th>declared in</th><th>in Claude Science today</th></tr>
              </thead>
              <tbody>
                {reqs.needs.map((r) => (
                  <tr key={r.what}>
                    <td>
                      {r.what}
                      <div className="mono tiny faint">{r.value}</div>
                    </td>
                    <td className="tiny">
                      {r.declared_in === "nothing declares this"
                        ? <Badge kind="flag">nothing declares this</Badge>
                        : <span className="mono">{r.declared_in}</span>}
                    </td>
                    <td className="tiny muted">{r.in_the_host}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h4 style={{ marginTop: 16 }}>And the tools it would get</h4>
            {reqs.servers.map((s) => (
              <div key={s.name} className="card" style={{ padding: 12, marginTop: 8 }}>
                <div className="spread">
                  <b className="mono">{s.name}</b>
                  <Badge>{s.transport}</Badge>
                </div>
                <div className="chain">
                  {s.tools.map((t) => <span key={t} className="chip mono">{t}</span>)}
                </div>
                {s.withheld.length > 0 && (
                  <p className="tiny faint" style={{ marginTop: 8 }}>
                    Not available, deliberately: <span className="mono">
                      {s.withheld.join(", ")}</span>. The answer to “does this replace the
                    LIMS” is a tool list.
                  </p>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
