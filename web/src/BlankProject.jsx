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
// exactly what Claude Science has no way to express. The page does not say
// so: an empty session here is a title and a composer, and that is the point
// made by showing it.

import { useEffect, useState } from "react";
import Composer from "./Composer.jsx";
import Turn from "./Turn.jsx";
import * as blank from "./blank.js";
import * as router from "./router.js";
import { CentreHead, elapsed } from "./lib.jsx";

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
          <CentreHead title={session?.title || "New session"} sub={rec.title} />
          <div className="centre-inner thread">
            {turns.map((t, i) => (
              <Turn key={i} who="you"><p>{t.text}</p></Turn>
            ))}
            {turns.length > 0 && (
              <p className="tiny faint" style={{ margin: "0 0 12px" }}>
                No model is connected in this prototype.
              </p>
            )}

            <Composer busy={false} onSend={send} />
          </div>
        </main>
      </div>
    </div>
  );
}
