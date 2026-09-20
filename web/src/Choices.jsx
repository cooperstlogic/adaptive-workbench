// The suggested asks, as the host presents a choice: the options, each with
// the prompt it sends, then *Let the agent decide*. Every option goes to the
// model in the centre seat when one is seated -- the option's `question` is
// the text sent, its title is what the bubble repeats -- except the one
// marked `registry`, which is a call to the laboratory's registry and says
// so where it sits. Without a seat the same options are answered from
// artifacts on disk by the briefing, as they were before decision 158, and
// the agent's option is not offered.
//
// The card appears only when the project's state gives a reason to suggest
// something, and the heading is that reason: a round at the lab, a flagged
// round nobody has ruled on, a round that came back quiet. A session with
// nothing pending gets a composer and no card. It shows until the first ask
// in the session or until skipped, and a small toggle brings it back.
//
// Options are numbered only when there is a choice to make between them; a
// lone option loses both the number and the gutter it sat in, because one
// option is one option and a "1" is a list pretending to be longer than it
// is. There is no "type your own" row: the composer is directly beneath and
// already says so.
//
// The card is workbench prose: nothing over it, no speaker.

export default function Choices({ options, canSend, busy, onPick, onSkip }) {
  const numbered = options.filter((o) => !o.agent && (o.key !== "live" || canSend));
  const agent = canSend ? options.find((o) => o.agent) : null;
  if (!numbered.length) return null;
  const lead = numbered.find((o) => o.lead);
  const many = numbered.length > 1;
  return (
    <div className="choices">
      <div className="choices-head">
        <h3 className="choices-title">{lead ? lead.lead : "What would you like to know?"}</h3>
        <button className="btn small" onClick={onSkip}>Skip</button>
      </div>
      {numbered.map((o, i) => (
        <button key={`${o.key}:${o.round ?? ""}`} className="choice" disabled={busy}
                onClick={() => onPick(o)}>
          {many && <span className="choice-n">{i + 1}</span>}
          <span className="choice-body">
            <span className="choice-head">{o.title || o.text}</span>
            {o.question && <span className="choice-q">{o.question}</span>}
            {o.pros && <span className="choice-pro">Pros: {o.pros}</span>}
            {o.cons && <span className="choice-con">Cons: {o.cons}</span>}
          </span>
        </button>
      ))}
      {agent && (
        <button className="choice choice-agent" disabled={busy} onClick={() => onPick(agent)}
                title={agent.question}>
          <span className="choice-n glyphic">✦</span>
          <span className="choice-body"><span className="choice-head">{agent.title}</span></span>
        </button>
      )}
    </div>
  );
}
