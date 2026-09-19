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

A third transcript, [`5b-host-round4.md`](5b-host-round4.md), is the same diagnosis run
in **Claude Science** in phase 5b, from the installed plugin. It is a demonstration
rather than a gate, and the difference is recorded below because it matters.

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

## The host run is not the gate, and the difference is the point

`5b-host-round4.md` was produced in Claude Science with the skill imported from GitHub
and both connectors installed as local commands. It reaches the same diagnosis: the
−1.014 pKD bridge offset, the cliff rejected because the shortfall is flat across the
edited positions rather than concentrated in a class, `apply_offset_correction`
recommended, the n=3 caveat carried. Every figure in it reproduces against `core/` to
the digit, and it wrote nothing into the repository.

**But the host session had the whole repository**, including `decision_004.json` and all
four documents the Claude Code gate removes. It said so and worked around it — *"A
proposed decision record for round 4 already exists on disk. I'll re-run the diagnostics
myself rather than take its reading on trust"* — then re-ran all five tests and
independently reproduced the numbers.

So it is strong evidence that the stack **runs and reproduces** in the host, and weaker
evidence of what the Claude Code gate tests, which is whether `SKILL.md` and the five
diagnostics are *sufficient on their own*. Criterion 3 stays anchored here, in the
harness that can be scripted, re-run after a skill edit, and committed. The repo carries
the proof; the host carries the pitch.

One honest difference in depth. The Claude Code run went a level further on the
remainder, with an ad hoc residue-level cut finding that 40 of 42 fresh designs carry
G102L against one measured observation of it. The host run reached the same conclusion —
*"the additive surrogate over-credits the dominant substitution when it is combined into
doubles"* — and stated it generally, without the cut that produces the number. Same
diagnosis, same action, same caveats, one level less specific.
