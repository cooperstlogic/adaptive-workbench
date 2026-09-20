#!/usr/bin/env python3
"""Render a headless Claude Code transcript (stream-json) as the gate's markdown.

    .venv/bin/python gates/render_transcript.py TREE/transcript.jsonl \\
        --title "Push-back gate: answering the ruling on round 4" \\
        --out gates/pushback-round4.md

The committed transcripts are evidence, so the rendering is mechanical: every
assistant text block in order, every tool call as the command it ran, and the
final report verbatim. Nothing is summarized and nothing awkward is removed --
a safeguard refusal in the middle of a run stays in the middle of the run.
"""

import argparse
import json
import textwrap

WRAP = 90


def _tool(block):
    name, inp = block.get("name"), block.get("input") or {}
    if name == "Bash":
        return "```console\n$ %s\n```" % inp.get("command", "").rstrip()
    if name in ("Read", "Glob", "Grep"):
        arg = inp.get("file_path") or inp.get("pattern") or ""
        return "```\n%s  %s\n```" % (name, arg)
    if name in ("Write", "Edit"):
        return "```\n%s  %s\n```" % (name, inp.get("file_path", ""))
    return "```\n%s  %s\n```" % (name, json.dumps(inp, indent=1))


def render(rows, title, prompt=None):
    init = next((r for r in rows if r.get("type") == "system" and r.get("subtype") == "init"), {})
    result = next((r for r in rows if r.get("type") == "result"), {})
    servers = ", ".join("`%s` %s" % (s["name"], s["status"]) for s in init.get("mcp_servers", []))
    # The prompt itself is not in the stream; it is passed in from the gate
    # script. The fallback is the first user text, which is usually a skill's.
    prompt = prompt or next((b.get("text") for r in rows if r.get("type") == "user"
                             for b in ((r.get("message") or {}).get("content") or [])
                             if isinstance(b, dict) and b.get("type") == "text"
                             and b.get("text")), "")
    head = [
        "# %s" % title, "",
        "| | |", "| --- | --- |",
        "| Model | `%s` |" % init.get("model", "?"),
        "| Connectors | %s |" % servers,
        "| Turns | %s |" % result.get("num_turns", "?"),
        "| Wall clock | %d s |" % round((result.get("duration_ms") or 0) / 1000),
        "| Cost | $%.2f |" % (result.get("total_cost_usd") or 0),
        "| Outcome | %s |" % result.get("subtype", "?"),
        "", "## The prompt, in full", "", "```", prompt.strip(), "```", "",
        "## What it did", "",
    ]
    body = []
    for r in rows:
        if r.get("type") != "assistant":
            continue
        for block in (r.get("message") or {}).get("content") or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                for para in block["text"].strip().split("\n\n"):
                    if para.lstrip().startswith(("```", "|", "-", "*", "#", "1.")):
                        body.append(para)
                    else:
                        body.append(textwrap.fill(para, WRAP))
                    body.append("")
            elif block.get("type") == "tool_use":
                body.append(_tool(block))
                body.append("")
    final = (result.get("result") or "").strip()
    tail = ["## What it reported back", "", final, ""] if final else []
    return "\n".join(head + body + tail)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prompt", default=None, help="the prompt the session was given")
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in open(args.transcript, encoding="utf-8") if line.strip()]
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(render(rows, args.title, args.prompt))
    print("wrote %s (%d rows)" % (args.out, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
