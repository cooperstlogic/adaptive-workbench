// The tool-call stream: one component, two sources.
//
// A live model and the committed record drive the same list of steps -- a
// sentence, a command that ran, a sentence about what it returned -- and the
// only visible difference is the badge over the turn. Every chip is a log
// entry, so a step that says a test ran is a test that ran, in this tab,
// against this copy of the project.
//
// The badge is where the mode is stated, once, above the turn and on no
// other kind of turn: `live · Sonnet 5`, or `replayed · 8 of 8 recomputed
// match`, or `stopped · daily budget spent`. Nothing under the turn explains
// it.

import Prose from "./Prose.jsx";
import Tool from "./Tool.jsx";
import { ACTION_LABEL, Badge, MODEL_LABEL } from "./lib.jsx";

export function agentBadge(turn) {
  if (!turn) return null;
  if (turn.mode === "replay") {
    const v = turn.verified || {};
    const parts = ["replayed"];
    if (v.of_diagnostics) parts.push(`${v.diagnostics} of ${v.of_diagnostics} results match`);
    if (v.of_ad_hoc) parts.push(`${v.ad_hoc} of ${v.of_ad_hoc} cuts reproduce`);
    if (turn.status === "running") parts.push("recomputing…");
    return { kind: "replay", text: parts.join(" · "),
             title: "The committed record's claims, with every test re-run here and hash-compared against it" };
  }
  const model = MODEL_LABEL[turn.model] || turn.model || "model";
  if (turn.status === "stopped" && turn.stop) {
    return { kind: "stop", text: `stopped · ${turn.stop.reason}`,
             title: turn.upstream === "scripted" ? "scripted upstream" : undefined };
  }
  const parts = [turn.upstream === "scripted" ? "scripted · harness" : `live · ${model}`];
  // The conversation the session held was not continued: the function
  // refused it before spending anything, and this turn began again from
  // the record. The reason is the tooltip.
  if (turn.restarted) parts.push("restarted");
  if (turn.status === "running") parts.push("working");
  const title = turn.fallback ? `served by ${turn.fallback} after a refusal`
    : turn.restarted ? `the conversation started over: ${turn.restarted}` : undefined;
  return { kind: "live", text: parts.join(" · "), title };
}

export default function AgentStream({ turn, log, live, ctx }) {
  if (!turn) return null;
  const byN = new Map((log || []).map((e) => [e.n, e]));
  const steps = turn.steps || [];
  const lastIndex = steps.length - 1;
  return (
    <div className="stream">
      {steps.map((s, i) => {
        if (s.type === "text") {
          if (!s.text && !(live && i === lastIndex)) return null;
          return (
            <div key={i} className={s.reading ? `reading ${s.reading.replace(/ /g, "-")}` : undefined}>
              <Prose text={s.text} streaming={live && i === lastIndex} />
            </div>
          );
        }
        if (s.type === "tool") {
          const entry = s.entry || byN.get(s.n);
          return entry ? <Tool key={i} entry={entry} verified={s.verified} /> : null;
        }
        if (s.type === "proposal") {
          return (
            <div key={i} className="card proposal">
              <div className="spread">
                <b>{s.decision_id}{s.pass > 1 ? ` · pass ${s.pass}` : ""}</b>
                <Badge kind="attn">{ACTION_LABEL[s.action] || s.action}</Badge>
              </div>
              <p className="small" style={{ margin: "6px 0 0" }}>
                {s.n_hypotheses} hypotheses, confidence {s.confidence}. Recorded by{" "}
                <span className="mono">record_decision.py</span>, every result recomputed. The
                rationale, the alternatives and the <i>if_wrong</i> line are in the Decision tab.
              </p>
              {s.amendment && (
                <p className="small" style={{ margin: "6px 0 0" }}>
                  It also asks to move <span className="mono">{s.amendment.field}</span> from{" "}
                  <span className="num">{s.amendment.from}</span> to{" "}
                  <span className="num">{s.amendment.to}</span>, which changes what the next
                  batch is made of. Nothing moves until it is ruled on.
                </p>
              )}
            </div>
          );
        }
        if (s.type === "revision") {
          const c = s.composition;
          return (
            <div key={i} className="card proposal">
              <div className="spread">
                <b>Round {s.round} re-composed</b>
                <Badge kind="attn">
                  {s.overrides.map((o) => o.field.split(".").pop()).join(", ")}
                </Badge>
              </div>
              <p className="small" style={{ margin: "6px 0 0" }}>
                {s.overrides.map((o) => `${o.field} ${o.from} → ${o.to}`).join("; ")}. The
                batch is now {c.control} control, {c.replicate} replicate, {c.exploration}{" "}
                exploration and {c.pick} fresh picks. This batch only —{" "}
                <span className="mono">objectives.json</span> is unchanged, and nobody has
                approved it.
              </p>
            </div>
          );
        }
        if (s.type === "refused") {
          return <p key={i} className="err small">Refused: {s.text}</p>;
        }
        if (s.type === "malformed") {
          return <p key={i} className="err small">Not run: {s.text}</p>;
        }
        if (s.type === "stop") {
          return <p key={i} className="small muted">Stopped: {s.reason}.</p>;
        }
        return null;
      })}
      {live && turn.status === "running" && turn.writing && (
        <p className="muted small"><span className="busy" /> {turn.writing === "propose_decision"
          ? "writing the proposal…" : `calling ${turn.writing}…`}</p>
      )}
      {live && turn.status === "running" && !turn.writing
        && !steps.some((s) => s.type === "text" && s.text) && (
        <p className="muted small"><span className="busy" /> thinking…</p>
      )}
      {ctx && ctx.busy && turn.status === "running" && steps[lastIndex]?.type === "tool" && (
        <p className="muted small"><span className="busy" /> reading it…</p>
      )}
    </div>
  );
}
