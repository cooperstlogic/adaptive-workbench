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
// Until phase 7 there is no live model, so the asks are the vocabulary and a
// briefing assembled in `wb_driver` is the answer. That is decision 62's
// one-surface, two-sources pattern applied to status rather than diagnosis.
//
// An empty one is a title and a composer. Nothing on the page says any of
// the above; the asks under the composer are the whole invitation.

import Briefing from "./Briefing.jsx";
import Composer from "./Composer.jsx";
import Turn from "./Turn.jsx";
import { CentreHead, projectTitle } from "./lib.jsx";

export default function AdHoc({ ctx, stored, suggestions }) {
  const { view, sessionId, busy, error, onAsk } = ctx;
  const turns = stored?.turns || [];

  return (
    <>
      <CentreHead title={stored?.title || "New session"}
                  sub={`${projectTitle(view.project)} · ${view.rounds.length} rounds · ${
                    view.n_designs} designs`} />
      <div className="centre-inner thread">
        {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

        {turns.map((t, i) => (
          <div key={i}>
            <Turn who="you"><p>{t.question}</p></Turn>
            <Turn who="workbench"><Briefing data={t.answer} ctx={ctx} /></Turn>
          </div>
        ))}

        {busy && <Turn who="workbench"><p className="muted"><span className="busy" /> reading
          the project…</p></Turn>}

        <Composer suggestions={suggestions} busy={busy}
                  onAsk={(key, round) => onAsk(key, round, sessionId)} />
      </div>
    </>
  );
}
