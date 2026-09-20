// The composer, and the rule that decides what goes through it.
//
// **Decisions are buttons; questions are asks.** Approval and the four ruling
// verbs are typed controls outside the composer — that is decision 65's whole
// point, and the reason the approval primitive is not a chat interrupt.
// Everything that only *reads* state — where are we, why did this flag,
// whether the lab has reported — belongs in here.
//
// The suggested asks above it work today and work deterministically: each one
// is answered by a briefing assembled in `wb_driver` from artifacts on disk,
// with no model involved and every figure carrying the `core/` function that
// produced it. Free text is phase 7, when a live model takes the same seat.
// None of that is said on the page; the page is a composer.

import { useState } from "react";

// The working model picker. Opus 5 is selectable because it is what phase 7
// would run; the others are shown to make the point that the choice exists.
const MODELS = [
  { id: "claude-opus-5", label: "Opus 5", live: true },
  { id: "claude-sonnet-5", label: "Sonnet 5", live: false },
  { id: "claude-haiku-4-5-20251001", label: "Haiku 4.5", live: false },
];

export default function Composer({ suggestions = [], onAsk, busy, placeholder, onSend }) {
  const [text, setText] = useState("");
  const [model, setModel] = useState(MODELS[0].id);
  const [picking, setPicking] = useState(false);

  const send = () => {
    if (!text.trim() || !onSend) return;
    onSend(text.trim());
    setText("");
  };

  return (
    <div className="composer-wrap">
      {suggestions.length > 0 && (
        <div className="asks">
          {suggestions.map((s) => (
            <button key={s.key} className="ask" disabled={busy}
                    onClick={() => onAsk && onAsk(s.key, s.round)}>
              {s.text}
            </button>
          ))}
        </div>
      )}
      <div className="composer">
        <textarea
          className="field" rows={2} value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && onSend) { e.preventDefault(); send(); }
          }}
          placeholder={placeholder
            || "Ask anything — @ for artifacts, # for sessions, / for skills, ⌘K to search…"}
        />
        <div className="composer-bar">
          <span className="composer-left">
            <button className="glyph" disabled title="Attach">+</button>
            <button className="glyph" disabled title="Tools">⚒</button>
          </span>
          <span className="composer-right">
            <span className="picker">
              <button className="glyph wide" onClick={() => setPicking(!picking)}>
                {MODELS.find((m) => m.id === model).label} <span className="chev">⌄</span>
              </button>
              {picking && (
                <div className="picker-menu" onMouseLeave={() => setPicking(false)}>
                  {MODELS.map((m) => (
                    <button key={m.id} className="picker-item" disabled={!m.live}
                            aria-selected={m.id === model}
                            onClick={() => { if (m.live) { setModel(m.id); setPicking(false); } }}>
                      <b>{m.label}</b>
                      <span className="mono tiny faint">{m.id}</span>
                    </button>
                  ))}
                </div>
              )}
            </span>
            <button className="glyph" disabled title="Dictate">🎙</button>
            {onSend && (
              <button className="glyph send" onClick={send} disabled={!text.trim() || busy}>
                ↑
              </button>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}
