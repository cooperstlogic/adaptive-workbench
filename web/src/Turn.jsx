// One turn in the centre column.
//
// Three speakers, and which one is talking is load-bearing rather than
// decorative. **Shannon** is the workbench: it reports what it ran, and every
// figure on screen came through it from a `core/` function. **Claude** is the
// part that read those numbers and had something to say about them, and it
// produces none of them — CLAUDE.md's non-negotiable 7, rendered as a byline.
// **You** is where the decision goes.
//
// Claude speaks only when a model wrote the words, or when the record's own
// author did and the turn is a replay of it. Either way the byline carries
// the badge that says which: `live · Opus 5`, or `replayed · 8 of 8 results
// match`. Prose the workbench assembled from artifacts is Shannon's.

import { SPEAKERS } from "./lib.jsx";

export default function Turn({ who, badge, children }) {
  const [initial, name] = SPEAKERS[who] || SPEAKERS.workbench;
  return (
    <div className="msg">
      <div className="msg-who">
        <span className={`dot who-${who}`}>{initial}</span>
        <span>{name}</span>
        {badge && (
          <span className={`mode ${badge.kind}`} title={badge.title}>{badge.text}</span>
        )}
      </div>
      <div className="msg-body">{children}</div>
    </div>
  );
}
