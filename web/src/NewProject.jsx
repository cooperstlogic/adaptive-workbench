// The template library, and the configure screen a chosen template opens.
//
// **The configuration screen is mostly locked, and that is the argument
// rather than a shortcut.** Every locked row is read out of `template.json`,
// so the screen renders the declaration instead of disabling a form. A
// template is not a prompt: it carries the objectives schema, the constraint
// ruleset enforced in code, the permitted recipes and diagnostics, and the
// batch policy — so what a project means does not depend on how well somebody
// phrased a request, and two people who instantiate it get the same project.
//
// **The declaration runs past the template file.** Three rows below it are
// the plugin's — the interpreter, the skill and the two stdio connectors with
// every tool each one exposes and the ones it withholds. They used to be a
// separate table in the margin, which read as an audit finding parked beside
// a product screen. In the same locked list as the objectives they are the
// same sentence continued: this is what the project is, this is what it needs
// to run, and this is the file each line came out of. The two rows no
// manifest can declare — the sandbox grants — are not drawn: they are a
// finding about the host, and this page is about this project.
//
// **Creating it runs three real commands in Pyodide.** `init_project.py` is
// the CLI's own entry point, mirrored into the bundle, and round 1 then goes
// through `generate_candidates.py` and `select_batch.py` like every other
// round. A project instantiated here is byte-identical to one instantiated in
// a terminal — check.py compares them file by file, which is decision 108 in
// the form a machine can check. The name and the description come from the
// New project dialog when it sent someone here; the description stays in this
// browser, because nothing in the round loop reads it and project.json has to
// stay byte-for-byte what the CLI writes.

import { useEffect, useMemo, useState } from "react";
import * as meta from "./meta.js";
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

/** Where a row came from, in the third column: the file, or a dash for the
 *  rows that are plausible rather than declared. */
function Source({ from }) {
  if (from === "mock") return <span className="tiny faint">—</span>;
  return <span className="mono tiny faint" title={`read from ${from}`}>{from}</span>;
}

/** One connector: its transport, every tool it exposes, and the ones it does
 *  not. The withheld list is read out of registry_server.py by bundle.py. */
function Server({ server }) {
  return (
    <div className="server">
      <div className="row" style={{ gap: 7 }}>
        <b className="mono">{server.name}</b>
        <Badge>{server.transport}</Badge>
        <span className="tiny faint">{server.tools.length} tools</span>
      </div>
      <div className="chain">
        {server.tools.map((t) => <span key={t} className="chip mono">{t}</span>)}
      </div>
      {server.withheld.length > 0 && (
        <p className="tiny faint" style={{ margin: "6px 0 0" }}>
          Not exposed: <span className="mono">{server.withheld.join(", ")}</span>
        </p>
      )}
    </div>
  );
}

export default function NewProject({ bump, campaign }) {
  const draft = useMemo(() => meta.take() || {}, []);
  const [templates, setTemplates] = useState(null);
  const [reqs, setReqs] = useState(null);
  const [picked, setPicked] = useState(null);
  const [name, setName] = useState(draft.name || "trastuzumab-affinity-2");
  const [description, setDescription] = useState(draft.description || "");
  const [team, setTeam] = useState("d.webster");
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

  const chosen = (templates || []).find((t) => t.id === picked) || null;
  // Which need is the connectors, without naming them here: the row whose
  // value is the server list itself. check.py holds the two together.
  const connectors = (reqs ? reqs.servers : []).map((s) => s.name).join(", ");
  // Only the rows a manifest declares. The two the audit found -- the sandbox
  // grants, which nothing anywhere can express -- are still in
  // requirements.json and still the sharpest thing phase 5b found, and they
  // belong in the audit rather than in a configure screen, where a row with
  // an empty source column is a question about the host asked on a page about
  // this project. Gap 109 is made in the README.
  const declared = (reqs ? reqs.needs : [])
    .filter((r) => r.declared_in !== "nothing declares this");

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
      meta.put(made.id, { description });
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
      meta.remove(id);
      rt.saveOverlay();
      bump();
      setError(null);
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  return (
    <div className="home">
      <header className="home-head">
        <div>
          <a className="tiny faint" href="#/">← {APP}</a>
          <h1 style={{ fontSize: 24, marginTop: 4 }}>Template library</h1>
        </div>
      </header>

      {error && <div className="err" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="new-single">
        {!templates ? <Empty>loading…</Empty> : (
          <div className="tiles">
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
            <div className="table-scroll">
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
                  <tr>
                    <td className="k">Description</td>
                    <td>
                      <textarea className="field area" rows={2} value={description}
                                disabled={busy} placeholder="Only to tell projects apart"
                                onChange={(e) => setDescription(e.target.value)} />
                    </td>
                    <td className="r"><Badge>editable</Badge></td>
                  </tr>
                  <tr>
                    <td className="k">Team</td>
                    <td>
                      <input className="field" value={team} disabled={busy}
                             onChange={(e) => setTeam(e.target.value)} />
                    </td>
                    <td className="r"><Badge>editable</Badge></td>
                  </tr>

                  <tr className="sub">
                    <td colSpan={3}>
                      <div className="sub-line">
                        <span>Declared by the template</span>
                        <span className="mono tiny faint">{chosen.id}</span>
                      </div>
                    </td>
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
                      <td className="r"><Source from={from} /></td>
                    </tr>
                  ))}

                  {reqs && (
                    <>
                      <tr className="sub">
                        <td colSpan={3}>
                          <div className="sub-line">
                            <span>Needed before a round can run</span>
                            <span className="mono tiny faint">
                              {reqs.plugin.name} v{reqs.plugin.version}
                            </span>
                          </div>
                        </td>
                      </tr>
                      {declared.map((r) => (
                        <tr key={r.what} className="locked">
                          <td className="k">{r.what}</td>
                          <td>
                            <span className="mono">{r.value}</span>
                            {r.value === connectors && (
                              <div className="servers">
                                {reqs.servers.map((s) => <Server key={s.name} server={s} />)}
                              </div>
                            )}
                          </td>
                          <td className="r"><Source from={r.declared_in} /></td>
                        </tr>
                      ))}
                    </>
                  )}
                </tbody>
              </table>
            </div>
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

        {mine.length > 0 && (
          <>
            <h3 className="home-h" style={{ marginTop: 26 }}>Projects you made here</h3>
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
      </div>
    </div>
  );
}
