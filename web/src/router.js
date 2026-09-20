// The hash router. Seven routes, no library.
//
// A hash router because the site is a static bundle served from a path that
// is not known at build time -- GitHub Pages, a file:// copy, a preview. The
// history API would need a server that rewrites every deep link back to
// index.html, and the one thing this build is not allowed to acquire is a
// server.
//
// Routes are parsed into plain objects and nothing else knows the string
// form, so a route that does not parse lands on home rather than on a blank
// page.
//
//   #/                        home
//   #/new                     home, with the New project dialog over it
//   #/templates               the template library
//   #/p/<id>                  a project, which redirects to where you left off
//   #/p/<id>/s/new            a new, empty session
//   #/p/<id>/s/<session-id>   a session -- a round, or an ad-hoc one
//   #/p/<id>/rounds           the round graph

export const HOME = { kind: "home" };

export function parse(hash) {
  const raw = String(hash || "").replace(/^#/, "").replace(/^\/+/, "");
  const parts = raw.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts.length === 0) return HOME;
  if (parts[0] === "new") return { kind: "new" };
  if (parts[0] === "templates") return { kind: "templates" };
  if (parts[0] === "p" && parts[1]) {
    const project = parts[1];
    if (parts[2] === "rounds") return { kind: "rounds", project };
    if (parts[2] === "s" && parts[3] === "new") return { kind: "session", project, id: "new" };
    if (parts[2] === "s" && parts[3]) return { kind: "session", project, id: parts[3] };
    return { kind: "project", project };
  }
  return HOME;
}

export function href(route) {
  const e = encodeURIComponent;
  switch (route.kind) {
    case "new": return "#/new";
    case "templates": return "#/templates";
    case "project": return `#/p/${e(route.project)}`;
    case "rounds": return `#/p/${e(route.project)}/rounds`;
    case "session": return `#/p/${e(route.project)}/s/${e(route.id)}`;
    default: return "#/";
  }
}

export function go(route) {
  const next = href(route);
  if (window.location.hash !== next) window.location.hash = next;
}

// Replace rather than push, for the one case that is a redirect and not a
// navigation: opening a project lands you on a session, and the back button
// should leave the project rather than bounce you into it again.
export function replace(route) {
  const next = href(route);
  if (window.location.hash === next) return;
  const url = `${window.location.pathname}${window.location.search}${next}`;
  window.history.replaceState(null, "", url);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

export function subscribe(fn) {
  const onChange = () => fn(parse(window.location.hash));
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/** Where a project opens, given what is actually pending in it.
 *
 * A project is not a lobby. Opening one puts you at the thing it needs from
 * you, and the round graph is one click away in the rail rather than the
 * thing you have to walk through to reach the work.
 */
export function landing(view) {
  if (!view) return null;
  const rounds = view.rounds || [];
  const flagged = rounds.find((r) => r.status === "flagged, ruling pending");
  if (flagged) return `r${flagged.round}`;
  const pending = rounds.find((r) => r.status === "awaiting approval");
  if (pending) return `r${pending.round}`;
  const reported = rounds.find((r) => r.reported);
  if (reported) return `r${reported.round}`;
  const atLab = rounds.find((r) => r.at_lab);
  if (atLab) return `r${atLab.round}`;
  const recent = (view.sessions || [])[0];
  if (recent) return recent.id;
  return "new";
}
