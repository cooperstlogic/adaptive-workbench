// One turn in the centre column.
//
// Two sides, as in the host. Yours is a bubble on the right: what you typed,
// or the ruling you gave. Everything else is the column's own prose — what
// ran, what came back, what the record says — and it carries no name over
// it, because every figure in it came through a `core/` function and a
// speaker would only claim otherwise.
//
// The one label left is the mode badge, and it marks the turns a model
// wrote. Claude speaks only when a model wrote the words, or when the
// record's own author did and the turn is a replay of it — CLAUDE.md's
// non-negotiable 7, rendered as `live · Sonnet 5` or `replayed · 8 of 8 results
// match` above the prose. Prose the workbench assembled from artifacts has
// nothing above it.

export default function Turn({ who, badge, children }) {
  if (who === "you") {
    return (
      <div className="msg you">
        <div className="bubble">{children}</div>
      </div>
    );
  }
  return (
    <div className={`msg ${who === "claude" ? "claude" : "workbench"}`}>
      {who === "claude" && badge && (
        <div className="msg-mode">
          <span className={`mode ${badge.kind}`} title={badge.title}>{badge.text}</span>
        </div>
      )}
      <div className="msg-body">{children}</div>
    </div>
  );
}
