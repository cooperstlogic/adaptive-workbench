// The top of the application: boot Python, then hand off to one of two shells.
//
// **Two shells, not one.** Home is full-bleed and centred, with no rail and
// no artifact panel, because a home screen drawn inside a project's chrome is
// a home screen that belongs to that project. A project gets the three-region
// layout -- rail, centre, panel -- and everything in it is scoped to that one
// project. The first load used to draw round 4's batch table beside a
// greeting, for a round nobody had opened.
//
// Nothing below knows about the demo campaign in particular. A project id
// comes out of the route, and both kinds -- a templated project the Python
// side holds, and a blank one that lives only in localStorage -- are opened
// the same way.

import { useCallback, useEffect, useState } from "react";
import BlankProject from "./BlankProject.jsx";
import Home from "./Home.jsx";
import NewProject from "./NewProject.jsx";
import Project from "./Project.jsx";
import * as blank from "./blank.js";
import * as router from "./router.js";
import * as rt from "./runtime.js";
import { APP } from "./lib.jsx";

export default function App() {
  const [boot, setBoot] = useState({ steps: [], done: false, error: null });
  const [runtime, setRuntime] = useState(null);
  const [route, setRoute] = useState(() => router.parse(window.location.hash));
  const [campaign, setCampaign] = useState(null);
  const [proposal, setProposal] = useState(null);
  // Bumped whenever a project is created or deleted, so the home screen and
  // the rail re-read the list without either of them owning it.
  const [epoch, setEpoch] = useState(0);
  const bump = useCallback(() => setEpoch((n) => n + 1), []);

  useEffect(() => router.subscribe(setRoute), []);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const info = await rt.boot((text) => live
          && setBoot((b) => ({ ...b, steps: [...b.steps, text] })));
        if (!live) return;
        setRuntime(info);
        setBoot((b) => ({ ...b, done: true }));
      } catch (err) {
        if (live) setBoot((b) => ({ ...b, error: String(err.message || err) }));
      }
    })();
    const base = import.meta.env.BASE_URL;
    fetch(`${base}assets/campaign.json`)
      .then((r) => r.json()).then((c) => live && setCampaign(c)).catch(() => {});
    fetch(`${base}workbench/reference/decision_004.proposal.json`)
      .then((r) => r.json()).then((p) => live && setProposal(p)).catch(() => {});
    return () => { live = false; };
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

  if (!boot.done) {
    return (
      <div className="boot"><div className="boot-card">
        <h2 className="brandmark">{APP}</h2>
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

  const shared = { runtime, campaign, proposal, epoch, bump };

  if (route.kind === "new" || route.kind === "templates") {
    return <NewProject {...shared} />;
  }

  if (route.kind === "project" || route.kind === "session" || route.kind === "rounds") {
    // A blank project has no Python state at all, so it gets its own shell
    // rather than a templated shell with everything in it disabled.
    const asBlank = blank.all().find((p) => p.id === route.project);
    if (asBlank) return <BlankProject route={route} project={asBlank} {...shared} />;
    return <Project key={route.project} route={route} {...shared} />;
  }

  return <Home {...shared} />;
}
