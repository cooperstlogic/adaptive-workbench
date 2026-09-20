// Blank projects: the control arm.
//
// **A blank project never touches Python, and that is the point rather than a
// limitation.** `project.load()` requires project.json, objectives.json,
// designs.json and rounds.json; a project with no template has none of them,
// because nothing has declared what its objectives are, which constraints
// hold, which recipes are permitted or how big a batch is. There is nothing
// for the round loop to read, so the round loop is not offered.
//
// That makes it the control arm for decision 108 -- "no project instantiation
// from a declaration", graded *survives, but under-tested* in the phase-5b
// audit. A blank project beside a templated one, both created live in the
// same interface, is the difference between asserting the gap and showing it:
// one of them opens on an empty chat, and the other opens on round 1 already
// enumerated, filtered and selected under constraints enforced in code.
//
// They live in localStorage and nowhere else. Losing them costs nothing,
// because there is nothing in them.

const KEY = "shannon.blank.v1";

function read() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : { projects: [] };
  } catch {
    return { projects: [] };            // private window, or blocked storage
  }
}

function write(doc) {
  try {
    localStorage.setItem(KEY, JSON.stringify(doc));
    return { error: null };
  } catch (err) {
    return { error: String(err.message || err) };
  }
}

export function list() {
  return read().projects.map((p) => ({ ...p, kind: "blank" }));
}

export function get(id) {
  return list().find((p) => p.id === id) || null;
}

export function create(title) {
  const doc = read();
  const now = new Date().toISOString();
  const id = `blank-${Date.now().toString(36)}`;
  doc.projects.unshift({
    id, title: title || "Untitled project", created: now, updated: now, sessions: [],
  });
  write(doc);
  return { ...doc.projects[0], kind: "blank" };
}

export function remove(id) {
  const doc = read();
  doc.projects = doc.projects.filter((p) => p.id !== id);
  return write(doc);
}

/** A session inside a blank project. It holds what was typed and nothing else. */
export function newSession(projectId) {
  const doc = read();
  const p = doc.projects.find((x) => x.id === projectId);
  if (!p) return null;
  const id = `s${p.sessions.length + 1}`;
  p.sessions.unshift({ id, title: null, created: new Date().toISOString(), turns: [] });
  p.updated = new Date().toISOString();
  write(doc);
  return p.sessions[0];
}

export function addTurn(projectId, sessionId, text) {
  const doc = read();
  const p = doc.projects.find((x) => x.id === projectId);
  const s = p && p.sessions.find((x) => x.id === sessionId);
  if (!s) return null;
  s.turns.push({ text, at: new Date().toISOString() });
  if (!s.title) s.title = text.slice(0, 48);
  p.updated = new Date().toISOString();
  write(doc);
  return s;
}

/** The model's answer to a turn, when a live session is available. It is a
 *  chat with nothing declared, which is what a blank project is; the answer
 *  is kept as text with the model that wrote it and how the turn ended. */
export function answer(projectId, sessionId, index, reply) {
  const doc = read();
  const p = doc.projects.find((x) => x.id === projectId);
  const s = p && p.sessions.find((x) => x.id === sessionId);
  if (!s || !s.turns[index]) return null;
  s.turns[index].answer = reply;
  write(doc);
  return s;
}

/** The four blank projects the home screen ships with, so the list reads like
 *  a workspace rather than a demo with one row in it. Each is a one-shot
 *  analysis rather than a campaign, which is the contrast: clicking one opens
 *  an empty chat, and that is what a project is without a template. */
export const SEEDED = [
  { id: "bridge-spr-bli", title: "Cross-assay bridging: SPR against BLI on the 2024 panel",
    days: 3 },
  { id: "devel-triage-q3", title: "Developability triage, Q3 lead set", days: 9 },
  { id: "plate-postmortem-118", title: "Plate-effect postmortem — HT-SPR run 118", days: 17 },
  { id: "lit-dg-isomerization", title: "Literature scan: DG isomerization in CDR-H3",
    days: 26 },
];

export function seeded() {
  const now = Date.now();
  return SEEDED.map((p) => ({
    ...p, kind: "blank", seeded: true, sessions: [],
    created: new Date(now - p.days * 86400000).toISOString(),
    updated: new Date(now - p.days * 86400000).toISOString(),
  }));
}

export function all() {
  const mine = list();
  const ids = new Set(mine.map((p) => p.id));
  return [...mine, ...seeded().filter((p) => !ids.has(p.id))];
}
