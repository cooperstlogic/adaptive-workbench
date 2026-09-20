// A model's text, laid out. Paragraphs, bullet lists, fenced code, and
// inline bold and code -- the four things Claude reaches for -- and nothing
// else, because a Markdown library is a dependency and the composer's
// answers are short.

import { Fragment } from "react";

function inline(text) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) parts.push(<b key={i++}>{tok.slice(2, -2)}</b>);
    else parts.push(<code key={i++} className="mono">{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export default function Prose({ text, streaming }) {
  const blocks = [];
  const lines = String(text || "").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const code = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i += 1;
      blocks.push(<pre key={blocks.length} className="code">{code.join("\n")}</pre>);
      continue;
    }
    if (/^\s*[-*•]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*•]\s+/, ""));
        i += 1;
      }
      blocks.push(
        <ul key={blocks.length} className="small" style={{ paddingLeft: 18, margin: "0 0 9px" }}>
          {items.map((it, k) => <li key={k}>{inline(it)}</li>)}
        </ul>,
      );
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i += 1;
      }
      blocks.push(
        <ol key={blocks.length} className="small" style={{ paddingLeft: 18, margin: "0 0 9px" }}>
          {items.map((it, k) => <li key={k}>{inline(it)}</li>)}
        </ol>,
      );
      continue;
    }
    if (!line.trim()) { i += 1; continue; }
    const para = [];
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith("```")
           && !/^\s*[-*•]\s+/.test(lines[i]) && !/^\s*\d+[.)]\s+/.test(lines[i])) {
      para.push(lines[i].replace(/^#+\s*/, ""));
      i += 1;
    }
    blocks.push(<p key={blocks.length}>{inline(para.join(" "))}</p>);
  }
  return (
    <Fragment>
      {blocks}
      {streaming && <span className="caret" aria-hidden="true" />}
    </Fragment>
  );
}
