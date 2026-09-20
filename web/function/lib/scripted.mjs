// A scripted upstream, for the harness and nothing else.
//
// check.py has to prove the live loop round-trips -- the transcript is
// signed and verified, tool results answer the calls the model made, the
// proposal reaches record_decision.py -- without spending money or needing a
// key on the machine that runs it. So the function can be told, by an
// environment variable the site never sets, to take its model turns from a
// script instead of the API: the committed record's own sequence of tests,
// as the same SDK-shaped stream of events the real client would produce.
//
// It is a test double and it is labelled one. The probe reports it as
// `upstream: "scripted"`, the page badge would show it, and every number it
// leads to is still computed in Pyodide, because the script names tests and
// carries no results.

import { readFileSync } from "node:fs";

const MODEL = "scripted";

function plan() {
  const file = process.env.WORKBENCH_SCRIPT_FILE;
  if (!file) throw new Error("WORKBENCH_SCRIPT_FILE names the proposal to script from");
  return JSON.parse(readFileSync(file, "utf8"));
}

/** The turns one pass of the record expands to. */
function turnsFor(pass, round) {
  const out = [];
  for (const h of pass.hypotheses) {
    out.push({ text: `${h.id}: ${h.claim}`,
               tool: { name: "run_diagnostic", input: { round, test: h.diagnostic, by: h.args.by || "position",
                       offset: h.args.offset || "none", scope: h.args.scope || "all" } } });
  }
  for (const a of pass.ad_hoc || []) {
    out.push({ text: `The library has no cut for this: ${a.question}`,
               tool: { name: "execute_analysis", input: { question: a.question, code: a.code } } });
  }
  out.push({ text: `Recommendation: ${pass.recommendation.action}, confidence ${pass.recommendation.confidence}.`,
             tool: { name: "propose_decision", proposal: pass } });
  return out;
}

/** Which pass the transcript is in, and how many assistant turns it holds. */
function position(messages) {
  const passIndex = messages.filter((m) => m.role === "user" && Array.isArray(m.content)
    && m.content.some((b) => b.type === "text" && /more_evidence_requested/.test(b.text))).length;
  let k = 0;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "user" && Array.isArray(m.content)
        && m.content.some((b) => b.type === "text" && !/^\s*$/.test(b.text))) break;
    if (m.role === "assistant") k += 1;
  }
  return { passIndex, k };
}

/** The stdout each execute_analysis got back, read from the transcript like a model would. */
function stdouts(messages) {
  const byId = new Map();
  for (const m of messages) {
    if (m.role !== "assistant") continue;
    for (const b of m.content) if (b.type === "tool_use") byId.set(b.id, b);
  }
  const out = [];
  for (const m of messages) {
    if (m.role !== "user" || !Array.isArray(m.content)) continue;
    for (const b of m.content) {
      if (b.type !== "tool_result") continue;
      const call = byId.get(b.tool_use_id);
      if (call && call.name === "execute_analysis") {
        try { out.push(JSON.parse(b.content).stdout || ""); } catch { out.push(""); }
      }
    }
  }
  return out;
}

function events(content) {
  const out = [];
  content.forEach((block, index) => {
    if (block.type === "text") {
      out.push({ type: "content_block_start", index, content_block: { type: "text", text: "" } });
      out.push({ type: "content_block_delta", index, delta: { type: "text_delta", text: block.text } });
    } else {
      out.push({ type: "content_block_start", index,
                 content_block: { type: "tool_use", id: block.id, name: block.name, input: {} } });
      out.push({ type: "content_block_delta", index,
                 delta: { type: "input_json_delta", partial_json: JSON.stringify(block.input) } });
    }
    out.push({ type: "content_block_stop", index });
  });
  return out;
}

export function scriptedClient() {
  const record = plan();
  return {
    beta: { messages: { stream(params) {
      const offered = new Set((params.tools || []).map((t) => t.name));
      if (!offered.has("propose_decision")) {
        // An ask or a chat. The script has no answer to give, so it says
        // what it was handed -- which is what the harness checks: that the
        // question arrived on the session's transcript, not a fresh one.
        const prior = params.messages.filter((m) => m.role === "assistant").length;
        const text = `(scripted upstream) answering from a transcript with ${prior} earlier assistant turns`;
        const content = [{ type: "text", text }];
        const message = {
          id: `msg_scripted_ask_${prior}`, type: "message", role: "assistant",
          model: MODEL, content, stop_details: null, stop_reason: "end_turn",
          usage: { input_tokens: 0, output_tokens: 0, cache_creation_input_tokens: 0,
                   cache_read_input_tokens: 0 },
        };
        return {
          async *[Symbol.asyncIterator]() { for (const e of events(content)) yield e; },
          async finalMessage() { return message; },
        };
      }
      const { passIndex, k } = position(params.messages);
      const pass = record.passes[Math.min(passIndex, record.passes.length - 1)];
      const turns = turnsFor(pass, record.round);
      const step = turns[Math.min(k, turns.length - 1)];
      const id = `toolu_scripted_${passIndex}_${k}`;
      let input = step.tool.input;
      if (step.tool.name === "propose_decision") {
        const outs = stdouts(params.messages);
        const p = step.tool.proposal;
        input = {
          trigger: record.trigger,
          hypotheses: p.hypotheses,
          ad_hoc: (p.ad_hoc || []).map((a, i) => ({ question: a.question, code: a.code,
                                                    stdout: outs[i] || "" })),
          recommendation: p.recommendation,
        };
      }
      // A tool the request did not offer is not called: the turn ends in
      // text instead.
      const content = offered.has(step.tool.name)
        ? [{ type: "text", text: step.text },
           { type: "tool_use", id, name: step.tool.name, input }]
        : [{ type: "text", text: `${step.text} (scripted upstream: ${step.tool.name} was not offered, so this is the answer)` }];
      const message = {
        id: `msg_scripted_${passIndex}_${k}`, type: "message", role: "assistant",
        model: MODEL, content, stop_details: null,
        stop_reason: offered.has(step.tool.name) ? "tool_use" : "end_turn",
        usage: { input_tokens: 0, output_tokens: 0, cache_creation_input_tokens: 0,
                 cache_read_input_tokens: 0 },
      };
      const stream = {
        async *[Symbol.asyncIterator]() { for (const e of events(content)) yield e; },
        async finalMessage() { return message; },
      };
      return stream;
    } } },
  };
}
