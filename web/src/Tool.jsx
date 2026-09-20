// One command that ran. The chip is the log entry: the command as the CLI
// would have been typed, its exit code, and both output streams behind a
// click. Nothing under it explains what it proved.
//
// An ad hoc entry -- model-written numpy run by execute_analysis -- carries
// its source as well, because the rule for that kind of evidence is that the
// code is shown beside the number. A `verified` mark says the result was
// hash-compared against the committed record, which is the replay's claim.

import { useState } from "react";

export default function Tool({ entry, defaultOpen, verified }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const refused = entry.refused;
  const adhoc = entry.kind === "adhoc";
  return (
    <div className={`tool${refused ? " refused" : ""}${adhoc ? " adhoc" : ""}`}>
      <button className="tool-head" onClick={() => setOpen(!open)}>
        <span className="tick">{entry.code === 0 ? "●" : refused ? "⊘" : "✕"}</span>
        <span className="grow">
          <span className="small">{entry.label}</span>
          <div className="tool-cmd">{entry.command}</div>
        </span>
        {verified && verified.checked && (
          <span className={`tiny ${verified.matched ? "ok-text" : "err"}`}
                title={verified.matched
                  ? "the result matches the committed record, by content hash"
                  : "the result differs from the committed record"}>
            {verified.matched ? "matches record" : "differs"}
          </span>
        )}
        <span className="faint tiny">{open ? "hide" : "output"}</span>
      </button>
      {open && (
        <div className="tool-out">
          {adhoc && entry.source && (
            <pre className="code" style={{ marginBottom: 8 }}>{entry.source}</pre>
          )}
          {entry.messages && <pre className="code">{entry.messages}</pre>}
          {entry.output && (
            <pre className="code" style={{ marginTop: entry.messages ? 8 : 0 }}>
              {entry.output}
            </pre>
          )}
          {!entry.output && !entry.messages && <pre className="code">(no output)</pre>}
        </div>
      )}
    </div>
  );
}
