// The composer, and the rule that decides what goes through it.
//
// **Decisions are buttons; questions are asks.** Approval and the four ruling
// verbs are typed controls outside the composer — that is decision 65's whole
// point, and the reason the approval primitive is not a chat interrupt.
// Everything that only *reads* state — where are we, why did this flag,
// whether the lab has reported — belongs in here.
//
// Two kinds of ask sit under it. The suggested ones are answered
// deterministically by a briefing assembled in `wb_driver` from artifacts on
// disk, no model involved. Free text, and the one suggestion marked `live`,
// go to the model in the centre seat — when there is one. When there is not,
// the box says so in a phrase and the suggested asks keep working; that is
// the default a cold visit to the public URL gets once the daily budget is
// spent, and live is the upgrade.
//
// The model picker is wired: the function accepts exactly these three ids.

import { useState } from "react";
import { MODELS } from "./lib.jsx";

export default function Composer({
  suggestions = [], onAsk, onSend, busy, placeholder, live, model, setModel,
}) {
  const [text, setText] = useState("");
  const [picking, setPicking] = useState(false);
  const canSend = !!(live && live.live && onSend);
  const shown = suggestions.filter((s) => s.key !== "live" || canSend);

  const send = () => {
    if (!text.trim() || !canSend) return;
    onSend(text.trim(), model);
    setText("");
  };

  const hint = canSend
    ? placeholder || "Ask anything — @ for artifacts, # for sessions, / for skills, ⌘K to search…"
    : `Live session unavailable — ${(live && live.reason) || "no function reachable"}`;

  return (
    <div className="composer-wrap">
      {shown.length > 0 && (
        <div className="asks">
          {shown.map((s) => (
            <button key={`${s.key}:${s.round ?? ""}`} className={`ask${s.key === "live" ? " live" : ""}`}
                    disabled={busy}
                    onClick={() => (s.key === "live"
                      ? onSend && onSend(s.question, model, s.text)
                      : onAsk && onAsk(s.key, s.round))}>
              {s.text}
            </button>
          ))}
        </div>
      )}
      <div className="composer">
        <textarea
          className="field" rows={2} value={text}
          disabled={!canSend}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
          }}
          placeholder={hint}
        />
        <div className="composer-bar">
          <span className="composer-left">
            <button className="glyph" disabled title="Attach">+</button>
            <button className="glyph" disabled title="Tools">⚒</button>
          </span>
          <span className="composer-right">
            <span className="picker">
              <button className="glyph wide" onClick={() => setPicking(!picking)}>
                {(MODELS.find((m) => m.id === model) || MODELS[0]).label}{" "}
                <span className="chev">⌄</span>
              </button>
              {picking && (
                <div className="picker-menu" onMouseLeave={() => setPicking(false)}>
                  {MODELS.map((m) => (
                    <button key={m.id} className="picker-item"
                            aria-selected={m.id === model}
                            onClick={() => { setModel && setModel(m.id); setPicking(false); }}>
                      <b>{m.label}</b>
                      <span className="mono tiny faint">{m.id}</span>
                    </button>
                  ))}
                </div>
              )}
            </span>
            <button className="glyph" disabled title="Dictate">🎙</button>
            <button className="glyph send" onClick={send} disabled={!text.trim() || busy || !canSend}>
              ↑
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}
