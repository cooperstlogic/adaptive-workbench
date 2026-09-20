// A project with no template. The control arm.
//
// Same chrome as a templated project — rail header, New / Search / Customize
// / Files / Compute, settings at the bottom, composer pinned with a working
// model picker — and nothing in it, because nothing has declared what it
// means. There is no Rounds item because there is no round graph. There is no
// artifact panel because there are no artifacts. There is no approval,
// because there is nothing to approve.
//
// That is decision 108 demonstrated rather than asserted. Open this beside
// the templated project: one of them opens on a blinking cursor and the other
// opens on 48 wells already enumerated, filtered against constraints enforced
// in code, scored by a model that beat another model, and waiting for a named
// person to sign. The gap between them is the template, and a template is
// exactly what Claude Science has no way to express.

import { useEffect, useState } from "react";
import Composer from "./Composer.jsx";
import Turn from "./Turn.jsx";
import * as blank from "./blank.js";
import * as router from "./router.js";
import { elapsed } from "./lib.jsx";

const RAIL = [
  { id: "new", icon: "✦", label: "New" },
  { id: "search", icon: "⌕", label: "Search" },
  { id: "customize", icon: "◉", label: "Customize" },
  { id: "files", icon: "▤", label: "Files" },
  { id: "compute", icon: "⚙", label: "Compute" },
];

export default function BlankProject({ route, project, bump }) {
  const [rec, setRec] = useState(project);
  const pid = project.id;
  const sessionId = route.kind === "session" ? route.id : null;

  useEffect(() => {
    if (route.kind === "project") {
      const first = (rec.sessions || [])[0];
      router.replace({ kind: "session", project: pid, id: first ? first.id : "new" });
    } else if (sessionId === "new") {
      if (project.seeded) {
        // A seeded project is scenery until someone types in it. Making it
        // real on open would fill localStorage with four empty projects
        // nobody asked for.
        return;
      }
      const s = blank.newSession(pid);
      if (s) {
        setRec(blank.get(pid));
        bump();
        router.replace({ kind: "session", project: pid, id: s.id });
      }
    }
  }, [route.kind, sessionId, pid, rec, project.seeded, bump]);

  const session = (rec.sessions || []).find((s) => s.id === sessionId) || null;
  const turns = session?.turns || [];

  const send = (text) => {
    let live = rec;
    if (project.seeded && !blank.get(pid)) {
      live = blank.create(project.title);
    }
    const target = live.id;
    let sid = sessionId;
    if (!sid || sid === "new" || !(blank.get(target)?.sessions || []).some((s) => s.id === sid)) {
      sid = blank.newSession(target).id;
    }
    blank.addTurn(target, sid, text);
    setRec(blank.get(target));
    bump();
    if (target !== pid || sid !== sessionId) {
      router.go({ kind: "session", project: target, id: sid });
    }
  };

  return (
    <div className="shell">
      <div className="body">
        <nav className="rail">
          <div className="rail-head">
            <a className="rail-back" href="#/" title="All projects">←</a>
            <button className="rail-project">
              <span className="ellipsis">{rec.title}</span>
              <span className="chev">⌄</span>
            </button>
            <button className="rail-collapse" title="Collapse">▤</button>
          </div>
          <div className="rail-sub tiny faint">No template</div>
          {RAIL.map((item) => (
            <a key={item.id} className="rail-item"
               href={item.id === "new"
                 ? router.href({ kind: "session", project: pid, id: "new" }) : "#"}
               onClick={(e) => { if (item.id !== "new") e.preventDefault(); }}>
              <span className="ic">{item.icon}</span>{item.label}
            </a>
          ))}

          <div className="rail-group hide-narrow">
            <div className="rail-label">Sessions</div>
            <div className="rail-sessions">
              {(rec.sessions || []).length === 0 && (
                <p className="tiny faint" style={{ padding: "4px 10px" }}>No sessions yet</p>
              )}
              {(rec.sessions || []).map((s) => (
                <a key={s.id} className="rail-session" aria-current={sessionId === s.id}
                   href={router.href({ kind: "session", project: pid, id: s.id })}>
                  <span className="t">
                    <span className="sess-dot adhoc" />
                    <span className="ellipsis">{s.title || "New session"}</span>
                  </span>
                  <span className="s">{elapsed(s.created)}</span>
                </a>
              ))}
            </div>
          </div>

          <div className="rail-foot hide-narrow">
            <button className="rail-item"><span className="ic">⚙</span>Settings</button>
          </div>
        </nav>

        <main className="centre">
          <div className="centre-inner">
            <h2>{session?.title || "New session"}</h2>
            <p className="small muted" style={{ margin: "2px 0 20px" }}>{rec.title}</p>

            {turns.length === 0 && (
              <Turn who="claude">
                <p>
                  This project has no template, so there is nothing here but this
                  conversation. Which is the point of showing it to you.
                </p>
                <p className="small muted">
                  Next door, <a href="#/p/demo-trastuzumab">Trastuzumab → HER2</a> has a
                  template applied, and that one file is the whole difference: it declares
                  the objectives schema, the constraint ruleset that is enforced in code
                  before any model runs, the recipes permitted to compete, the diagnostics
                  a decision may cite, and the batch policy. Without it there is no round
                  graph to read, no batch to approve and no decision to rule on — not
                  because the feature is missing, but because nothing has said what any of
                  those would mean here.
                </p>
                <p className="tiny faint">
                  Type something if you like. It is kept in this browser and goes nowhere;
                  there is no model behind this composer in this build.
                </p>
              </Turn>
            )}

            {turns.map((t, i) => (
              <Turn key={i} who="you"><p>{t.text}</p></Turn>
            ))}
            {turns.length > 0 && (
              <Turn who="claude">
                <p className="muted">
                  There is no model wired to this composer in this build — phase 7 is where
                  one arrives. What your message demonstrates is the shape of the thing:
                  a project whose entire state is what was said in it.
                </p>
              </Turn>
            )}

            <Composer busy={false} onSend={send}
                      note={"Nothing typed here is sent anywhere. The picker is the host's "
                        + "own; the project is empty because no template has declared what "
                        + "it means."} />
          </div>
        </main>
      </div>
    </div>
  );
}
