#!/bin/zsh
# Re-run an hour-5 gate. The point of this script is that the gate is a thing
# you run, not a thing the README claims happened.
#
#   gates/run_gate.sh round4     diagnose the flagged round and write a record
#   gates/run_gate.sh round1     run one full round end to end on a new project
#
# It builds a throwaway tree holding only what the gate is entitled to -- the
# code, the skill, the connectors and the project -- and points a headless
# Claude Code session at it. README.md, SPEC.md, DECISIONS.md and CLAUDE.md are
# deliberately absent, because all four discuss round 4 and the gate would
# otherwise be testing whether an agent can find an answer already written down.
#
# `data/` has to be present, because the registry connector imports the oracle.
# The gate tree denies Read on it and the prompt says it is off limits, and the
# transcript is grepped afterwards to confirm nothing reached it. That is a
# guard rather than a sandbox, and DECISIONS.md decision 97 says so plainly.

set -e
WHICH="${1:-round4}"
REPO="${0:A:h:h}"
TREE="${TMPDIR:-/tmp}/adaptive-gate-$WHICH"

rm -rf "$TREE"; mkdir -p "$TREE"
cd "$REPO"
for d in core data skills connectors templates; do
  rsync -a --exclude='__pycache__' --exclude='.DS_Store' "$d" "$TREE/"
done
cp lims.py run_rounds.py init_project.py .mcp.json "$TREE/"
ln -s "$REPO/.venv" "$TREE/.venv"
mkdir -p "$TREE/.claude/skills" "$TREE/projects" "$TREE/lims_store"
rsync -a --exclude='__pycache__' --exclude='.DS_Store' \
      skills/adaptive-optimization "$TREE/.claude/skills/"
cat > "$TREE/.claude/settings.json" <<'JSON'
{ "permissions": { "deny": ["Read(./data/**)", "Read(./lims_store/**)"] } }
JSON

OFFLIMITS='

The data/ directory is the simulated laboratory. It holds ground truth the workbench is never allowed to see, so do not read it.'

if [[ "$WHICH" == "round4" ]]; then
  rsync -a --exclude='__pycache__' --exclude='.DS_Store' \
        projects/demo-trastuzumab "$TREE/projects/"
  rsync -a lims_store/demo-trastuzumab.json "$TREE/lims_store/"
  # The gate writes this record. Handing it the answer would make it a formality.
  rm -f "$TREE/projects/demo-trastuzumab/decisions/decision_004.json"
  PROMPT="Round 4 of the project at projects/demo-trastuzumab came back flagged and the loop has stopped. Work out what the round means and write a decision record with a recommendation a scientist can rule on.${OFFLIMITS}"
else
  (cd "$TREE" && .venv/bin/python init_project.py --name gate-round1 --team a.gate --force >/dev/null)
  PROMPT="The project at projects/gate-round1 was just created and has no designs yet. Run round 1 end to end: get the batch selected, tested and the results imported and modelled, so the project is ready to choose round 2. Report what came back.${OFFLIMITS}"
fi

cd "$TREE"
echo "gate tree: $TREE"
claude -p "$PROMPT" \
  --model opus \
  --mcp-config .mcp.json --strict-mcp-config \
  --output-format stream-json --verbose \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,Skill,TodoWrite,mcp__registry__submit_batch,mcp__registry__pull_assay_results,mcp__registry__list_designs,mcp__registry__get_construct,mcp__registry__attach_recommendation,mcp__bioprovider__embed_sequences,mcp__bioprovider__score_properties,mcp__bioprovider__predict_structures" \
  | tee "$TREE/transcript.jsonl" >/dev/null

echo "transcript: $TREE/transcript.jsonl"
grep -c 'landscape.npz\|data/synthetic\|data/oracle' "$TREE/transcript.jsonl" \
  && echo "LEAK: the session reached the simulated laboratory" \
  || echo "clean: nothing in the transcript touched data/"
