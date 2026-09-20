// The composer, and the rule that decides what goes through it.
//
// **Decisions are buttons; questions are asks.** Approval and the four ruling
// verbs are typed controls outside the composer — that is decision 65's whole
// point, and the reason the approval primitive is not a chat interrupt.
// Everything that only *reads* state — where are we, why did this flag,
// whether the lab has reported — belongs in here.
//
// Everything in it goes to the model in the centre seat when one is seated:
// free text as typed, and the suggested asks above the box as the prompt
// each one shows -- decision 158. The one suggestion that is a call to the
// laboratory's registry rather than a question about state is marked as such
// and stays one. When there is no seat, the box says so in a phrase and the
// suggested asks are answered from artifacts on disk by the briefing
// `wb_driver` assembles, with nothing over the answer; that is the default a
// cold visit to the public URL gets once the daily budget is spent, and live
// is the upgrade.
//
// The suggestions are presented as the host presents a choice -- `Choices`
// -- until the session's first ask or a skip, and a toggle brings them back.
// The model picker is wired: the function accepts exactly these two ids. It
// is the only control under the box: nothing is drawn here that does not work.

import { useRef, useState } from "react";
import Choices from "./Choices.jsx";
import { MODELS } from "./lib.jsx";

export default function Composer({
  suggestions = [], onAsk, onSend, busy, placeholder, live, model, setModel, asked = 0,
}) {
  const [text, setText] = useState("");
  const [picking, setPicking] = useState(false);
  // Open while nothing has been asked in this session, and again whenever the
  // project's state changes what there is to suggest -- a round comes back,
  // a round flags -- because that is a new reason rather than the old one
  // repeated. Closed by hand until then.
  const signature = suggestions
    .map((s) => `${s.key}:${s.round ?? ""}:${s.state ?? ""}`).join(",");
  const [shown, setShown] = useState(null);
  const at = useRef(signature);
  if (at.current !== signature) {
    at.current = signature;
    setShown(signature ? true : null);
  }
  const canSend = !!(live && live.live && onSend);
  const open = shown === null ? asked === 0 : shown;

  const send = () => {
    if (!text.trim() || !canSend) return;
    onSend(text.trim(), model);
    setText("");
  };

  const pick = (o) => {
    setShown(false);
    if (o.registry || !canSend) onAsk && onAsk(o.key, o.round);
    else onSend(o.question, model, o.title || o.text);
  };

  const hint = canSend
    ? placeholder || "Ask anything…"
    : `Live session unavailable — ${(live && live.reason) || "no function reachable"}`;

  return (
    <div className="composer-wrap">
      {suggestions.length > 0 && (open
        ? <Choices options={suggestions} canSend={canSend} busy={busy} onPick={pick}
                   onSkip={() => setShown(false)} />
        : <div className="asks">
            <button className="ask" onClick={() => setShown(true)}>Suggested asks ▸</button>
          </div>)}
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
