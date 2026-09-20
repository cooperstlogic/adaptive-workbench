// The agent in the session: one stream of steps, two sources.
//
// **Live.** `runLive` owns the `while stop_reason == "tool_use"` loop. Each
// model turn is one call to the stateless function; every tool the model
// names runs here, in the visitor's Pyodide, through the same `wb_driver`
// calls the buttons use, so each one lands in the command log with its exit
// code and both output streams. The transcript comes back signed and goes
// back verbatim; this file never edits it. It is the session's: a diagnosis,
// the questions asked after it and the ruling that sends it back all
// continue the one conversation, and the caller hands in where it got to.
// When the function will not continue it -- signed under another key, or
// grown past the cap -- the turn starts a fresh one from the record and
// says so on itself, rather than ending.
//
// **Replay.** `runReplay` walks the committed record's claims through the
// same emitter: for each hypothesis, the claim, then the test actually run
// here and hash-checked against the record, then the reading; for each ad
// hoc cut, its code run again and its stdout compared; then the proposal
// handed to `record_decision.py` exactly as a live one is. A cold visitor
// with no key watches the diagnosis happen, and every number on screen was
// computed in their tab.
//
// Nothing in here renders, and nothing in here is bound to the page: `call`
// is passed in, so `web/scripts/pyodide-check.mjs` drives the same code in
// node and hands the artifacts to check.py.

export const ENDPOINT = "/api/ask";

// --- the access code --------------------------------------------------------
//
// The live seat on the public URL is open to whoever was sent the link, and
// the link carries the code: `?code=…` before the hash. The page keeps it in
// localStorage, takes it off the address bar, and sends it on every call.
// Without it the function answers its probe with the reason and the page is
// in replay, which is the same page a visitor without a key gets.

const CODE_KEY = "workbench-code";
const CODE_HEADER = "x-workbench-code";

export function adoptCode(loc = globalThis.location, storage = globalThis.localStorage) {
  try {
    const url = new URL(loc.href);
    const code = url.searchParams.get("code");
    if (!code) return;
    storage.setItem(CODE_KEY, code);
    url.searchParams.delete("code");
    history.replaceState(null, "", url.pathname + url.search + url.hash);
  } catch { /* a private window, or no window at all */ }
}

function headers(extra = {}) {
  let code = null;
  try { code = localStorage.getItem(CODE_KEY); } catch { /* private window */ }
  return code ? { ...extra, [CODE_HEADER]: code } : extra;
}

// --- the probe --------------------------------------------------------------

export async function probe(fetchImpl = globalThis.fetch, base = "") {
  try {
    const res = await fetchImpl(`${base}${ENDPOINT}`, { method: "GET", headers: headers() });
    if (!res.ok) return { live: false, reason: `probe returned ${res.status}` };
    return await res.json();
  } catch (err) {
    return { live: false, reason: "no function reachable" };
  }
}

// --- server-sent events -----------------------------------------------------

async function* sse(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let event = "message", data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) yield { event, data: JSON.parse(data) };
    }
  }
}

// --- tools, as the driver runs them ----------------------------------------

/** The arguments a test takes and nothing else, so the log reads as the CLI. */
export function diagnosticArgs(input) {
  const out = { test: input.test };
  if (input.test === "residual_by_mutation_class" && input.by) out.by = input.by;
  if (input.test === "calibration_by_region" && input.offset && input.offset !== "none") {
    out.offset = input.offset;
  }
  if (input.scope && input.scope !== "all") out.scope = input.scope;
  return out;
}

export function runTool({ name, input }, { call, project, round, session, verify }) {
  if (name === "run_diagnostic") {
    const args = diagnosticArgs(input || {});
    const target = Number.isInteger(input && input.round) ? input.round : round;
    const out = call("diagnostic", { round_id: target, project, session, ...args, verify });
    return { entry: out.log, content: JSON.stringify(out.result), verified: out.verified };
  }
  if (name === "execute_analysis") {
    const out = call("execute_analysis", {
      code: input.code, question: input.question, round_id: round, project, session, verify,
    });
    return {
      entry: out.log,
      content: JSON.stringify({ ok: out.ok, stdout: out.stdout, stderr: out.stderr }),
      is_error: !out.ok,
      verified: out.verified,
      stdout: out.stdout,
    };
  }
  if (name === "propose_decision") {
    const payload = {
      trigger: input.trigger, hypotheses: input.hypotheses,
      recommendation: input.recommendation, ad_hoc: input.ad_hoc || [],
    };
    try {
      const decision = call("propose", { round_id: round, project, session, payload });
      return {
        decision,
        content: `recorded ${decision.id} pass ${decision.n_passes}, status ${decision.status}. `
          + "A named person rules next.",
      };
    } catch (err) {
      // The writer refused the payload. That refusal is the rule working, and
      // it goes back to the model as an error result so it can answer it.
      return { content: String(err.message || err), is_error: true, refused: true };
    }
  }
  return { content: `no such tool: ${name}`, is_error: true };
}

// --- the live loop ------------------------------------------------------------

const MAX_TURNS = 24;

/**
 * Drive one live agent turn to completion.
 *
 * kind: "diagnose" | "ask" | "chat". For diagnose, `ruling` continues a
 * record with a more_evidence_requested ruling. `transcript` is the
 * session's signed conversation so far and `pending` the tool result
 * answering the proposal it ended on, if it did; both come off the previous
 * turn's `transcript` and `pending`. `emit` receives every step as it
 * happens; `save` receives the accumulated turn whenever it changes.
 */
export async function runLive({
  kind, project, round, session, question, model, ruling, transcript = null, pending = null,
  call, emit = () => {}, save = () => {}, fetchImpl = globalThis.fetch, base = "",
  id = `live-${Date.now()}`, at = new Date().toISOString(),
}) {
  // `task` and not `kind`: the driver stamps `kind: "agent"` on every stored
  // agent turn so the page can tell it from an ask.
  const turn = {
    id, mode: "live", task: kind, model, round: round ?? null, at, question: question || null,
    pass: ruling ? 2 : 1,
    steps: [], status: "running", stop: null, usage: { input: 0, output: 0, cost_usd: 0 },
    verified: null, transcript: null, pending: null, restarted: null,
  };
  const push = (step) => { turn.steps.push(step); emit(step); save(turn); return step; };

  let context = null;
  if (kind !== "chat") context = call("agent_context", { project, round_id: round ?? null });
  // An ad-hoc session has no round of its own; tools that need one read the
  // round the context is focused on unless the call names another.
  const toolRound = round ?? (context ? context.focus_round : null);
  let nextTurn;
  if (kind === "diagnose") {
    nextTurn = ruling
      ? { type: "ruling", verdict: ruling.verdict, by: ruling.by, note: ruling.note,
          requested: ruling.requested }
      : { type: "diagnose" };
  } else {
    nextTurn = { type: "question", text: question };
  }
  let signed = transcript;
  if (signed && pending) nextTurn = { ...nextTurn, pending_results: pending };

  for (let i = 0; i < MAX_TURNS; i++) {
    const res = await fetchImpl(`${base}${ENDPOINT}`, {
      method: "POST",
      headers: headers({ "content-type": "application/json" }),
      body: JSON.stringify({ kind, model, context, transcript: signed, turn: nextTurn }),
    });
    if (!res.ok) {
      let why = `${res.status}`;
      try {
        const body = await res.json();
        why = body.reason || body.error || why;
      } catch { /* keep the status */ }
      if (signed && !turn.restarted && (res.status === 403
          || (res.status === 400 && /transcript|tool results/.test(why)))) {
        // The function will not continue the conversation it was handed: it
        // was signed under another key, or it has outgrown the cap. Nothing
        // was spent. The turn starts over from the record, which carries
        // everything that was decided, and carries the reason on itself.
        signed = null;
        const { pending_results, ...fresh } = nextTurn;
        nextTurn = fresh;
        turn.restarted = why;
        save(turn);
        continue;
      }
      turn.status = "stopped";
      turn.stop = { reason: why, kind: res.status === 429 ? "budget" : "error" };
      push({ type: "stop", reason: why });
      return turn;
    }

    let final = null;
    let text = null;
    let toolInput = null;
    for await (const { event, data } of sse(res.body)) {
      if (event === "content_block_start" && data.content_block.type === "text") {
        text = push({ type: "text", text: "" });
      } else if (event === "content_block_start" && data.content_block.type === "tool_use") {
        toolInput = { name: data.content_block.name, json: "" };
        turn.writing = toolInput.name;
        emit({ type: "tool_start", name: toolInput.name });
      } else if (event === "content_block_delta" && data.delta.type === "text_delta") {
        if (!text) text = push({ type: "text", text: "" });
        text.text += data.delta.text;
        emit({ type: "text_delta", delta: data.delta.text });
      } else if (event === "content_block_delta" && data.delta.type === "input_json_delta") {
        if (toolInput) { toolInput.json += data.delta.partial_json; }
        emit({ type: "tool_input_delta", name: toolInput && toolInput.name,
               delta: data.delta.partial_json });
      } else if (event === "content_block_stop") {
        if (text) { save(turn); text = null; }
        if (toolInput) { turn.writing = null; emit({ type: "tool_written", name: toolInput.name }); }
        toolInput = null;
      } else if (event === "workbench") {
        final = data;
      } else if (event === "error") {
        turn.status = "stopped";
        turn.stop = { reason: data.error, kind: "error" };
        push({ type: "stop", reason: data.error });
        return turn;
      }
    }
    if (!final) {
      turn.status = "stopped";
      turn.stop = { reason: "the stream ended without a message", kind: "error" };
      push({ type: "stop", reason: turn.stop.reason });
      return turn;
    }

    // The conversation only advances on the turn once the turn is done: a
    // transcript cut off between a call and its result is not one the
    // session continues from.
    signed = final.transcript;
    turn.model = final.message.model || turn.model;
    turn.usage.input += (final.message.usage && final.message.usage.input_tokens) || 0;
    turn.usage.output += (final.message.usage && final.message.usage.output_tokens) || 0;
    turn.usage.cost_usd += final.cost_usd || 0;
    turn.budget = final.budget;
    turn.upstream = final.upstream || "anthropic";
    if (final.fallback) turn.fallback = final.fallback;

    if (final.refusal) {
      turn.status = "stopped";
      turn.stop = { reason: `declined (${final.refusal.category || "policy"})`, kind: "refusal" };
      push({ type: "stop", reason: turn.stop.reason });
      return turn;
    }
    if (final.truncated) {
      turn.status = "stopped";
      turn.stop = { reason: "the turn hit its output cap", kind: "truncated" };
      push({ type: "stop", reason: turn.stop.reason });
      return turn;
    }

    const calls = final.message.content.filter((b) => b.type === "tool_use");
    if (!calls.length) {
      turn.status = "done";
      turn.transcript = signed;
      save(turn);
      return turn;
    }

    const results = [];
    let proposed = false;
    for (const c of calls) {
      const out = runTool(c, { call, project, round: toolRound, session });
      if (out.entry) {
        // The entry rides on the step while the turn streams, so the chip can
        // render before the page re-reads the log; the stored copy drops it
        // and finds the entry by its number.
        push({ type: "tool", name: c.name, n: out.entry.n, input: summarize(c.name, c.input),
               verified: out.verified || null, entry: out.entry });
      }
      if (out.decision) {
        proposed = true;
        push({ type: "proposal", decision_id: out.decision.id, pass: out.decision.n_passes,
               action: out.decision.recommendation.action,
               confidence: out.decision.recommendation.confidence,
               n_hypotheses: out.decision.hypotheses.length });
      } else if (out.refused) {
        push({ type: "refused", text: out.content });
      }
      results.push({ tool_use_id: c.id, content: out.content, is_error: !!out.is_error });
    }
    if (proposed) {
      // The proposal ends the turn. The tool_result answering it travels with
      // whatever continues the session -- a question, the ruling -- so the
      // transcript stays continuous.
      turn.pending = results;
      turn.status = "done";
      turn.transcript = signed;
      save(turn);
      return turn;
    }
    nextTurn = { type: "tool_results", results };
  }
  turn.status = "stopped";
  turn.stop = { reason: `stopped after ${MAX_TURNS} turns`, kind: "limit" };
  push({ type: "stop", reason: turn.stop.reason });
  return turn;
}

function summarize(name, input) {
  if (name === "run_diagnostic") return diagnosticArgs(input || {});
  if (name === "execute_analysis") return { question: (input || {}).question };
  if (name === "propose_decision") {
    const p = input || {};
    return { hypotheses: (p.hypotheses || []).length,
             action: p.recommendation && p.recommendation.action };
  }
  return input;
}

// --- replay -------------------------------------------------------------------

const sleep = (ms) => (ms > 0 ? new Promise((r) => setTimeout(r, ms)) : Promise.resolve());

/**
 * Step the committed record's pass through the same emitter. Every test is
 * run here and checked against the record; the proposal is written by the
 * same script a live one goes through.
 */
export async function runReplay({
  project, round, session, plan, pass = 1, call, emit = () => {}, save = () => {},
  delay = 350, id = `replay-${Date.now()}`, at = new Date().toISOString(),
}) {
  const p = (plan.passes || []).find((x) => Number(x.pass) === Number(pass));
  if (!p) throw new Error(`the record has no pass ${pass}`);
  const turn = {
    id, mode: "replay", task: "diagnose", model: null, round, at, question: null,
    pass, steps: [], status: "running", stop: null,
    verified: { diagnostics: 0, of_diagnostics: 0, ad_hoc: 0, of_ad_hoc: 0 },
    source_record: plan.source_record,
  };
  const push = (step) => { turn.steps.push(step); emit(step); save(turn); return step; };

  if (p.answering) {
    push({ type: "text", text: `Answering the ruling: running ${p.answering} as asked, and reading it against what the first pass found.` });
    await sleep(delay);
  }
  for (const h of p.hypotheses) {
    push({ type: "text", text: `${h.id}: ${h.claim}` });
    await sleep(delay);
    const out = runTool({ name: "run_diagnostic", input: { test: h.diagnostic, ...h.args } },
                        { call, project, round, session, verify: { pass, hypothesis: h.id } });
    turn.verified.of_diagnostics += 1;
    if (out.verified && out.verified.matched) turn.verified.diagnostics += 1;
    push({ type: "tool", name: "run_diagnostic", n: out.entry.n,
           input: diagnosticArgs({ test: h.diagnostic, ...h.args }), verified: out.verified,
           entry: out.entry });
    await sleep(delay);
    push({ type: "text", text: `${h.reading}. ${h.reasoning}`, reading: h.reading });
    await sleep(delay);
  }
  const adHoc = [];
  for (const [i, a] of (p.ad_hoc || []).entries()) {
    push({ type: "text", text: `The library has no cut for this, so: ${a.question}` });
    await sleep(delay);
    const out = runTool({ name: "execute_analysis", input: { question: a.question, code: a.code } },
                        { call, project, round, session, verify: { pass, index: i } });
    turn.verified.of_ad_hoc += 1;
    if (out.verified && out.verified.matched) turn.verified.ad_hoc += 1;
    push({ type: "tool", name: "execute_analysis", n: out.entry.n,
           input: { question: a.question }, verified: out.verified, entry: out.entry });
    adHoc.push({ question: a.question, code: a.code, stdout: out.stdout || "" });
    await sleep(delay);
  }
  const rec = p.recommendation;
  push({ type: "text", text: `Recommendation: ${rec.action.replace(/_/g, " ")}, confidence ${rec.confidence}.` });
  await sleep(delay);
  const out = runTool({
    name: "propose_decision",
    input: { trigger: plan.trigger, hypotheses: p.hypotheses, ad_hoc: adHoc, recommendation: rec },
  }, { call, project, round, session });
  if (out.decision) {
    push({ type: "proposal", decision_id: out.decision.id, pass: out.decision.n_passes,
           action: out.decision.recommendation.action,
           confidence: out.decision.recommendation.confidence,
           n_hypotheses: out.decision.hypotheses.length });
    turn.status = "done";
  } else {
    push({ type: "refused", text: out.content });
    turn.status = "stopped";
    turn.stop = { reason: out.content, kind: "refused" };
  }
  save(turn);
  return turn;
}

/** The recorded ruling that sent a pass back, if the record has one. */
export function recordedPushback(plan, pass = 1) {
  const p = (plan && plan.passes || []).find((x) => Number(x.pass) === Number(pass));
  const r = p && p.ruling;
  if (!r || r.verdict !== "more_evidence_requested") return null;
  return { verdict: r.verdict, by: r.by, note: r.note,
           requested: r.requested && r.requested.diagnostic };
}
