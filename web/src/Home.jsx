// Shell A: home. Full-bleed and centred, with no rail and no artifact panel.
//
// Claude Science's home has a "waiting on you" queue whose items are chat
// interrupts. This one has the same slot carrying a typed decision, which is
// the whole argument compressed into a card: a named person rules on a record
// with hashed evidence and an if_wrong line, rather than replying to a
// message.
//
// The projects list is deliberately mixed. One of them is a campaign -- six
// weeks of rounds under a template -- and the rest are one-shot analyses with
// no template at all. Clicking one of those opens an empty chat, which is
// what a project is when nothing has declared what it means. The page does
// not say so. The templated card carries a template, rounds and a best
// observed value, and the others carry a title and a date; the difference is
// shown and not captioned.

import { useEffect, useMemo, useState } from "react";
import NewProjectDialog from "./NewProjectDialog.jsx";
import * as blank from "./blank.js";
import * as meta from "./meta.js";
import * as router from "./router.js";
import * as rt from "./runtime.js";
import {
  APP, APP_STAGE, Badge, Empty, elapsed, n, projectTitle, templateTitle,
} from "./lib.jsx";

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function Home({ epoch, bump, dialog }) {
  const [projects, setProjects] = useState([]);
  const [views, setViews] = useState({});
  const [error, setError] = useState(null);

  useEffect(() => {
    try {
      const templated = rt.call("projects");
      setProjects(templated);
      const next = {};
      for (const p of templated) next[p.id] = rt.call("view", { project: p.id });
      setViews(next);
    } catch (err) {
      setError(String(err.message || err));
    }
  }, [epoch]);

  const blanks = useMemo(() => blank.all(), [epoch]);

  // One card, for the one thing actually waiting. Across every project,
  // because the queue is the person's and not the project's.
  const needs = useMemo(() => {
    const out = [];
    for (const [id, v] of Object.entries(views)) {
      if (v.needs_you) out.push({ project: id, view: v, ...v.needs_you });
    }
    return out;
  }, [views]);

  const sessions = useMemo(() => {
    const out = [];
    for (const [id, v] of Object.entries(views)) {
      for (const s of v.sessions || []) out.push({ ...s, project: id, view: v });
    }
    for (const p of blanks) {
      for (const s of p.sessions || []) {
        out.push({ ...s, title: s.title || "New session", project: p.id, blankTitle: p.title,
                   subtitle: `${s.turns.length} message${s.turns.length === 1 ? "" : "s"}` });
      }
    }
    out.sort((a, b) => String(b.updated || "").localeCompare(String(a.updated || "")));
    return out.slice(0, 8);
  }, [views, blanks]);

  return (
    <div className="home">
      {dialog && (
        <NewProjectDialog bump={bump} onClose={() => router.go(router.HOME)} />
      )}
      <header className="home-head">
        <div>
          <h1 className="brandmark">{APP}</h1>
          <div className="row" style={{ gap: 10, marginTop: 2 }}>
            <span className="tiny faint">{APP_STAGE}</span>
            <span className="tiny accent">
              {needs.length
                ? `${needs.length} waiting on you`
                : "nothing waiting on you"} · running in your browser
            </span>
          </div>
        </div>
        <div className="row">
          <a className="btn small" href={router.href({ kind: "templates" })}>Templates</a>
          <a className="btn small primary" href={router.href({ kind: "new" })}>
            + New project
          </a>
        </div>
      </header>

      {error && <div className="err" style={{ marginBottom: 16 }}>{error}</div>}

      <h2 className="home-greet">{greeting()}</h2>

      <div className="home-grid">
        <section>
          <h3 className="home-h">
            {needs.length ? `${needs.length} waiting on you` : "Nothing waiting on you"}
          </h3>
          {needs.length === 0 && <Empty>Every round is ruled and fitted.</Empty>}
          {needs.map((item) => (
            <a key={`${item.project}-${item.round}`} className="card card-attention block"
               href={router.href({ kind: "session", project: item.project,
                                   id: `r${item.round}` })}>
              <div className="spread">
                <b>{item.headline}</b>
                <Badge kind="attn">Needs you</Badge>
              </div>
              <p className="small muted" style={{ margin: "5px 0 0" }}>
                {projectTitle(item.view.project)} · {item.detail}
              </p>
              <p className="tiny faint" style={{ margin: "8px 0 0", textAlign: "right" }}>
                {elapsed(item.view.rounds.find((r) => r.round === item.round)?.updated)}
              </p>
            </a>
          ))}

          <h3 className="home-h" style={{ marginTop: 26 }}>Projects</h3>
          <div className="stack">
            {projects.map((p) => {
              const v = views[p.id];
              return (
                <a key={p.id} className="card block"
                   href={router.href({ kind: "project", project: p.id })}>
                  <div className="spread">
                    <div>
                      <b>{projectTitle(p)}</b>
                      <p className="tiny faint mono" style={{ margin: "2px 0 0" }}>{p.id}</p>
                      {meta.describe(p.id) && (
                        <p className="small muted" style={{ margin: "6px 0 0", maxWidth: 420 }}>
                          {meta.describe(p.id)}
                        </p>
                      )}
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className="num">
                        {p.best_observed == null ? "—" : `${n(p.best_observed)} pKD`}
                      </div>
                      <div className="tiny faint">best observed, synthetic</div>
                    </div>
                  </div>
                  <div className="chain">
                    <span className="chip">{templateTitle(p.template)}</span>
                    <span className="chip">rounds <b className="num">{p.n_rounds}</b></span>
                    <span className="chip">designs <b className="num">{p.n_designs}</b></span>
                    {p.n_flagged > 0 && (
                      <span className="chip">flagged <b className="num">{p.n_flagged}</b></span>
                    )}
                    {v?.reported_round && (
                      <span className="chip">round {v.reported_round} reported</span>
                    )}
                    {v?.at_lab_round && (
                      <span className="chip">round {v.at_lab_round} at the lab</span>
                    )}
                  </div>
                </a>
              );
            })}
            {blanks.map((p) => (
              <a key={p.id} className="card block subtle"
                 href={router.href({ kind: "project", project: p.id })}>
                <div className="spread">
                  <b>{p.title}</b>
                  <span className="tiny faint">{elapsed(p.updated)}</span>
                </div>
                {meta.describe(p.id) && (
                  <p className="small muted" style={{ margin: "5px 0 0" }}>
                    {meta.describe(p.id)}
                  </p>
                )}
              </a>
            ))}
          </div>
        </section>

        <section>
          <h3 className="home-h">Recent sessions</h3>
          {sessions.length === 0 && <Empty>Nothing yet.</Empty>}
          <div className="stack">
            {sessions.map((s) => (
              <a key={`${s.project}-${s.id}`} className="card row-card block"
                 href={router.href({ kind: "session", project: s.project, id: s.id })}>
                <div className="spread">
                  <span className="row" style={{ gap: 7, minWidth: 0 }}>
                    <span className={`sess-dot ${s.kind === "round" ? "round" : "adhoc"}`} />
                    <b className="ellipsis">{s.title}</b>
                    {s.flagged && <Badge kind="flag">!</Badge>}
                  </span>
                  <span className="tiny faint nowrap">{elapsed(s.updated)}</span>
                </div>
                <p className="tiny faint" style={{ margin: "3px 0 0 15px" }}>
                  {s.blankTitle || <>
                    {projectTitle(s.view?.project)}{" "}
                    <span className="mono">{s.project}</span>
                  </>} · {s.subtitle}
                </p>
              </a>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
