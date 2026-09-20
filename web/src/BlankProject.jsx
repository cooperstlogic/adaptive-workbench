// A project with no template. The control arm.
//
// Same chrome as a templated project — rail header, New, settings at the
// bottom, composer pinned with a working model picker — and nothing in it,
// because nothing has declared what it
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

import { useEffect, useRef, useState } from "react";
import Composer from "./Composer.jsx";
import Prose from "./Prose.jsx";
import Turn from "./Turn.jsx";
import * as agent from "./agent.js";
import * as blank from "./blank.js";
import * as meta from "./meta.js";
import * as router from "./router.js";
import { CentreHead, MODEL_LABEL, elapsed } from "./lib.jsx";

export default function BlankProject({ route, project, bump, live, reprobe, model, setModel }) {
  const [rec, setRec] = useState(project);
  // The answer being streamed, if a model is seated. A blank project is a
  // chat with nothing declared: no tools, no context, and the answer says
  // what has not been declared when asked.
  const [streaming, setStreaming] = useState(null);
  const inFlight = useRef(null);
  // One signed transcript per session, in page memory, so a follow-up here
  // is a follow-up -- the same rule as a templated project's sessions.
  const transcripts = useRef(new Map());
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

  const send = async (text, chosenModel) => {
    let mine = rec;
    if (project.seeded && !blank.get(pid)) {
      mine = blank.create(project.title);
    }
    const target = mine.id;
    let sid = sessionId;
    if (!sid || sid === "new" || !(blank.get(target)?.sessions || []).some((s) => s.id === sid)) {
      sid = blank.newSession(target).id;
    }
    const s = blank.addTurn(target, sid, text);
    const index = s.turns.length - 1;
    setRec(blank.get(target));
    bump();
    if (target !== pid || sid !== sessionId) {
      router.go({ kind: "session", project: target, id: sid });
    }
    if (!(live && live.live)) return;
    const thread = `${target}/${sid}`;
    const keep = (t) => {
      const reply = { text: t.steps.filter((x) => x.type === "text").map((x) => x.text).join("\n\n"),
                      model: t.model, status: t.status, stop: t.stop, upstream: t.upstream,
                      restarted: t.restarted };
      if (t.transcript) transcripts.current.set(thread, t.transcript);
      inFlight.current = { ...t, index };
      setStreaming({ ...t, index });
      blank.answer(target, sid, index, reply);
    };
    try {
      await agent.runLive({
        kind: "chat", question: text, model: chosenModel || model, call: () => null,
        instructions: meta.instructionsFor(target) || null,
        transcript: transcripts.current.get(thread) || null,
        emit: () => { if (inFlight.current) setStreaming({ ...inFlight.current }); },
        save: keep,
      });
    } finally {
      setStreaming(null);
      inFlight.current = null;
      setRec(blank.get(target));
      if (reprobe) reprobe();
    }
  };

  const badgeFor = (a) => (a.status === "stopped" && a.stop
    ? { kind: "stop", text: `stopped · ${a.stop.reason}` }
    : { kind: "live",
        text: (a.upstream === "scripted" ? "scripted · harness"
          : `live · ${MODEL_LABEL[a.model] || a.model || "model"}`)
          + (a.restarted ? " · restarted" : ""),
        title: a.restarted ? `the conversation started over: ${a.restarted}` : undefined });

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
          <a className="rail-item" href={router.href({ kind: "session", project: pid,
                                                       id: "new" })}>
            <span className="ic">✦</span><span>New</span>
          </a>

          {meta.instructionsFor(pid) && (
            <div className="rail-group hide-narrow">
              <div className="rail-label">Instructions for Claude</div>
              <p className="tiny faint rail-note">{meta.instructionsFor(pid)}</p>
            </div>
          )}

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
            <button className="rail-item"><span className="ic">⚙</span><span>Settings</span></button>
          </div>
        </nav>

        <main className="centre">
          <CentreHead title={session?.title || "New session"} sub={rec.title} />
          <div className="centre-inner thread">
            {turns.map((t, i) => {
              const inflight = streaming && streaming.index === i;
              const reply = inflight
                ? { text: streaming.steps.filter((x) => x.type === "text").map((x) => x.text)
                      .join("\n\n"), model: streaming.model, status: streaming.status,
                    stop: streaming.stop, upstream: streaming.upstream }
                : t.answer;
              return (
                <div key={i}>
                  <Turn who="you"><p>{t.text}</p></Turn>
                  {reply && (
                    <Turn who="claude" badge={badgeFor(reply)}>
                      <Prose text={reply.text} streaming={inflight} />
                    </Turn>
                  )}
                </div>
              );
            })}
            {turns.length > 0 && !(live && live.live) && !turns[turns.length - 1].answer && (
              <p className="tiny faint" style={{ margin: "0 0 12px" }}>
                Live session unavailable — {(live && live.reason) || "no function reachable"}.
              </p>
            )}

            <Composer busy={!!streaming} onSend={send} live={live} model={model}
                      setModel={setModel} />
          </div>
        </main>
      </div>
    </div>
  );
}
