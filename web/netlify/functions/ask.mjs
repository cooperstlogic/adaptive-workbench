// The single stateless model proxy. One model turn per invocation; the loop
// lives in the browser, where the data and the sandbox already are.
//
// **It is not a proxy for the Claude API.** SPEC.md calls that the single
// most important line in its section, and it is enforced here rather than
// promised. The function builds the request itself: a system prompt that is
// the skill file (`lib/skill.mjs`, generated from SKILL.md by web/bundle.py),
// a fixed tool list, a model from a two-entry allowlist, fixed effort and
// a fixed output cap. A caller supplies four typed things -- which kind of
// turn, the project's state as `wb_driver.agent_context` read it, the
// session's transcript so far, and one new user turn -- and every one of
// them is checked. The transcript is the session's whole conversation, a
// diagnosis and the questions and the ruling that followed it, so a question
// can refer back to what was said; the record on disk, re-read into the
// context on every turn, is what was decided. The transcript is accepted
// only if this function signed it: each
// response ends with an HMAC over the full message list, and a transcript
// that does not verify is refused before a token is spent. So an assistant
// turn cannot be forged, a tool result can only answer a tool call the model
// actually made, and a question is a length-capped string. What is left is a
// low-effort model on an antibody-diagnosis prompt with a daily cap, which
// is not a free endpoint.
//
// **Everything the model can do is read.** `run_diagnostic` and
// `execute_analysis` run in the visitor's Pyodide and write nothing.
// `propose_decision` is how it hands a diagnosis back; the page gives that
// payload to `record_decision.py`, which refuses any number in it and
// recomputes every test. Non-negotiable 7 holds because the writer holds it.
//
// **Refusal is handled, and it is not hypothetical.** The hour-5 gate tripped
// the `bio` classifier three times. `fallbacks: "default"` re-runs a declined
// request server-side by refusal category; if the whole chain declines,
// `stop_reason` is `refusal` on a 200, and the closing event says so instead
// of rendering an empty bubble. The page treats it exactly as it treats the
// budget cap: replay, with the reason on the badge.

import Anthropic from "@anthropic-ai/sdk";
import { createHmac, createHash, timingSafeEqual } from "node:crypto";
import { account, check, costOf } from "./lib/budget.mjs";
import { SKILL_MD, SKILL_PATH, SKILL_SHA256 } from "./lib/skill.mjs";

export const MODELS = ["claude-sonnet-5", "claude-haiku-4-5-20251001"];
export const DEFAULT_MODEL = "claude-sonnet-5";
// Haiku 4.5 predates adaptive thinking and the effort parameter, and rejects
// both by name -- `adaptive thinking is not supported on this model`, then
// `This model does not support the effort parameter`. It is the one model on
// the list that needs the request shaped for it rather than for the family,
// so the two fields are omitted for it and nothing else changes: the same
// prompt, the same tools, the same cap, the same signed transcript. Probed
// against the live API before it was written down -- `fallbacks: "default"`
// it does accept.
export const NO_THINKING = ["claude-haiku-4-5-20251001"];
export const KINDS = ["diagnose", "ask", "chat"];
export const TURNS = ["diagnose", "question", "tool_results", "ruling"];
export const FALLBACK_BETA = "server-side-fallback-2026-07-01";
export const EFFORT = "low";
// The proposal turn is the long one: eight hypotheses with reasoning, three
// cuts with code and stdout, and a rationale, an alternatives paragraph and
// an if_wrong that a sceptic reads first. Thinking counts against the cap.
export const MAX_TOKENS = { diagnose: 16000, ask: 4096, chat: 2048 };

const LIMITS = {
  context_bytes: 400_000, question_chars: 4_000, note_chars: 4_000,
  tool_results: 8, tool_result_chars: 40_000, transcript_messages: 80,
};

const TESTS = ["offset_from_controls", "residual_by_plate", "residual_by_mutation_class",
               "replicate_concordance", "calibration_by_region"];
const READINGS = ["supported", "partially supported", "not supported", "inconclusive"];
const ACTIONS = ["apply_offset_correction", "drop_wells", "refit_only", "no_action"];
const CONFIDENCE = ["high", "medium", "low", "refuses"];

// --- the prompt -----------------------------------------------------------

export const PREAMBLE = `You are Claude, seated in a project session of Shannon Science: a thin layer over Claude Science that keeps persistent decision state across the experimental rounds of an antibody lead-optimization campaign. The skill below is the same file you would load in Claude Code or in Claude Science. Here its scripts are reachable as tools, and nothing else is:

- \`run_diagnostic\` is skills/adaptive-optimization/scripts/run_diagnostic.py: one named test from core/diagnostics.py, read-only. The template's permitted tests are the only names the tool accepts, and every argument is one of the values the script takes.
- \`execute_analysis\` is the ad hoc escape hatch the skill describes: a short read-only numpy analysis run against the project's own files, in the visitor's browser. The paths it can read are listed under \`paths\` in the context, relative to the working directory. It cannot reach the simulated laboratory or the registry. Its output is evidence a person reads and is never an input to a code path.
- \`propose_decision\` is record_decision.py --propose, and it is how you hand a diagnosis back. Name the tests; the script re-runs them itself and writes the numbers it gets. It refuses a payload that carries a result. List every ad hoc cut you ran, with its code and the stdout you received. It writes nothing else and it does not rule.

You cannot run the pipeline scripts, submit anything to the registry, or rule. A named person rules on what you propose, with four verbs, outside this conversation. If the ruling comes back as more_evidence_requested, run what was asked for and propose again; the record keeps both passes.

The project's state follows the skill, read from its own artifacts by the workbench. Every affinity value in it is synthetic: the landscape is generated and the assay is an oracle replaying it with noise. Say "synthetic" beside any number you quote.

The conversation is the session's. It may already hold a diagnosis, the questions asked since it, and a ruling, and a question may refer back to any of that. The project's state is re-read from its artifacts on every turn and is authoritative for what has been decided; the conversation is what was said.

How to work in this seat. Before each tool call, say in one or two plain sentences what you are about to run and why: what you know so far and what the result will tell you. Choose the second test from what the first returned. Keep the prose between calls brief; the recommendation's rationale, its alternatives and its if_wrong are where the writing belongs, and a sceptical scientist reads if_wrong first. When you are asked a question rather than to diagnose a round, answer it from the context and the two read tools, in prose, and do not propose. Do not include internal or system XML tags in your response.`;

export const skillFingerprint = () => SKILL_SHA256;

export function systemFor(kind, context) {
  if (kind === "chat") {
    return [{
      type: "text",
      text: "You are Claude, in a project session of Shannon Science, a layer over Claude Science. This project has no template: nothing has declared its objectives, its constraints, its model recipes or its diagnostics, and there is no state on disk to read. Answer plainly and briefly, and if the person asks what the project can do, say what has not been declared.",
    }];
  }
  return [
    { type: "text", text: PREAMBLE },
    { type: "text", text: SKILL_MD },
    {
      type: "text",
      text: "## The project, as its artifacts hold it\n\n```json\n"
        + JSON.stringify(context) + "\n```",
      cache_control: { type: "ephemeral" },
    },
  ];
}

// --- the tools ------------------------------------------------------------

const HYPOTHESIS_SCHEMA = {
  type: "object",
  properties: {
    id: { type: "string", description: "h1, h2, ..." },
    claim: { type: "string" },
    diagnostic: { type: "string", enum: TESTS },
    args: {
      type: "object",
      properties: {
        by: { type: "string", enum: ["position", "n_mutations"] },
        offset: { type: "string", enum: ["none", "bridge"] },
        scope: { type: "string", enum: ["all", "fresh"] },
      },
    },
    reading: { type: "string", enum: READINGS },
    reasoning: { type: "string" },
  },
  required: ["id", "claim", "diagnostic", "reading", "reasoning"],
};

export function toolsFor(kind, permitted) {
  if (kind === "chat") return [];
  const tests = TESTS.filter((t) => permitted.includes(t));
  const run_diagnostic = {
    name: "run_diagnostic",
    description: "Run one named test from core/diagnostics.py against the flagged round, "
      + "read-only, exactly as run_diagnostic.py would. Returns the test's record as JSON: "
      + "the result, the arguments, and the hashes of the snapshot and batch it read.",
    strict: true,
    input_schema: {
      type: "object",
      properties: {
        round: { type: "integer", description: "the round to read; the flagged one is focus_round in the context" },
        test: { type: "string", enum: tests },
        by: { type: "string", enum: ["position", "n_mutations"],
              description: "residual_by_mutation_class only; position otherwise" },
        offset: { type: "string", enum: ["none", "bridge"],
                  description: "calibration_by_region only: score the counterfactual moved by the recorded bridge estimate" },
        scope: { type: "string", enum: ["all", "fresh"],
                 description: "all designs the round predicted and measured, or only the fresh ones the flag was computed over" },
      },
      required: ["round", "test", "by", "offset", "scope"],
      additionalProperties: false,
    },
  };
  const execute_analysis = {
    name: "execute_analysis",
    description: "Run a short read-only numpy analysis against the project's files, in the "
      + "visitor's browser. Use it for the question the five library tests do not answer. "
      + "Read the JSON artifacts named under `paths` in the context with json.load(open(...)); "
      + "print what you find. Returns stdout, stderr and whether it ran. The simulated "
      + "laboratory and the registry are not reachable.",
    eager_input_streaming: true,
    input_schema: {
      type: "object",
      properties: {
        question: { type: "string", description: "the question this cut answers, one sentence" },
        code: { type: "string", description: "Python 3 with numpy and json; ten to forty lines" },
      },
      required: ["question", "code"],
    },
  };
  const propose_decision = {
    name: "propose_decision",
    description: "Hand the diagnosis to record_decision.py --propose. Name every hypothesis "
      + "you considered with the test it rests on and your reading; the script re-runs each "
      + "test and writes the numbers it gets. Include every ad hoc cut with its code and the "
      + "stdout it returned. A recommendation needs a rationale, the alternatives considered "
      + "and an if_wrong. This ends your turn; a named person rules next.",
    eager_input_streaming: true,
    input_schema: {
      type: "object",
      properties: {
        trigger: { type: "string" },
        hypotheses: { type: "array", items: HYPOTHESIS_SCHEMA, minItems: 1 },
        ad_hoc: {
          type: "array",
          items: {
            type: "object",
            properties: {
              question: { type: "string" }, code: { type: "string" }, stdout: { type: "string" },
            },
            required: ["question", "code", "stdout"],
          },
        },
        recommendation: {
          type: "object",
          properties: {
            action: { type: "string", enum: ACTIONS },
            confidence: { type: "string", enum: CONFIDENCE },
            parameters: { type: "object",
                          properties: { plates: { type: "array", items: { type: "string" } } } },
            rationale: { type: "string" },
            alternative_considered: { type: "string" },
            if_wrong: { type: "string" },
          },
          required: ["action", "confidence", "rationale", "alternative_considered", "if_wrong"],
        },
      },
      required: ["hypotheses", "recommendation"],
    },
  };
  return kind === "diagnose"
    ? [run_diagnostic, execute_analysis, propose_decision]
    : [run_diagnostic, execute_analysis];
}

// --- the signature --------------------------------------------------------

function secret() {
  const explicit = process.env.WORKBENCH_SIGNING_SECRET;
  if (explicit) return explicit;
  const key = process.env.ANTHROPIC_API_KEY || "";
  return createHash("sha256").update("workbench-transcript:" + key).digest("hex");
}

export function sign(messages) {
  return createHmac("sha256", secret()).update(JSON.stringify(messages)).digest("hex");
}

function verify(messages, signature) {
  const expected = Buffer.from(sign(messages), "utf8");
  const given = Buffer.from(String(signature || ""), "utf8");
  return expected.length === given.length && timingSafeEqual(expected, given);
}

// --- validation -----------------------------------------------------------

export class Refused extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

const isStr = (v, max) => typeof v === "string" && v.length <= max;

export function validate(body) {
  if (!body || typeof body !== "object") throw new Refused(400, "a JSON object");
  const kind = body.kind;
  if (!KINDS.includes(kind)) throw new Refused(400, `kind is one of ${KINDS.join(", ")}`);
  const model = body.model || DEFAULT_MODEL;
  if (!MODELS.includes(model)) throw new Refused(400, `model is one of ${MODELS.join(", ")}`);

  let context = null;
  if (kind !== "chat") {
    context = body.context;
    if (!context || typeof context !== "object") throw new Refused(400, "context is required");
    const bytes = Buffer.byteLength(JSON.stringify(context), "utf8");
    if (bytes > LIMITS.context_bytes) throw new Refused(413, `context is ${bytes} bytes; the cap is ${LIMITS.context_bytes}`);
    if (!context.project || typeof context.project.id !== "string") throw new Refused(400, "context.project.id");
    const permitted = context.tests && context.tests.permitted;
    if (!Array.isArray(permitted) || !permitted.length || !permitted.every((t) => TESTS.includes(t))) {
      throw new Refused(400, "context.tests.permitted names library tests only");
    }
  }

  let messages = [];
  if (body.transcript) {
    const t = body.transcript;
    if (!Array.isArray(t.messages) || t.messages.length > LIMITS.transcript_messages) {
      throw new Refused(400, "transcript.messages");
    }
    if (!verify(t.messages, t.signature)) {
      throw new Refused(403, "the transcript was not signed by this function");
    }
    messages = t.messages;
  }

  const turn = body.turn;
  if (!turn || !TURNS.includes(turn.type)) throw new Refused(400, `turn.type is one of ${TURNS.join(", ")}`);
  const last = messages[messages.length - 1];
  const pendingCalls = last && last.role === "assistant"
    ? last.content.filter((b) => b.type === "tool_use").map((b) => b.id) : [];

  let userMessage;
  if (turn.type === "tool_results") {
    if (!pendingCalls.length) throw new Refused(400, "no tool call is waiting for a result");
    const results = turn.results;
    if (!Array.isArray(results) || results.length > LIMITS.tool_results) throw new Refused(400, "turn.results");
    const ids = results.map((r) => r && r.tool_use_id);
    if (ids.length !== pendingCalls.length || pendingCalls.some((id) => !ids.includes(id))) {
      throw new Refused(400, "tool results must answer exactly the calls the model made");
    }
    userMessage = {
      role: "user",
      content: results.map((r) => {
        if (!isStr(r.content, LIMITS.tool_result_chars)) throw new Refused(413, "a tool result is too long");
        return { type: "tool_result", tool_use_id: r.tool_use_id, content: r.content,
                 is_error: !!r.is_error };
      }),
    };
  } else {
    // The session's transcript is one conversation: a diagnosis, the
    // questions asked after it, the ruling that sends it back. A proposal
    // ends the model's turn with its tool_use unanswered, so whatever turn
    // continues the transcript answers it in the same message -- one
    // tool_result per propose_decision call, then the turn's own text. Any
    // other unanswered call means the loop was cut off mid-turn, and that
    // transcript is not continued.
    let answers = [];
    if (pendingCalls.length) {
      const names = last.content.filter((b) => b.type === "tool_use").map((b) => b.name);
      if (names.some((n) => n !== "propose_decision")) {
        throw new Refused(400, "the model is waiting for tool results");
      }
      const results = turn.pending_results;
      if (!Array.isArray(results) || results.length !== pendingCalls.length
          || pendingCalls.some((id) => !results.some((r) => r && r.tool_use_id === id))) {
        throw new Refused(400, "a turn that continues a proposal carries the proposal's tool results");
      }
      answers = results.map((r) => {
        if (!isStr(r.content, LIMITS.tool_result_chars)) throw new Refused(413, "a tool result is too long");
        return { type: "tool_result", tool_use_id: r.tool_use_id, content: r.content,
                 is_error: !!r.is_error };
      });
    }
    let text;
    if (turn.type === "diagnose") {
      if (kind !== "diagnose") throw new Refused(400, "a diagnose turn belongs to a diagnose session");
      const r = context.focus_round;
      if (!Number.isInteger(r)) throw new Refused(400, "context.focus_round");
      text = `Round ${r} of the project at ${context.project.root} came back flagged and the loop has stopped. Work out what the round means and hand back a decision record with a recommendation a scientist can rule on, through propose_decision.`;
    } else if (turn.type === "question") {
      if (!isStr(turn.text, LIMITS.question_chars) || !turn.text.trim()) throw new Refused(400, "turn.text");
      text = turn.text.trim();
    } else {
      if (kind !== "diagnose") throw new Refused(400, "a ruling belongs to a diagnose session");
      const verdict = String(turn.verdict || "");
      if (verdict !== "more_evidence_requested") throw new Refused(400, "only more_evidence_requested comes back to the model");
      if (!isStr(turn.by, 120) || !isStr(turn.note || "", LIMITS.note_chars)) throw new Refused(400, "turn.by / turn.note");
      if (!TESTS.includes(turn.requested)) throw new Refused(400, "turn.requested names a library test");
      text = `The ruling on your recommendation is more_evidence_requested, by ${turn.by}. `
        + `Requested test: ${turn.requested}. Their note: ${JSON.stringify(turn.note || "")}. `
        + `Run what was asked for, read it against what you already found, and propose again through propose_decision; the record keeps both passes.`;
    }
    userMessage = { role: "user", content: [...answers, { type: "text", text }] };
  }

  return { kind, model, context, messages: [...messages, userMessage] };
}

// --- the request ----------------------------------------------------------

export function buildRequest({ kind, model, context, messages }) {
  const permitted = context ? context.tests.permitted : [];
  return {
    model,
    max_tokens: MAX_TOKENS[kind],
    ...(NO_THINKING.includes(model)
      ? {}
      : { thinking: { type: "adaptive" }, output_config: { effort: EFFORT } }),
    betas: [FALLBACK_BETA],
    fallbacks: "default",
    system: systemFor(kind, context),
    tools: toolsFor(kind, permitted),
    messages,
  };
}

// --- the handler ----------------------------------------------------------

const json = (status, body) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json", "cache-control": "no-store" },
});

function ipOf(request, context) {
  return (context && context.ip)
    || request.headers.get("x-nf-client-connection-ip")
    || request.headers.get("x-forwarded-for")
    || "local";
}

// The harness's scripted upstream -- lib/scripted.mjs -- is on only when the
// environment says so, which Netlify's never does. It is reported wherever
// the live flag is, so nothing that runs on it can be mistaken for a model.
const scripted = () => process.env.WORKBENCH_UPSTREAM === "scripted";

export async function probe(request, context) {
  const key = process.env.ANTHROPIC_API_KEY;
  const ip = ipOf(request, context);
  const b = await check(ip);
  const reason = !key && !scripted() ? "no key configured" : b.reason;
  return json(200, {
    live: (!!key || scripted()) && b.ok, reason, store: b.store, budget: b.budget,
    upstream: scripted() ? "scripted" : "anthropic",
    models: MODELS, default_model: DEFAULT_MODEL, effort: EFFORT,
    skill: { path: SKILL_PATH, sha256: SKILL_SHA256 },
  });
}

export default async function handler(request, context) {
  if (request.method === "GET") return probe(request, context);
  if (request.method !== "POST") return json(405, { error: "GET or POST" });

  let body;
  try {
    body = await request.json();
  } catch {
    return json(400, { error: "a JSON body" });
  }
  let turn;
  try {
    turn = validate(body);
  } catch (err) {
    if (err instanceof Refused) return json(err.status, { error: err.message });
    throw err;
  }

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key && !scripted()) {
    return json(503, { error: "no key configured", live: false, reason: "no key configured" });
  }
  const ip = ipOf(request, context);
  const b = await check(ip);
  if (!b.ok) return json(429, { error: b.reason, live: false, reason: b.reason, budget: b.budget });

  const client = scripted()
    ? (await import("./lib/scripted.mjs")).scriptedClient()
    : new Anthropic({ apiKey: key, maxRetries: 2 });
  const params = buildRequest(turn);
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const emit = (event, data) => controller.enqueue(
        encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      try {
        let message = null;
        for (let attempt = 0; attempt < 2 && !message; attempt++) {
          const upstream = client.beta.messages.stream(params);
          try {
            for await (const event of upstream) {
              if (event.type === "content_block_start" || event.type === "content_block_delta"
                  || event.type === "content_block_stop" || event.type === "message_delta") {
                emit(event.type, event);
              }
            }
            message = await upstream.finalMessage();
          } catch (err) {
            // Eager input streaming hands the client the parse: JSON the SDK
            // cannot read at all rejects here, once, and API errors do not.
            if (err instanceof Anthropic.APIError || attempt === 1) throw err;
            emit("retry", { reason: "the tool input was not parseable; re-issuing the turn" });
          }
        }
        const usage = message.usage;
        const cost = costOf(usage, message.model);
        const budget = await account(ip, cost);
        const messages = [...turn.messages, { role: "assistant", content: message.content }];
        const refusal = message.stop_reason === "refusal"
          ? { category: message.stop_details && message.stop_details.category,
              explanation: message.stop_details && message.stop_details.explanation }
          : null;
        const fallback = (usage && usage.iterations || []).some((i) => i.type === "fallback_message")
          ? message.model : null;
        emit("workbench", {
          message: { content: message.content, stop_reason: message.stop_reason,
                     model: message.model, usage },
          upstream: scripted() ? "scripted" : "anthropic",
          refusal, fallback,
          truncated: message.stop_reason === "max_tokens",
          transcript: { messages, signature: sign(messages) },
          cost_usd: Number(cost.toFixed(5)), budget,
        });
      } catch (err) {
        const status = err instanceof Anthropic.APIError ? err.status : 502;
        emit("error", { error: String(err.message || err), status });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: { "content-type": "text/event-stream", "cache-control": "no-store",
               "x-accel-buffering": "no" },
  });
}
