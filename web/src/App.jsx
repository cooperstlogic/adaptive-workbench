// The shell. Three regions and a home screen, borrowed from Claude Science so
// that the argument is made before anyone reads a word of copy — and labelled
// a wireframe at the top of the page, because failure mode one applies to the
// frame as much as to the contents.

import { useCallback, useEffect, useState } from "react";
import Home, { Gallery } from "./Home.jsx";
import Panel, { TABS } from "./Panel.jsx";
import RoundGraph from "./RoundGraph.jsx";
import Session from "./Session.jsx";
import { Badge, Hash, elapsed } from "./lib.jsx";
import * as rt from "./runtime.js";

const RAIL = [
  { id: "new", icon: "✦", label: "New" },
  { id: "search", icon: "⌕", label: "Search" },
  { id: "customize", icon: "◉", label: "Customize" },
  { id: "files", icon: "▤", label: "Files" },
  { id: "compute", icon: "⚙", label: "Compute" },
];

const HOST_ONLY = {
  search: ["Search", "The host has it. Nothing in this wireframe is behind it, so it is "
    + "drawn and not wired."],
  customize: ["Customize", "Skills, connectors and project instructions live here in the "
    + "host. This artifact installs into that surface — see the README's Claude Science "
    + "section — rather than replacing it."],
  files: ["Files", "The host has a Files directory with persistent folder grants. The "
    + "project directory in this browser is the same idea, and it is not the gap: "
    + "the gap is that nothing renders the graph those files form."],
  compute: ["Compute", "The host has persistent kernels. The kernel here is Pyodide, "
    + "running the repository's own modules, and the Notebook tab shows exactly which "
    + "function produced any number on screen."],
  new: ["New", "In the host this starts a chat. Here it would start a project from a "
    + "template — open the gallery from the home screen."],
};

export default function App() {
  const [boot, setBoot] = useState({ steps: [], done: false, error: null });
  const [runtime, setRuntime] = useState(null);
  const [view, setView] = useState(null);
  const [route, setRoute] = useState({ kind: "home" });
  const [tab, setTab] = useState("Batch");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [gallery, setGallery] = useState(false);
  const [campaign, setCampaign] = useState(null);
  const [artifacts, setArtifacts] = useState({});
  const [traced, setTraced] = useState(null);
  const [lineage, setLineage] = useState(null);
  const [drops, setDrops] = useState([]);
  const [dropNotes, setDropNotes] = useState({});
  const [saved, setSaved] = useState(null);

  /* boot ------------------------------------------------------------------ */
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const info = await rt.boot((text) => live
          && setBoot((b) => ({ ...b, steps: [...b.steps, text] })));
        if (!live) return;
        setRuntime(info);
        setView(rt.call("view"));
        setBoot((b) => ({ ...b, done: true }));
      } catch (err) {
        if (live) setBoot((b) => ({ ...b, error: String(err.message || err) }));
      }
    })();
    fetch(`${import.meta.env.BASE_URL}assets/campaign.json`)
      .then((r) => r.json()).then((c) => live && setCampaign(c)).catch(() => {});
    return () => { live = false; };
  }, []);

  const activeRound = route.kind === "round" ? route.round : view?.active_round;
  const roundView = view?.rounds.find((r) => r.round === activeRound) || null;

  /* artifacts for whichever round is open ---------------------------------- */
  useEffect(() => {
    if (!view || !activeRound) return;
    try {
      const batch = rt.call("artifact", { kind: "batches", round_id: activeRound });
      const decision = rt.call("artifact", { kind: "decision", round_id: activeRound });
      const lastScored = [...view.rounds].reverse().find((r) => r.refs.evaluation);
      const evaluation = lastScored
        ? rt.call("artifact", { kind: "batches", round_id: lastScored.round, suffix: ".eval" })
        : null;
      const ids = batch ? batch.slots.map((s) => s.design_id) : [];
      const designs = ids.length
        ? Object.fromEntries(rt.call("designs", { ids }).map((d) => [d.design_id, d]))
        : {};
      setArtifacts({ batch, decision, evaluation, designs });
    } catch (err) {
      setError(String(err.message || err));
    }
  }, [view, activeRound]);

  /* the Notebook tab ------------------------------------------------------- */
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

  /* actions ---------------------------------------------------------------- */
  const act = useCallback(async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await rt.paint();
      fn();
      setView(rt.call("view"));
      setSaved(rt.saveOverlay());
    } catch (err) {
      setError(`${err.message}${err.traceback ? `\n${err.traceback}` : ""}`);
    } finally {
      setBusy(false);
    }
  }, []);

  const onApprove = (by) => act(() => {
    rt.call("approve", {
      round_id: activeRound, by,
      drops, drop_notes: drops.map((d) => dropNotes[d] || ""),
    });
    setDrops([]);
    setTab("Progress");
  });

  const onDiagnose = () => act(() => {
    const proposal = artifacts.proposal || fetchedProposal;
    rt.call("propose", {
      round_id: activeRound,
      payload: {
        trigger: proposal.trigger, hypotheses: proposal.hypotheses,
        recommendation: proposal.recommendation, ad_hoc: proposal.ad_hoc,
      },
    });
    setTab("Decision");
  });

  const onDiagnostic = (test, args) => act(() => {
    rt.call("diagnostic", { round_id: activeRound, test, ...args });
  });

  const onRule = (verdict, by, note, request) => act(() => {
    rt.call("rule", { round_id: activeRound, verdict, by, note, request });
  });

  const onAdvance = () => act(() => {
    const next = rt.call("act_and_advance", { round_id: activeRound });
    setRoute({ kind: "round", round: (next.pending_round || activeRound + 1) });
    setTab("Batch");
  });

  const onContinue = () => act(() => {
    const next = rt.call("continue_unflagged", { round_id: activeRound });
    setRoute({ kind: "round", round: (next.pending_round || activeRound + 1) });
    setTab("Batch");
  });

  const onReset = () => {
    rt.clearOverlay();
    window.location.reload();
  };

  /* the committed proposal, fetched once ----------------------------------- */
  const [fetchedProposal, setFetchedProposal] = useState(null);
  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}workbench/reference/decision_004.proposal.json`)
      .then((r) => r.json()).then(setFetchedProposal).catch(() => {});
  }, []);

  if (boot.error) {
    return (
      <div className="boot"><div className="boot-card card">
        <h2>The Python runtime did not start</h2>
        <p className="err" style={{ marginTop: 10 }}>{boot.error}</p>
        <p className="small muted">
          Everything on this page runs in your browser, so there is no server to blame.
          A reload is the first thing to try.
        </p>
      </div></div>
    );
  }

  if (!boot.done || !view) {
    return (
      <div className="boot"><div className="boot-card">
        <h2>Adaptive optimization workbench</h2>
        <p className="muted">
          Starting Python in your browser. The project, the model code and the simulated lab
          are the repository's own files; nothing is sent anywhere.
        </p>
        <div className="boot-steps">
          {boot.steps.map((s, i) => (
            <div className="boot-step" key={i}>
              <span className="boot-dot" />
              <b>{s}</b>
            </div>
          ))}
          <div className="boot-step"><span className="busy" /></div>
        </div>
      </div></div>
    );
  }

  const ctx = {
    view, campaign, round: activeRound, roundView,
    batch: artifacts.batch, decision: artifacts.decision, evaluation: artifacts.evaluation,
    designs: artifacts.designs || {}, log: view.log,
    busy, error, onTrace, traced, lineage,
    drops, setDrops, dropNotes, setDropNotes,
    onApprove, onDiagnostic,
    // The recorded diagnosis is round 4's. Another flagged round gets the
    // library and an honest sentence, not round 4's reasoning wearing its number.
    onDiagnose: (fetchedProposal && activeRound === fetchedProposal.round)
      ? onDiagnose : undefined,
    onRule, onAdvance, onContinue,
  };

  const sessions = [...view.rounds].reverse();
  const stub = route.kind === "stub" ? HOST_ONLY[route.id] : null;

  return (
    <div className="shell">
      <div className="wirebar">
        <b>Wireframe</b>
        <span>
          The chrome imitates Claude Science, to show where this layer would live. The
          Python, the project state and the hashes inside it are real and are running in
          this tab. Every affinity value is synthetic.
        </span>
      </div>

      <div className="body">
        <nav className="rail">
          <div className="rail-brand">
            <div className="mark">Adaptive workbench</div>
            <div className="tiny faint">{view.project.id}</div>
          </div>
          {RAIL.map((item) => (
            <button key={item.id} className="rail-item"
                    aria-current={route.kind === "stub" && route.id === item.id}
                    onClick={() => (item.id === "new"
                      ? setGallery(true) : setRoute({ kind: "stub", id: item.id }))}>
              <span className="ic">{item.icon}</span>{item.label}
            </button>
          ))}
          <button className="rail-item is-new" aria-current={route.kind === "rounds"}
                  onClick={() => setRoute({ kind: "rounds" })}>
            <span className="ic">⌸</span>Rounds
            <span className="rail-new-tag">new</span>
          </button>

          <div className="rail-group hide-narrow">
            <div className="rail-label">Active</div>
            <div className="rail-sessions">
              {sessions.filter((r) => r.status !== "complete").map((r) => (
                <button key={r.round} className="rail-session"
                        aria-current={route.kind === "round" && route.round === r.round}
                        onClick={() => setRoute({ kind: "round", round: r.round })}>
                  <span className="t">
                    Round {r.round} · {r.status.split(",")[0]}
                    {r.flagged && <Badge kind="flag">!</Badge>}
                  </span>
                  <span className="s">{elapsed(r.updated)}</span>
                </button>
              ))}
              <div className="rail-label">Older</div>
              {sessions.filter((r) => r.status === "complete").map((r) => (
                <button key={r.round} className="rail-session"
                        aria-current={route.kind === "round" && route.round === r.round}
                        onClick={() => setRoute({ kind: "round", round: r.round })}>
                  <span className="t">Round {r.round} · {r.verdict ? "ruled" : "batch approved"}</span>
                  <span className="s">{elapsed(r.updated)}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="rail-foot hide-narrow">
            <button className="rail-item" onClick={() => setRoute({ kind: "home" })}>
              <span className="ic">⌂</span>Home
            </button>
            <div style={{ padding: "6px 8px 0" }}>
              Python {runtime.python} · numpy {runtime.numpy}<br />
              pyodide {runtime.pyodide}<br />
              bundle <Hash value={view.manifest.hash} />
              {saved?.error && <><br /><span className="err">progress not saved</span></>}
            </div>
            <button className="btn small" style={{ margin: "8px 8px 0" }} onClick={onReset}>
              Reset to round 4
            </button>
          </div>
        </nav>

        <main className={`centre${route.kind === "rounds" ? " wide" : ""}`}>
          {route.kind === "home" && (
            <Home ctx={ctx}
                  onOpenRound={(r) => { setRoute({ kind: "round", round: r }); setTab("Batch"); }}
                  onOpenGraph={() => setRoute({ kind: "rounds" })}
                  onNewProject={() => setGallery(true)} />
          )}
          {route.kind === "rounds" && (
            <RoundGraph ctx={ctx}
                        onOpenRound={(r) => setRoute({ kind: "round", round: r })} />
          )}
          {route.kind === "round" && roundView && <Session ctx={ctx} />}
          {stub && (
            <div className="centre-inner">
              <h2>{stub[0]}</h2>
              <p className="muted" style={{ maxWidth: 560 }}>{stub[1]}</p>
              <p className="note" style={{ marginTop: 18 }}>
                Everything above <b>Rounds</b> in the rail already exists in Claude Science.
                Exactly one item is new, and it is the one holding the campaign.
              </p>
              <button className="btn" style={{ marginTop: 14 }}
                      onClick={() => setRoute({ kind: "rounds" })}>
                Open Rounds
              </button>
            </div>
          )}
        </main>

        {(route.kind === "round" || route.kind === "home") && (
          <Panel tab={tab} setTab={setTab} ctx={ctx} />
        )}
      </div>

      {gallery && <Gallery onClose={() => setGallery(false)} />}
    </div>
  );
}
