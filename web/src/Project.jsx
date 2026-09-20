// Shell B: one project. Rail, centre, artifact panel.
//
// Everything in here is scoped to a single project id out of the route. The
// rail header is the *project* -- back arrow, name, chevron, collapse -- and
// New is the project-scoped item beneath it, which is what the host does.
// The product name is not in this rail, because the product and the project
// are not one object.
//
// Below those sits Rounds, the one item that is new, and then the session
// list. A session is a unit of work: a round starts one, and a person can
// start an ad-hoc one at any time. Both kinds are in the same list.
//
// The host's Search, Customize, Files and Compute were drawn here once, and
// are gone: nothing in this build is behind them, and a button that does
// nothing is a claim the page cannot keep.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AdHoc from "./AdHoc.jsx";
import Panel from "./Panel.jsx";
import RoundGraph from "./RoundGraph.jsx";
import Session from "./Session.jsx";
import * as agent from "./agent.js";
import * as router from "./router.js";
import * as rt from "./runtime.js";
import { Badge, Hash, elapsed, projectTitle, templateTitle } from "./lib.jsx";

// Under this width the artifact panel is a sheet over the conversation rather
// than a column beside it. The same number is in styles.css; the stylesheet
// decides how the sheet is drawn and this decides whether it starts open.
const NARROW = "(max-width: 980px)";

function useMedia(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatches(mq.matches);
    mq.addEventListener("change", on);
    on();
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return matches;
}

// One draggable edge: the rail's right, the panel's left. `measure` turns
// the pointer's x into the width that edge implies; the result is clamped,
// kept per browser under `key`, and null means the stylesheet's default.
// Storage that is missing or refused just means the default. The grip
// captures the pointer, so the drag keeps going when it leaves the strip;
// double-click puts the width back.
function useDragWidth({ key, min, max, measure }) {
  const [width, setWidth] = useState(() => {
    try {
      const w = Number(localStorage.getItem(key));
      return w >= min ? w : null;
    } catch {
      return null;
    }
  });
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    if (dragging) return;
    try {
      if (width) localStorage.setItem(key, String(width));
      else localStorage.removeItem(key);
    } catch { /* the width lasts until the reload, then */ }
  }, [dragging, key, width]);
  const grip = {
    onPointerDown: (e) => { e.currentTarget.setPointerCapture(e.pointerId); setDragging(true); },
    onPointerMove: (e) => {
      if (!dragging) return;
      setWidth(Math.round(Math.min(Math.max(measure(e.clientX), min), max())));
    },
    onPointerUp: () => setDragging(false),
    onPointerCancel: () => setDragging(false),
    onDoubleClick: () => setWidth(null),
  };
  return { width, dragging, grip };
}

export default function Project({ route, runtime, campaign, proposal, live, reprobe,
                                  model, setModel }) {
  const pid = route.project;
  const [view, setView] = useState(null);
  // The agent turn in flight, for the stream to render as it happens. It is
  // the same object the loop mutates, copied on every step so React sees it;
  // the stored copy lives beside the session's asks and is what a reload
  // shows.
  const [agentTurn, setAgentTurn] = useState(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const inFlight = useRef(null);
  // Signed transcripts live here and nowhere else, one per session: the
  // diagnosis, every question asked after it and the ruling that sends it
  // back continue the same conversation, so a follow-up can refer to what
  // was said. The decision record is the durable state; the conversation
  // that produced it is not, and a transcript that went through the
  // project's canonical JSON would no longer verify. After a reload the next
  // turn in a session starts a fresh transcript from the record.
  const transcripts = useRef(new Map());
  const [tab, setTab] = useState("Batch");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [drops, setDrops] = useState([]);
  const [dropNotes, setDropNotes] = useState({});
  const [traced, setTraced] = useState(null);
  const [lineage, setLineage] = useState(null);
  const [artifacts, setArtifacts] = useState({});
  const [saved, setSaved] = useState(null);
  const [collapsed, setCollapsed] = useState(false);
  // The artifact panel: a column beside the conversation that can be hidden
  // and dragged, or under the narrow breakpoint a sheet that starts closed
  // and is opened from the title bar. Crossing the breakpoint resets it.
  const narrow = useMedia(NARROW);
  const [panelOpen, setPanelOpen] = useState(!narrow);
  useEffect(() => { setPanelOpen(!narrow); }, [narrow]);
  // Both edges drag. The rail's left is the viewport's, so its width is the
  // pointer's x; the panel is flush with the right edge, so its width is the
  // distance from the pointer to that edge.
  const rail = useDragWidth({ key: "wb.rail-w", min: 180,
                              max: () => Math.min(420, window.innerWidth * 0.3),
                              measure: (x) => x });
  const panel = useDragWidth({ key: "wb.panel-w", min: 340,
                               max: () => window.innerWidth * 0.6,
                               measure: (x) => window.innerWidth - x });
  const resizing = rail.dragging || panel.dragging;
  useEffect(() => {
    if (!(narrow && panelOpen)) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setPanelOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [narrow, panelOpen]);
  const togglePanel = useCallback(() => setPanelOpen((o) => !o), []);

  const refresh = useCallback(() => {
    try {
      setView(rt.call("view", { project: pid }));
      setError(null);
    } catch (err) {
      setError(String(err.message || err));
    }
  }, [pid]);

  useEffect(refresh, [refresh]);

  /* where a project opens ---------------------------------------------------
     Not a lobby: a project that has a round waiting on a ruling opens on that
     ruling, and the round graph is one click away rather than in the way. */
  useEffect(() => {
    if (!view) return;
    if (route.kind === "project") {
      router.replace({ kind: "session", project: pid, id: router.landing(view) });
    } else if (route.kind === "session" && route.id === "new") {
      const rec = rt.call("new_session", { project: pid, created: new Date().toISOString() });
      setView(rt.call("view", { project: pid }));
      router.replace({ kind: "session", project: pid, id: rec.id });
    }
  }, [view, route.kind, route.id, pid]);

  const sessionId = route.kind === "session" ? route.id : null;
  const round = sessionId && /^r\d+$/.test(sessionId) ? Number(sessionId.slice(1)) : null;
  const roundView = view?.rounds.find((r) => r.round === round) || null;

  // The turns asked in this session, read back from it. Both kinds of session
  // store them the same way, beside the command log, so a reload keeps them.
  const stored = useMemo(() => {
    if (!view || !sessionId || sessionId === "new") return null;
    try {
      return rt.call("session", { session_id: sessionId, project: pid });
    } catch {
      return null;
    }
  }, [view, sessionId, pid]);

  // What the round did, for a round that did it somewhere else. The command
  // log is this tab's; a round that ran before the tab was opened has none,
  // and its story is in its artifacts.
  const history = useMemo(() => {
    if (!view || !round) return null;
    return rt.safeCall("round_history", { round_id: round, project: pid }) || null;
  }, [view, round, pid]);

  /* artifacts for whichever round is open ---------------------------------- */
  useEffect(() => {
    if (!view || !round) { setArtifacts({}); return; }
    try {
      const batch = rt.call("artifact", { kind: "batches", round_id: round, project: pid });
      const decision = rt.call("artifact", { kind: "decision", round_id: round, project: pid });
      const lastScored = [...view.rounds].reverse().find((r) => r.refs.evaluation);
      const evaluation = lastScored
        ? rt.call("artifact", { kind: "batches", round_id: lastScored.round,
                                suffix: ".eval", project: pid })
        : null;
      const ids = batch ? batch.slots.map((s) => s.design_id) : [];
      const designs = ids.length
        ? Object.fromEntries(rt.call("designs", { ids, project: pid })
          .map((d) => [d.design_id, d]))
        : {};
      setArtifacts({ batch, decision, evaluation, designs });
    } catch (err) {
      setError(String(err.message || err));
    }
  }, [view, round, pid]);

  const onTrace = useCallback((item) => {
    setTraced(item);
    setLineage(null);
    if (!item) return;
    setTab("Notebook");
    setPanelOpen(true);
    try {
      setLineage(rt.call("lineage", { dotted: item.source }));
    } catch (err) {
      setLineage({ error: String(err.message || err) });
    }
  }, []);

  const act = useCallback(async (fn) => {
    setBusy(true);
    setError(null);
    let out = null;
    try {
      await rt.paint();
      out = fn();
      setView(rt.call("view", { project: pid }));
      setSaved(rt.saveOverlay());
    } catch (err) {
      setError(`${err.message}${err.traceback ? `\n${err.traceback}` : ""}`);
    } finally {
      setBusy(false);
    }
    return out;
  }, [pid]);

  /* the agent ------------------------------------------------------------
     One loop, two sources, both through web/src/agent.js. Live goes through
     the function; replay steps the shipped record. Either way every tool
     call runs here, and the turn is stored beside the session's asks as it
     progresses so a reload shows what happened. */
  const persist = useCallback((sid, t) => {
    if (!sid) return;
    // A turn carries its transcript only once it is done, so a stopped turn
    // leaves the session's conversation where the last finished one left it.
    if (t.transcript) {
      transcripts.current.set(sid, { transcript: t.transcript, pending: t.pending || null });
    }
    const steps = t.steps.map((s) => (s.entry ? { ...s, entry: undefined } : s));
    try {
      rt.call("agent_turn_save", { session_id: sid, project: pid, at: t.at,
                                   turn: { ...t, steps, transcript: null, pending: null } });
    } catch { /* the stream still renders; the reload will not */ }
  }, [pid]);
  const conversation = (sid) => transcripts.current.get(sid) || { transcript: null, pending: null };

  const drive = useCallback(async (fn) => {
    setAgentBusy(true);
    setError(null);
    let out = null;
    try {
      await rt.paint();
      out = await fn();
      setView(rt.call("view", { project: pid }));
      setSaved(rt.saveOverlay());
    } catch (err) {
      setError(`${err.message}${err.traceback ? `\n${err.traceback}` : ""}`);
    } finally {
      setAgentBusy(false);
      setAgentTurn(null);
      inFlight.current = null;
      if (reprobe) reprobe();
    }
    return out;
  }, [pid, reprobe]);

  const hooks = useCallback((sid, extra = {}) => ({
    // The loop mutates one turn object; the state holds a shallow copy taken
    // on every step and every text delta, so the stream re-renders while the
    // stored copy is written only when a step lands.
    emit: () => { if (inFlight.current) setAgentTurn({ ...inFlight.current }); },
    save: (t) => {
      Object.assign(t, extra);
      inFlight.current = t;
      setAgentTurn({ ...t });
      persist(sid, t);
    },
  }), [persist]);

  const diagnose = useCallback((mode, { pass = 1, ruling = null } = {}) =>
    drive(async () => {
      const turn = mode === "live"
        ? await agent.runLive({ kind: "diagnose", project: pid, round, session: sessionId,
                                model, ruling, ...conversation(sessionId),
                                call: rt.call, ...hooks(sessionId) })
        : await agent.runReplay({ project: pid, round, session: sessionId, plan: proposal,
                                  pass, call: rt.call, ...hooks(sessionId) });
      setTab("Decision");
      return turn;
    }), [drive, hooks, pid, round, sessionId, model, proposal]);

  const askLive = useCallback((question, chosenModel, label) =>
    drive(() => agent.runLive({
      kind: "ask", project: pid, round: round ?? null, session: sessionId, question,
      model: chosenModel || model, ...conversation(sessionId),
      call: rt.call, ...hooks(sessionId, label ? { label } : {}),
    })), [drive, hooks, pid, round, sessionId, model]);

  const ctx = useMemo(() => ({
    project: pid, view, campaign, round, roundView, sessionId,
    batch: artifacts.batch, decision: artifacts.decision, evaluation: artifacts.evaluation,
    designs: artifacts.designs || {}, log: view?.log || [],
    busy: busy || agentBusy, error, onTrace, traced, lineage,
    drops, setDrops, dropNotes, setDropNotes,
    proposal, live, model, setModel, agentTurn, agentBusy,
    panel: { open: panelOpen, narrow, toggle: togglePanel },
    onDiagnoseLive: () => diagnose("live"),
    onReplay: (pass = 1) => diagnose("replay", { pass }),
    onPushbackLive: (ruling) => diagnose("live", { ruling }),
    onAskLive: askLive,
    onApprove: (by) => act(() => {
      const r = rt.call("approve", { round_id: round, by, project: pid, session: sessionId,
                                     drops, drop_notes: drops.map((d) => dropNotes[d] || "") });
      setDrops([]);
      setTab("Progress");
      return r;
    }),
    onRelease: () => act(() =>
      rt.call("release_run", { round_id: round, project: pid, session: sessionId })),
    onDiagnostic: (test, args) => act(() =>
      rt.call("diagnostic", { round_id: round, test, project: pid, session: sessionId,
                              ...args })),
    hasReplay: !!(proposal && round === proposal.round),
    onRule: (verdict, by, note, request) => act(() =>
      rt.call("rule", { round_id: round, verdict, by, note, request, project: pid,
                        session: sessionId })),
    onAdvance: () => act(() => {
      const next = rt.call("act_and_advance", { round_id: round, project: pid,
                                                session: sessionId });
      router.go({ kind: "session", project: pid,
                  id: `r${next.pending_round || round + 1}` });
      setTab("Batch");
    }),
    onContinue: () => act(() => {
      const next = rt.call("continue_unflagged", { round_id: round, project: pid,
                                                   session: sessionId });
      router.go({ kind: "session", project: pid,
                  id: `r${next.pending_round || round + 1}` });
      setTab("Batch");
    }),
    onAsk: (key, forRound, inSession) => act(() =>
      rt.call("ask", { key, project: pid, round_id: forRound ?? null,
                       session_id: inSession || null, at: new Date().toISOString() })),
    onDownload: (path) => {
      const file = rt.call("download", { path });
      const url = URL.createObjectURL(new Blob([file.text], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      a.click();
      URL.revokeObjectURL(url);
    },
    refresh,
  }), [pid, view, campaign, round, roundView, sessionId, artifacts, busy, agentBusy, error,
       onTrace, traced, lineage, drops, dropNotes, proposal, live, model, setModel, agentTurn,
       panelOpen, narrow, togglePanel, diagnose, askLive, act, refresh]);

  const suggestionsFor = useMemo(
    () => (view ? rt.safeCall("suggested_asks", { project: pid, round_id: round }) : []),
    [view, pid, round]);

  if (!view) {
    return (
      <div className="boot"><div className="boot-card card">
        <h2>No such project</h2>
        <p className="small muted">
          Nothing in this browser is called <span className="mono">{pid}</span>.
        </p>
        {error && <p className="err" style={{ marginTop: 10 }}>{error}</p>}
        <a className="btn" style={{ marginTop: 12 }} href="#/">Home</a>
      </div></div>
    );
  }

  const sessions = view.sessions || [];
  const active = sessions.filter((s) => s.needs_you || s.at_lab || s.kind === "adhoc");
  const older = sessions.filter((s) => !active.includes(s));
  const suggestions = suggestionsFor;

  const SessionLink = ({ s }) => (
    <a key={s.id} className="rail-session"
       aria-current={sessionId === s.id}
       href={router.href({ kind: "session", project: pid, id: s.id })}>
      <span className="t">
        <span className={`sess-dot ${s.kind === "round" ? "round" : "adhoc"}`} />
        <span className="ellipsis">{s.title}</span>
        {s.flagged && <Badge kind="flag">!</Badge>}
      </span>
      <span className="s">{s.subtitle} · {elapsed(s.updated)}</span>
    </a>
  );

  const showPanel = route.kind === "session" && panelOpen;
  const widths = {};
  if (rail.width) widths["--rail-w"] = `${rail.width}px`;
  if (panel.width) widths["--panel-w"] = `${panel.width}px`;

  return (
    <div className="shell">
      <div className={`body${resizing ? " is-resizing" : ""}`} style={widths}>
        <nav className={`rail${collapsed ? " is-collapsed" : ""}`}>
          <div className="rail-head">
            <a className="rail-back" href="#/" title="All projects">←</a>
            <button className="rail-project" onClick={() => router.go({ kind: "rounds",
                                                                        project: pid })}>
              <span className="ellipsis">{projectTitle(view.project)}</span>
              <span className="chev">⌄</span>
            </button>
            <button className="rail-collapse" onClick={() => setCollapsed(!collapsed)}
                    title="Collapse">▤</button>
          </div>
          <div className="rail-sub mono tiny faint">{view.project.id}</div>

          <a className="rail-item" href={router.href({ kind: "session", project: pid,
                                                       id: "new" })}>
            <span className="ic">✦</span><span>New</span>
          </a>
          <a className="rail-item is-new" aria-current={route.kind === "rounds"}
             href={router.href({ kind: "rounds", project: pid })}>
            <span className="ic">⌸</span><span>Rounds</span>
          </a>

          <div className="rail-group hide-narrow">
            <div className="rail-label">Sessions</div>
            <div className="rail-sessions">
              {active.map((s) => <SessionLink key={s.id} s={s} />)}
              {older.length > 0 && <div className="rail-label">Earlier</div>}
              {older.map((s) => <SessionLink key={s.id} s={s} />)}
            </div>
          </div>

          <div className="rail-foot hide-narrow">
            <div style={{ padding: "6px 8px 0" }}>
              {templateTitle(view.project.template)} v{view.project.template.version}<br />
              Python {runtime.python} · numpy {runtime.numpy}<br />
              bundle <Hash value={view.manifest.hash} />
              {saved?.error && <><br /><span className="err">progress not saved</span></>}
            </div>
            <button className="btn small" style={{ margin: "8px 8px 0" }}
                    onClick={() => { rt.clearOverlay(); window.location.reload(); }}>
              ⚙ Reset this browser
            </button>
          </div>
        </nav>
        {!collapsed && !narrow && (
          <div className="grip" role="separator" aria-orientation="vertical"
               title="Drag to resize; double-click to reset" {...rail.grip} />
        )}

        <main className={`centre${route.kind === "rounds" ? " wide" : ""}`}>
          {route.kind === "rounds" && (
            <RoundGraph ctx={ctx}
                        onOpenRound={(r) => router.go({ kind: "session", project: pid,
                                                        id: `r${r}` })} />
          )}
          {route.kind === "session" && round !== null && roundView && (
            <Session ctx={ctx} stored={stored} history={history} suggestions={suggestions} />
          )}
          {route.kind === "session" && round === null && route.id !== "new" && (
            <AdHoc ctx={ctx} stored={stored} suggestions={suggestions} />
          )}
        </main>

        {showPanel && narrow && <div className="scrim" onClick={togglePanel} />}
        {showPanel && !narrow && (
          <div className="grip" role="separator" aria-orientation="vertical"
               title="Drag to resize; double-click to reset" {...panel.grip} />
        )}
        {showPanel && (
          <Panel tab={tab} setTab={setTab} ctx={ctx} onClose={narrow ? togglePanel : null} />
        )}
      </div>
    </div>
  );
}
