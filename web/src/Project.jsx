// Shell B: one project. Rail, centre, artifact panel.
//
// Everything in here is scoped to a single project id out of the route. The
// rail header is the *project* -- back arrow, name, chevron, collapse -- and
// New / Search / Customize / Files / Compute are project-scoped items beneath
// it, which is what the host does. The product name is not in this rail,
// because the product and the project are not one object.
//
// Below those sits Rounds, the one item that is new, and then the session
// list. A session is a unit of work: a round starts one, and a person can
// start an ad-hoc one at any time. Both kinds are in the same list.
//
// The four host items are drawn and not wired: nothing in this build is
// behind Search, Customize, Files or Compute, and a rail item that opens an
// essay about what the host does there is an essay in the way of the round.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AdHoc from "./AdHoc.jsx";
import Panel from "./Panel.jsx";
import RoundGraph from "./RoundGraph.jsx";
import Session from "./Session.jsx";
import * as agent from "./agent.js";
import * as router from "./router.js";
import * as rt from "./runtime.js";
import { Badge, Hash, elapsed, projectTitle, templateTitle } from "./lib.jsx";

const RAIL = [
  { id: "search", icon: "⌕", label: "Search" },
  { id: "customize", icon: "◉", label: "Customize" },
  { id: "files", icon: "▤", label: "Files" },
  { id: "compute", icon: "⚙", label: "Compute" },
];

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
  // Signed transcripts live here and nowhere else. The decision record is the
  // durable state; the conversation that produced it is not, and a transcript
  // that went through the project's canonical JSON would no longer verify. A
  // push-back after a reload starts a fresh transcript from the record.
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
    if (t.transcript) transcripts.current.set(t.id, { transcript: t.transcript, pending: t.pending });
    const steps = t.steps.map((s) => (s.entry ? { ...s, entry: undefined } : s));
    try {
      rt.call("agent_turn_save", { session_id: sid, project: pid, at: t.at,
                                   turn: { ...t, steps, transcript: null, pending: null } });
    } catch { /* the stream still renders; the reload will not */ }
  }, [pid]);

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

  const diagnose = useCallback((mode, { pass = 1, ruling = null, transcript = null } = {}) =>
    drive(async () => {
      const turn = mode === "live"
        ? await agent.runLive({ kind: "diagnose", project: pid, round, session: sessionId,
                                model, ruling, transcript, call: rt.call, ...hooks(sessionId) })
        : await agent.runReplay({ project: pid, round, session: sessionId, plan: proposal,
                                  pass, call: rt.call, ...hooks(sessionId) });
      setTab("Decision");
      return turn;
    }), [drive, hooks, pid, round, sessionId, model, proposal]);

  const askLive = useCallback((question, chosenModel, label) =>
    drive(() => agent.runLive({
      kind: "ask", project: pid, round: round ?? null, session: sessionId, question,
      model: chosenModel || model, call: rt.call, ...hooks(sessionId, label ? { label } : {}),
    })), [drive, hooks, pid, round, sessionId, model]);

  const ctx = useMemo(() => ({
    project: pid, view, campaign, round, roundView, sessionId,
    batch: artifacts.batch, decision: artifacts.decision, evaluation: artifacts.evaluation,
    designs: artifacts.designs || {}, log: view?.log || [],
    busy: busy || agentBusy, error, onTrace, traced, lineage,
    drops, setDrops, dropNotes, setDropNotes,
    proposal, live, model, setModel, agentTurn, agentBusy,
    onDiagnoseLive: () => diagnose("live"),
    onReplay: (pass = 1) => diagnose("replay", { pass }),
    onPushbackLive: (ruling, priorId) => {
      const kept = priorId ? transcripts.current.get(priorId) : null;
      return diagnose("live", {
        ruling: { ...ruling, pending: kept ? kept.pending : undefined },
        transcript: kept ? kept.transcript : null, pass: 2,
      });
    },
    onAskLive: askLive,
    onApprove: (by) => act(() => {
      const r = rt.call("approve", { round_id: round, by, project: pid, session: sessionId,
                                     drops, drop_notes: drops.map((d) => dropNotes[d] || "") });
      setDrops([]);
      setTab("Progress");
      return r;
    }),
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
       diagnose, askLive, act, refresh]);

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

  return (
    <div className="shell">
      <div className="body">
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
            <span className="ic">✦</span>New
          </a>
          {RAIL.map((item) => (
            <button key={item.id} className="rail-item" title="Not wired in this prototype">
              <span className="ic">{item.icon}</span>{item.label}
            </button>
          ))}
          <a className="rail-item is-new" aria-current={route.kind === "rounds"}
             href={router.href({ kind: "rounds", project: pid })}>
            <span className="ic">⌸</span>Rounds
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

        <main className={`centre${route.kind === "rounds" ? " wide" : ""}`}>
          {route.kind === "rounds" && (
            <RoundGraph ctx={ctx}
                        onOpenRound={(r) => router.go({ kind: "session", project: pid,
                                                        id: `r${r}` })} />
          )}
          {route.kind === "session" && round !== null && roundView && (
            <Session ctx={ctx} stored={stored} suggestions={suggestions} />
          )}
          {route.kind === "session" && round === null && route.id !== "new" && (
            <AdHoc ctx={ctx} stored={stored} suggestions={suggestions} />
          )}
        </main>

        {route.kind === "session" && (
          <Panel tab={tab} setTab={setTab} ctx={ctx} />
        )}
      </div>
    </div>
  );
}
