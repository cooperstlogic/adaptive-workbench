// An ad-hoc session: a unit of work inside a project that is not a round.
//
// The reference screenshot shows both kinds in one rail — *Diagnose Round 4…*
// beside *List Designs Registry Connector*. That is the amendment to
// `SPEC.md`'s "a session is a round", and it is where the thesis gets
// demonstrated rather than asserted:
//
//   Open a project you have never opened. Click `+ New`. Ask *where are we?*
//   Back comes the state of the campaign, every figure read from an artifact
//   on disk and resolving to the `core/` function that produced it. The same
//   question in a chat product gets a summary of the transcript, because
//   there is no state to read.
//
// The suggested asks are answered by a briefing assembled in `wb_driver`;
// free text goes to the model in the centre seat when one is available, with
// the same two read-only tools the diagnosis has and the project's state as
// its context. Both kinds of answer are stored in the session, and the
// byline says which produced each.
//
// An empty one is a title and a composer. Nothing on the page says any of
// the above; the asks under the composer are the whole invitation.

import AgentStream, { agentBadge } from "./AgentStream.jsx";
import Briefing from "./Briefing.jsx";
import Composer from "./Composer.jsx";
import Turn from "./Turn.jsx";
import { CentreHead, projectTitle } from "./lib.jsx";

export default function AdHoc({ ctx, stored, suggestions }) {
  const { view, sessionId, busy, error, onAsk, onAskLive, live, model, setModel, agentTurn,
          log } = ctx;
  const turns = (stored?.turns || [])
    .map((t) => (agentTurn && t.kind === "agent" && agentTurn.id === t.id ? agentTurn : t));
  if (agentTurn && !turns.some((t) => t.kind === "agent" && t.id === agentTurn.id)) {
    turns.push(agentTurn);
  }

  return (
    <>
      <CentreHead title={stored?.title || "New session"}
                  sub={`${projectTitle(view.project)} · ${view.rounds.length} rounds · ${
                    view.n_designs} designs`} />
      <div className="centre-inner thread">
        {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

        {turns.map((t, i) => (
          t.kind === "agent" ? (
            <div key={t.id || i}>
              <Turn who="you"><p>{t.label || t.question}</p></Turn>
              <Turn who="claude" badge={agentBadge(t)}>
                <AgentStream turn={t} log={log}
                             live={!!(agentTurn && agentTurn.id === t.id)} ctx={ctx} />
              </Turn>
            </div>
          ) : (
            <div key={i}>
              <Turn who="you"><p>{t.question}</p></Turn>
              <Turn who="workbench"><Briefing data={t.answer} ctx={ctx} /></Turn>
            </div>
          )
        ))}

        {busy && !agentTurn && (
          <Turn who="workbench"><p className="muted"><span className="busy" /> reading
            the project…</p></Turn>
        )}

        <Composer suggestions={suggestions} busy={busy}
                  live={live} model={model} setModel={setModel}
                  onAsk={(key, round) => onAsk(key, round, sessionId)}
                  onSend={(text, chosen, label) => onAskLive(text, chosen, label)} />
      </div>
    </>
  );
}
