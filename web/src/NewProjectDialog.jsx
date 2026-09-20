// The New project dialog, over whatever page opened it.
//
// It is Claude Science's dialog — a name, a description that only tells
// projects apart, and instructions Claude reads in every session — and what
// it creates is a blank project: a box you write a paragraph into. The other
// kind of project, an instance of a declaration, is not made here. A template
// is not a prompt — it carries the objectives schema, the constraint ruleset
// enforced in code before optimization runs, the permitted recipes and
// diagnostics and the batch policy — so choosing one is done where templates
// are read, and the dialog offers that as a single link to the library. What
// was typed before the link was clicked goes with it.

import { useEffect, useRef, useState } from "react";
import * as blank from "./blank.js";
import * as meta from "./meta.js";
import * as router from "./router.js";

export default function NewProjectDialog({ onClose, bump }) {
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
    const p = blank.create(name.trim() || "Untitled project");
    meta.put(p.id, { description, instructions });
    bump();
    router.go({ kind: "project", project: p.id });
  };

  const toTemplates = (e) => {
    e.preventDefault();
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
            <textarea id="np-inst" className="field area" rows={5} value={instructions}
                      placeholder={"“This project compares new measurements with "
                        + "published results. Use SI units, cite a source for every "
                        + "claim, and tell me when the evidence is weak.”"}
                      onChange={(e) => setInstructions(e.target.value)} />
            <p className="tiny faint">
              Claude reads these in every session in this project. Use them for
              background, conventions, and rules.
            </p>
          </div>
        </div>

        <div className="dialog-foot">
          <a className="from-template" href={router.href({ kind: "templates" })}
             onClick={toTemplates}>Create from template</a>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn primary">Create</button>
        </div>
      </form>
    </div>
  );
}
