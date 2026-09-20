// An ad-hoc session: a unit of work inside a project that is not a round.
//
// The reference screenshot shows both kinds in one rail — *Diagnose Round 4…*
// beside *List Designs Registry Connector*. That is the amendment to the
// original "a session is a round", and it is where the thesis gets
// demonstrated rather than asserted:
//
//   Open a project you have never opened. Click `+ New`. Ask *where are we?*
//   Back comes the state of the campaign, read by the model in the centre
//   seat from the project's artifacts with the same two read-only tools the
//   diagnosis has -- decision 158. The same question in a chat product gets
//   a summary of the transcript, because there is no state to read.
//
// Every turn is stored in the session. A model's carries the mode badge; a
// briefing the workbench assembled from artifacts -- the registry's answer
// to a round's results check, made from a round session -- carries nothing.
// An empty one is a title and a composer, and without a seat the composer
// says so and stays closed: there is nothing on this page to press.

import AgentStream, { agentBadge } from "./AgentStream.jsx";
import Briefing from "./Briefing.jsx";
import Composer from "./Composer.jsx";
import Turn from "./Turn.jsx";
import { CentreHead, PanelToggle, projectTitle } from "./lib.jsx";

export default function AdHoc({ ctx, stored }) {
  const { view, sessionId, busy, error, onAskLive, live, model, setModel, agentTurn,
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
                    view.n_designs} designs`}
                  aside={<PanelToggle panel={ctx.panel} />} />
      <div className="centre-inner thread">
        {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

        {turns.map((t, i) => (
          t.kind === "agent" ? (
            <div key={t.id || i}>
              <Turn who="you"><p title={t.label ? t.question : undefined}>{t.label || t.question}</p></Turn>
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

        <Composer key={sessionId} busy={busy} live={live} model={model} setModel={setModel}
                  onSend={(text, chosen, label) => onAskLive(text, chosen, label)} />
      </div>
    </>
  );
}
