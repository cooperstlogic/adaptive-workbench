# The gates

Two acceptance criteria are claims about an *agent* rather than about code, so neither
can be asserted in a README. They are run, and the transcripts are here.

| | Criterion | Transcript |
| --- | --- | --- |
| Hour-5 gate | 3 — given the round-4 snapshot, produce a decision record that identifies the offset, rejects the cliff with the evidence that rejects it, and recommends the correction | [`hour5-round4.md`](hour5-round4.md) · [raw](hour5-round4.jsonl) |
| Full round | 2 — given only the skill and the two connectors, complete one full round unaided | [`criterion2-round1.md`](criterion2-round1.md) · [raw](criterion2-round1.jsonl) |

Both ran on `claude-opus-5` through headless Claude Code, with both connectors loaded
from `.mcp.json`. Re-run either with `gates/run_gate.sh round4` or
`gates/run_gate.sh round1`.

## What the session was given, and what it was not

The gate builds a throwaway tree holding the code, the skill, the connectors and the
project. **`README.md`, `SPEC.md`, `DECISIONS.md` and `CLAUDE.md` are absent**, because
all four discuss round 4 and the gate is supposed to test whether `SKILL.md` and the five
diagnostics are sufficient — not whether an agent can find an answer already written
down. `decision_004.json` is removed for the same reason; the round-4 run writes it.

`decision_002.json` **is** present, and the round-4 session read it. That is the round-2
record from phase 4, it is part of the project's own state, and a scientist picking up a
flagged round would read the last one too. It contains no round-4 numbers.

`data/` has to be in the tree, because the registry connector imports the oracle. The
gate denies `Read` on it and the prompt says it is off limits; afterwards the transcript
is grepped for any access. Both runs came back clean, and the round-1 session volunteered
"I did not read `data/`" without being asked. This is a guard and not a sandbox, and
`DECISIONS.md` says so rather than overclaiming it.

## The prompt

Deliberately short, and it names no hypothesis:

> Round 4 of the project at `projects/demo-trastuzumab` came back flagged and the loop
> has stopped. Work out what the round means and write a decision record with a
> recommendation a scientist can rule on.

## One thing in the transcripts that is not the gate

Both sessions show an `API Error` immediately after the `Skill` call — a safeguard flag
on a turn about antibody engineering, tagged `[bio]`. The skill content did land (it is
in the raw transcript as the message after the tool call) and both sessions continued
without a retry. It is left in the committed transcripts rather than edited out, because
a transcript with the awkward part removed is not evidence.
