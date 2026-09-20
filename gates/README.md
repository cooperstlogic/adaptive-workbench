# The gates

Two acceptance criteria are claims about an *agent* rather than about code, so neither
can be asserted in a README. They are run, and the transcripts are here.

| | Criterion | Transcript |
| --- | --- | --- |
| Hour-5 gate | 3 — given the round-4 snapshot, produce a decision record that identifies the offset, rejects the cliff with the evidence that rejects it, and recommends the correction | [`hour5-round4.md`](hour5-round4.md) · [raw](hour5-round4.jsonl) |
| Full round | 2 — given only the skill and the two connectors, complete one full round unaided | [`criterion2-round1.md`](criterion2-round1.md) · [raw](criterion2-round1.jsonl) |
| Push-back | 8 — given the round-4 record ruled `more_evidence_requested`, run the test that was asked for, read it against the first pass, and propose again | [`pushback-round4.md`](pushback-round4.md) · [raw](pushback-round4.jsonl) |

All three ran on `claude-opus-5` through headless Claude Code, with both connectors loaded
from `.mcp.json`. Re-run any of them with `gates/run_gate.sh round4`,
`gates/run_gate.sh round1` or `gates/run_gate.sh round4-pushback`; the markdown is
rendered from the raw transcript by `gates/render_transcript.py`, mechanically.

A third transcript, [`5b-host-round4.md`](5b-host-round4.md), is the same diagnosis run
in **Claude Science** in phase 5b, from the installed plugin. It is a demonstration
rather than a gate, and the difference is recorded below because it matters.

## What the session was given, and what it was not

The gate builds a throwaway tree holding the code, the skill, the connectors and the
project. **`README.md` and `CLAUDE.md` are absent**, because both discuss round 4 and
the gate is supposed to test whether `SKILL.md` and the five
diagnostics are sufficient — not whether an agent can find an answer already written
down. `decision_004.json` is removed for the same reason; the round-4 run writes it.

`decision_002.json` **is** present, and the round-4 session read it. That is the round-2
record from phase 4, it is part of the project's own state, and a scientist picking up a
flagged round would read the last one too. It contains no round-4 numbers.

`data/` has to be in the tree, because the registry connector imports the oracle. The
gate denies `Read` on it and the prompt says it is off limits; afterwards the transcript
is grepped for any access. Both runs came back clean, and the round-1 session volunteered
"I did not read `data/`" without being asked. This is a guard and not a sandbox, and it
is stated as one rather than overclaimed.

## The prompt

Deliberately short, and it names no hypothesis:

> Round 4 of the project at `projects/demo-trastuzumab` came back flagged and the loop
> has stopped. Work out what the round means and write a decision record with a
> recommendation a scientist can rule on.

## The push-back gate, and what its first run taught

The third gate is the second half of acceptance criterion 8. The tree holds the committed
project *with* `decision_004.json` — pass 1, the hour-5 gate's own record, ruled
`more_evidence_requested` by d.webster with a note that quotes the record's `if_wrong`
back at it: the three bridge members all sit on R4P1, so run `residual_by_plate` on the
fresh designs alone. The prompt names no test and no answer. `record_decision.py` refuses
a second pass that does not run what was asked for, so the gate cannot be passed by
restating pass 1.

It was run twice, and the first run is not committed. That run answered the question
correctly and went one level further — the LIMS export carries a `well` column, and it
found the bridge sits in one *row* of R4P1 — but its second ad hoc cut read that export
from `/tmp/r4_readonly.csv`, the path it had handed `pull_assay_results` itself. A
reviewer on another machine, or the browser replaying the record from its own pull,
cannot run that. `SKILL.md` now says a cut reads the project directory and the round's
export where the registry writes it, by relative path, and nothing else; the second run
read only project files and its two cuts reproduce in the browser, which `check.py`
verifies. Same diagnosis, same action, one level less deep, and reproducible — that is
the trade the skill makes on purpose.

The first run also listed the real repository, because the plugin installed in phase 5
resolves its skill against this checkout, and saw in the listing that `README.md` and
`CLAUDE.md` exist there. It read none of them, and the
committed run named none of them, but a gate should not depend on restraint: the tree
now denies reads of the repository and the script greps the transcript for its path.

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
the proof; the host run shows it working where it would actually live.

One honest difference in depth. The Claude Code run went a level further on the
remainder, with an ad hoc residue-level cut finding that 40 of 42 fresh designs carry
G102L against one measured observation of it. The host run reached the same conclusion —
*"the additive surrogate over-credits the dominant substitution when it is combined into
doubles"* — and stated it generally, without the cut that produces the number. Same
diagnosis, same action, same caveats, one level less specific.
