// What a person writes about a project, as opposed to what a template
// declares about it.
//
// Claude Science's New project dialog collects three things: a name, a
// description that only helps you tell projects apart, and instructions
// Claude reads in every session. The first is already a project's id here.
// The other two live in this browser and nowhere else, because neither is
// something the round loop reads:
//
// **The description is a note.** It never reaches Python, so a project
// instantiated here stays byte-identical to one instantiated in a terminal --
// which is the claim check.py makes file by file, and writing a free-text
// field into project.json would break it for a line nothing computes with.
//
// **The instructions are only a blank project's.** They are the whole
// contrast the dialog draws: in a project with no template, what Claude knows
// about the work is a paragraph somebody typed, and it goes into the system
// prompt as prose. In a templated project there is no such box, because the
// objectives, the constraints, the permitted recipes, the batch policy and
// the diagnostics are declared in template.json and enforced in code before
// the model is asked anything. A templated project that also carried a prose
// brief would blur the one difference worth showing.
//
// localStorage, like the blank projects themselves: losing it costs a note.

const KEY = "workbench.meta.v1";

function read() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};                          // private window, or blocked storage
  }
}

function write(doc) {
  try {
    localStorage.setItem(KEY, JSON.stringify(doc));
  } catch { /* nothing here is worth failing a creation over */ }
}

export function get(id) {
  return read()[id] || null;
}

export function put(id, { description = "", instructions = "" } = {}) {
  const doc = read();
  const kept = {};
  if (description.trim()) kept.description = description.trim();
  if (instructions.trim()) kept.instructions = instructions.trim();
  if (Object.keys(kept).length === 0) delete doc[id];
  else doc[id] = kept;
  write(doc);
  return kept;
}

export function remove(id) {
  const doc = read();
  delete doc[id];
  write(doc);
}

export const describe = (id) => (get(id) || {}).description || "";
export const instructionsFor = (id) => (get(id) || {}).instructions || "";

// The dialog hands off to the template library rather than creating anything
// itself, and the library is a route away. What was typed waits here in page
// memory until the configure screen picks it up; a reload, or a deep link
// straight to #/templates, finds nothing and starts from the defaults.
let handoff = null;

export function stage(draft) { handoff = draft; }

export function take() {
  const d = handoff;
  handoff = null;
  return d;
}
