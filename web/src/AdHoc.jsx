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

import Briefing from "./Briefing.jsx";
import Composer from "./Composer.jsx";
import Turn from "./Turn.jsx";
import { projectTitle } from "./lib.jsx";

export default function AdHoc({ ctx, stored, suggestions }) {
  const { view, sessionId, busy, error, onAsk } = ctx;
  const turns = stored?.turns || [];

  return (
    <div className="centre-inner">
      <div className="spread" style={{ marginBottom: 16 }}>
        <div>
          <h2>{stored?.title || "New session"}</h2>
          <p className="small muted" style={{ margin: "2px 0 0" }}>
            {projectTitle(view.project)} · {view.rounds.length} rounds ·{" "}
            {view.n_designs} designs
          </p>
        </div>
      </div>

      {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

      {turns.length === 0 && (
        <Turn who="workbench">
          <p>
            This session is empty, and the project it is in is not. Ask anything below —
            the answer is assembled from the project's own artifacts rather than from
            anything said in this window, which is the difference a persistent decision
            state makes.
          </p>
          <p className="small muted">
            There is no live model in this build; that is phase 7. What runs today is a
            briefing read off disk, so every number in an answer has a file behind it and
            a function behind that.
          </p>
        </Turn>
      )}

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
  );
}
