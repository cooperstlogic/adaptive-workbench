// Starting a project: blank, or from a template.
//
// **The configuration screen is mostly locked, and that is the argument
// rather than a shortcut.** Every locked row is read out of `template.json`,
// so the screen renders the declaration instead of disabling a form. A
// template is not a prompt: it carries the objectives schema, the constraint
// ruleset enforced in code, the permitted recipes and diagnostics, and the
// batch policy — so what a project means does not depend on how well somebody
// phrased a request, and two people who instantiate it get the same project.
//
// **Creating it runs three real commands in Pyodide.** `init_project.py` is
// the CLI's own entry point, mirrored into the bundle, and round 1 then goes
// through `generate_candidates.py` and `select_batch.py` like every other
// round. A project instantiated here is byte-identical to one instantiated in
// a terminal — check.py compares them file by file, which is decision 108 in
// the form a machine can check.
//
// **A blank project is the control arm.** It never touches Python, because
// there is nothing for `project.load()` to read: no objectives, no
// constraints, no batch policy. It opens on an empty chat. Putting the two
// side by side, both created live in the same interface, is the difference
// between asserting the gap and showing it.

import { useEffect, useMemo, useState } from "react";
import * as blank from "./blank.js";
import * as router from "./router.js";
import * as rt from "./runtime.js";
import { Validation } from "./Panel.jsx";
import { APP, Badge, Empty, templateTitle } from "./lib.jsx";

/** The locked declaration, row by row, read from the template file itself.
 *
 *  A few rows are plausible rather than real — the assay platform and the
 *  plate format are not declared anywhere in this build — and they are marked
 *  so, because failure mode one applies to a configuration screen as much as
 *  to anything else.
 */
const MOCK_TIP = "Not declared anywhere in this build.";

function declaration(tpl) {
  const lead = tpl.lead;
  const c = tpl.constraints;
  const b = tpl.batch;
  const region = lead.editable_region;
  const window = lead.sequence.slice(region[0], region[1]);
  return [
    ["Template", `${templateTitle(tpl)} · v${tpl.version}`, "template.json"],
    ["Input antibody", `${lead.name} ${lead.chain}, ${lead.sequence.length} aa`,
      "template.json"],
    ["Target", "HER2", "template.json"],
    ["Editable region", `VH ${region[0]}–${region[1]} · ${window}`, "template.json"],
    ["Constraints", `≤ ${c.max_mutations} mutations · forbidden ${
      c.forbidden_motifs.join(", ")}`, "template.json"],
    ["Objectives", tpl.objectives.map((o) => `${o.name} ${
      o.direction === "maximize" ? "↑" : "↓"}${
      o.threshold !== undefined ? ` ≤ ${o.threshold}` : ""}`).join(" · "), "template.json"],
    ["Source data", "Registry (LIMS) · Bioprovider — both connected",
      ".claude-plugin/plugin.json"],
    ["Assay", "SPR · 24-well plates, 2 per round", "mock"],
    ["Model selection", `${tpl.model_recipes.join(" + ")} — competed, lowest held-out `
      + "NLPD wins", "template.json"],
    ["Batch policy", `${b.size} wells · ${b.controls} control · ${b.replicates} replicate · `
      + `${b.exploration_slots} exploration`, "template.json"],
    ["Round 1 policy", `${b.round1_policy.replace(/_/g, " ")} · ${b.round1_scan_residues}`,
      "template.json"],
    ["Diagnostics", tpl.diagnostics.join(", "), "template.json"],
  ];
}

export default function NewProject({ bump, campaign }) {
  const [templates, setTemplates] = useState(null);
  const [reqs, setReqs] = useState(null);
  const [picked, setPicked] = useState(null);
  const [name, setName] = useState("trastuzumab-affinity-2");
  const [team, setTeam] = useState("d.webster");
  const [blankTitle, setBlankTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [steps, setSteps] = useState([]);

  useEffect(() => {
    try {
      setTemplates(rt.call("templates"));
    } catch (err) {
      setError(String(err.message || err));
    }
    fetch(`${import.meta.env.BASE_URL}workbench/reference/requirements.json`)
      .then((r) => r.json()).then(setReqs).catch(() => {});
  }, []);

  const live = useMemo(
    () => (templates || []).filter((t) => t.status !== "stub"), [templates]);
  const chosen = (templates || []).find((t) => t.id === picked) || null;

  const createTemplated = async () => {
    setBusy(true);
    setError(null);
    setSteps([]);
    try {
      await rt.paint();
      const made = rt.call("create_project", {
        name, template: chosen.id, lead: chosen.lead.name, target: "HER2", team,
        created: new Date().toISOString(),
      });
      setSteps((made.view.log || []).filter((e) => e.round === null || e.round === 1));
      rt.saveOverlay();
      bump();
      router.go({ kind: "project", project: made.id });
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  // The cap tells you to delete one, so the remedy lives where the refusal
  // happens rather than as a destructive control on the main path.
  const mine = (rt.safeCall("projects") || []).filter((p) => p.id !== "demo-trastuzumab");
  const removeProject = (id) => {
    try {
      rt.call("delete_project", { project: id });
      rt.saveOverlay();
      bump();
      setError(null);
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  const createBlank = () => {
    const p = blank.create(blankTitle.trim() || "Untitled project");
    bump();
    router.go({ kind: "project", project: p.id });
  };

  return (
    <div className="home">
      <header className="home-head">
        <div>
          <a className="tiny faint" href="#/">← {APP}</a>
          <h1 style={{ fontSize: 24, marginTop: 4 }}>New project</h1>
        </div>
      </header>

      {error && <div className="err" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="new-grid">
        <section>
          <h3 className="home-h">Start from a template</h3>
          {!templates ? <Empty>loading…</Empty> : (
            <div className="tiles" style={{ marginTop: 4 }}>
              {templates.map((t) => {
                const stub = t.status === "stub";
                return (
                  <button key={t.id} className="tile" aria-disabled={stub}
                          aria-pressed={picked === t.id}
                          onClick={() => !stub && setPicked(picked === t.id ? null : t.id)}>
                    <div className="spread">
                      <b>{templateTitle(t)}</b>
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

          {chosen && (
            <div className="card" style={{ marginTop: 14 }}>
              <h4>Configure</h4>
              <table className="grid config" style={{ marginTop: 8 }}>
                <tbody>
                  <tr>
                    <td className="k">Project name</td>
                    <td>
                      <input className="field" value={name} disabled={busy}
                             onChange={(e) => setName(e.target.value)} />
                    </td>
                    <td className="r"><Badge>editable</Badge></td>
                  </tr>
                  {declaration(chosen).map(([k, v, from]) => (
                    <tr key={k} className="locked">
                      <td className="k">{k}</td>
                      <td>
                        {v}
                        {from === "mock" && (
                          <span className="tag-syn" title={MOCK_TIP}>mock</span>
                        )}
                      </td>
                      <td className="r"><span className="lock" title={`read from ${from}`}>
                        🔒</span></td>
                    </tr>
                  ))}
                  <tr>
                    <td className="k">Team</td>
                    <td>
                      <input className="field" value={team} disabled={busy}
                             onChange={(e) => setTeam(e.target.value)} />
                    </td>
                    <td className="r"><Badge>editable</Badge></td>
                  </tr>
                </tbody>
              </table>
              {campaign && (
                <div className="card stack" style={{ marginTop: 12, padding: 12 }}>
                  <Validation campaign={campaign} />
                </div>
              )}
              <div className="card" style={{ marginTop: 12, padding: 12 }}>
                <p className="tiny faint" style={{ margin: 0 }}>Create runs:</p>
                <pre className="code" style={{ marginTop: 6 }}>{
`python init_project.py --template ${chosen.id} --name ${name || "<name>"} …
python skills/adaptive-optimization/scripts/generate_candidates.py --round 1
python skills/adaptive-optimization/scripts/select_batch.py --round 1`}</pre>
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn primary" disabled={busy || !name.trim()}
                        onClick={createTemplated}>
                  {busy ? <span className="busy" /> : null} Create and select round 1
                </button>
              </div>
              {steps.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  {steps.map((e) => (
                    <div key={e.n} className="tool-cmd">{e.command}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>

        <section>
          {mine.length > 0 && (
            <>
              <h3 className="home-h">Projects you made here</h3>
              <div className="card" style={{ padding: 12 }}>
                {mine.map((p) => (
                  <div key={p.id} className="spread" style={{ padding: "4px 0" }}>
                    <span className="small">
                      <b>{p.id}</b>
                      <span className="tiny faint"> · {p.n_rounds} round
                        {p.n_rounds === 1 ? "" : "s"}, {p.n_designs} designs</span>
                    </span>
                    <button className="btn small" onClick={() => removeProject(p.id)}>
                      remove
                    </button>
                  </div>
                ))}
                <p className="tiny faint" style={{ marginTop: 8, marginBottom: 0 }}>
                  This browser holds three created projects at a time.
                </p>
              </div>
            </>
          )}

          <h3 className="home-h" style={{ marginTop: mine.length > 0 ? 24 : 0 }}>
            Or start blank
          </h3>
          <div className="card">
            <p className="small muted" style={{ marginTop: 0 }}>
              An empty project with no template.
            </p>
            <input className="field" placeholder="What is it about?" value={blankTitle}
                   onChange={(e) => setBlankTitle(e.target.value)} />
            <button className="btn" style={{ marginTop: 10 }} onClick={createBlank}>
              Create blank project
            </button>
          </div>

          {reqs && live.length > 0 && (
            <>
              <h3 className="home-h" style={{ marginTop: 24 }}>
                What a templated project needs before a round can run
              </h3>
              <table className="grid" style={{ marginTop: 4 }}>
                <thead>
                  <tr><th>needs</th><th>declared in</th></tr>
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
                    </tr>
                  ))}
                </tbody>
              </table>
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
                      Not exposed: <span className="mono">{s.withheld.join(", ")}</span>
                    </p>
                  )}
                </div>
              ))}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
