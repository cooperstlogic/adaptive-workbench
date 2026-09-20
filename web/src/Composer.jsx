// The composer, and the rule that decides what goes through it.
//
// **Decisions are buttons; questions are asks.** Approval and the four ruling
// verbs are typed controls outside the composer — that is decision 65's whole
// point, and the reason the approval primitive is not a chat interrupt.
// Everything that only *reads* state — where are we, why did this flag —
// belongs in here, as free text to the model in the centre seat.
//
// Nothing sits over the box. There were suggested asks once, presented as
// the host presents a choice; they were more in the way than they were
// worth, and the one that was not a question -- whether the lab has
// reported -- is a button in the column now, because it is a call to the
// registry. When there is no seat the box says so in a phrase and stays
// disabled; that is what a cold visit to the public URL gets, and live is
// the upgrade. The model picker is wired: the function accepts exactly these
// two ids. It is the only control under the box: nothing is drawn here that
// does not work.

import { useState } from "react";
import { MODELS } from "./lib.jsx";

export default function Composer({ onSend, busy, placeholder, live, model, setModel }) {
  const [text, setText] = useState("");
  const [picking, setPicking] = useState(false);
  const canSend = !!(live && live.live && onSend);

  const send = () => {
    if (!text.trim() || !canSend) return;
    onSend(text.trim(), model);
    setText("");
  };

  const hint = canSend
    ? placeholder || "Ask anything…"
    : `Live session unavailable — ${(live && live.reason) || "no function reachable"}`;

  return (
    <div className="composer-wrap">
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
            <button className="glyph send" onClick={send} disabled={!text.trim() || busy || !canSend}>
              ↑
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}
