// The New project dialog, over whatever page opened it.
//
// It is Claude Science's dialog — a name, a description that only tells
// projects apart, and instructions Claude reads in every session — with one
// control added at the top, and that control is the whole idea in a single
// radio group. A project here is either a box you write a paragraph into, or
// an instance of a declaration. Choosing the second replaces the
// instructions box with the template library, because a template is not a
// prompt: it carries the objectives schema, the constraint ruleset enforced
// in code before optimization runs, the permitted recipes and diagnostics and
// the batch policy, and two people who instantiate it get the same project.
//
// Nothing is created on the templated branch. The dialog hands the name and
// the description to the library and gets out of the way, because what has to
// be chosen next is a template and the library is where templates are read.

import { useEffect, useRef, useState } from "react";
import * as blank from "./blank.js";
import * as meta from "./meta.js";
import * as router from "./router.js";

const KINDS = [
  { id: "template", label: "From a template",
    blurb: "Objectives, constraints, recipes and a batch policy, declared in a file." },
  { id: "blank", label: "Blank project",
    blurb: "An empty chat. Nothing is declared." },
];

export default function NewProjectDialog({ onClose, bump }) {
  const [kind, setKind] = useState("template");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const first = useRef(null);

  useEffect(() => {
    first.current?.focus();
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = (e) => {
    e.preventDefault();
    if (kind === "blank") {
      const p = blank.create(name.trim() || "Untitled project");
      meta.put(p.id, { description, instructions });
      bump();
      router.go({ kind: "project", project: p.id });
      return;
    }
    meta.stage({ name: name.trim(), description: description.trim() });
    router.go({ kind: "templates" });
  };

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="sheet dialog" onSubmit={submit}
            role="dialog" aria-modal="true" aria-label="New project">
        <div className="dialog-head">
          <h2>New project</h2>
          <button type="button" className="glyph" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="dialog-body">
          <div className="field-group">
            <span className="field-label">Start from</span>
            <div className="picks">
              {KINDS.map((k) => (
                <button key={k.id} type="button" className="pick" aria-pressed={kind === k.id}
                        onClick={() => setKind(k.id)}>
                  <b>{k.label}</b>
                  <span className="small muted">{k.blurb}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="np-name">Name</label>
            <input id="np-name" ref={first} className="field" value={name}
                   placeholder="Project name" onChange={(e) => setName(e.target.value)} />
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="np-desc">Description</label>
            <textarea id="np-desc" className="field area" rows={3} value={description}
                      placeholder="Describe what this project is about"
                      onChange={(e) => setDescription(e.target.value)} />
            <p className="tiny faint">
              This helps you tell your projects apart. It isn’t part of the instructions
              to Claude.
            </p>
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="np-inst">Instructions for Claude</label>
            {kind === "blank" ? (
              <>
                <textarea id="np-inst" className="field area" rows={5} value={instructions}
                          placeholder={"“This project compares new measurements with "
                            + "published results. Use SI units, cite a source for every "
                            + "claim, and tell me when the evidence is weak.”"}
                          onChange={(e) => setInstructions(e.target.value)} />
                <p className="tiny faint">
                  Claude reads these in every session in this project. Use them for
                  background, conventions, and rules.
                </p>
              </>
            ) : (
              <div className="field declared">
                <p className="small">The template declares them, and the configure
                  screen lists every line it declares.</p>
              </div>
            )}
          </div>
        </div>

        <div className="dialog-foot">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary">
            {kind === "blank" ? "Create" : "Choose a template"}
          </button>
        </div>
      </form>
    </div>
  );
}
