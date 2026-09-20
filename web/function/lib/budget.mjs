// The daily spend cap and the per-address counter.
//
// A global daily spend cap and a per-IP counter live in a store the
// host provides. Under the cap the session runs live; over it the site
// returns to replay, which is the default that live calls temporarily
// upgrade. The cap exists so a public URL cannot run up a bill, not to meter
// anyone.
//
// **The cap is reserved before the turn, not written after it.** A model
// turn runs five to thirty seconds, and a counter read before it and written
// after it lets every request that arrives in between pass on the same stale
// read: a burst of a hundred is a hundred times the call's maximum before the
// store hears about any of them. So a call takes its maximum out of the day
// atomically before a token is spent -- an increment whose returned value is
// the check, rolled back if it overshot -- and settles to what it actually
// cost when the turn ends. The same for the per-address count and a small
// in-flight count, which is a throttle rather than a cap: it keeps a burst
// from spending the day in a second. Decision 161.
//
// The store is Upstash Redis, reached over its REST API, which is what the
// Vercel marketplace provisions and what a function that may be running in
// several instances at once needs: counters every instance increments and
// every instance sees (decision 159). Anywhere the store's two variables are
// not set (the Vite dev server, check.py's harness) the counters live in
// memory and reset with the process. That is the honest local behaviour and
// it is labelled in the probe as `store`.

import { createHash } from "node:crypto";

// Anthropic first-party rates, USD per million tokens. Cache writes bill at
// 1.25x input and cache reads at 0.1x -- the same ratios on every model.
export const PRICES = {
  "claude-opus-5": { input: 5.0, output: 25.0 },
  "claude-opus-4-8": { input: 5.0, output: 25.0 },
  "claude-sonnet-5": { input: 2.0, output: 10.0 },
  "claude-haiku-4-5": { input: 1.0, output: 5.0 },
  "claude-haiku-4-5-20251001": { input: 1.0, output: 5.0 },
};

export function costOf(usage, model) {
  const p = PRICES[model] || PRICES["claude-opus-5"];
  const u = usage || {};
  const input = (u.input_tokens || 0) * p.input;
  const written = (u.cache_creation_input_tokens || 0) * p.input * 1.25;
  const read = (u.cache_read_input_tokens || 0) * p.input * 0.1;
  const output = (u.output_tokens || 0) * p.output;
  return (input + written + read + output) / 1e6;
}

/** The most a call could cost: every input token written to cache, every
 * output token up to the cap. What a call reserves before it is made. */
export function maxCostOf({ model, input_tokens, max_tokens }) {
  const p = PRICES[model] || PRICES["claude-opus-5"];
  return ((input_tokens || 0) * p.input * 1.25 + (max_tokens || 0) * p.output) / 1e6;
}

export const dayKey = (now = new Date()) => now.toISOString().slice(0, 10);

export const hashIp = (ip) =>
  createHash("sha256").update(String(ip || "unknown")).digest("hex").slice(0, 16);

// A day's counters are kept for three days and then expire, so the store
// holds nothing older than the cap it enforces. The in-flight count expires
// ten minutes after it was last touched: a function killed mid-turn (the
// host's ceiling, a crash) never decrements it, and the expiry is what keeps
// that from locking the seat for good.
const KEEP_SECONDS = 3 * 86400;
const INFLIGHT_SECONDS = 600;

const keys = (day) => ({
  spent: `workbench-budget:${day}:spent`,
  calls: `workbench-budget:${day}:calls`,
  ip: `workbench-budget:${day}:ip`,
  inflight: "workbench-budget:inflight",
});

// --- the two stores ---------------------------------------------------------
//
// Six operations, each atomic in Redis; the memory store is one process, so
// its Map is atomic by construction.

const memory = new Map();

const memoryStore = {
  kind: "memory",
  incrbyfloat: async (k, d) => { const v = (memory.get(k) || 0) + d; memory.set(k, v); return v; },
  incr: async (k, d) => { const v = (memory.get(k) || 0) + d; memory.set(k, v); return v; },
  hincrby: async (k, f, d) => {
    const h = memory.get(k) || {}; h[f] = (h[f] || 0) + d; memory.set(k, h); return h[f];
  },
  get: async (k) => memory.get(k) ?? null,
  hget: async (k, f) => (memory.get(k) || {})[f] ?? null,
  expire: async () => {},
};

async function store() {
  // The marketplace integration names the two variables KV_REST_API_*; the
  // same database provisioned by hand names them UPSTASH_REDIS_REST_*. Both
  // are read, and with neither set the counters are process memory.
  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!(url && token)) return memoryStore;
  const { Redis } = await import("@upstash/redis");
  const r = new Redis({ url, token });
  return {
    kind: "upstash-redis",
    incrbyfloat: async (k, d) => Number(await r.incrbyfloat(k, d)),
    incr: async (k, d) => Number(await r.incrby(k, d)),
    hincrby: async (k, f, d) => Number(await r.hincrby(k, f, d)),
    get: async (k) => { const v = await r.get(k); return v === null ? null : Number(v); },
    hget: async (k, f) => { const v = await r.hget(k, f); return v === null ? null : Number(v); },
    expire: async (k, s) => { await r.expire(k, s); },
  };
}

export const limits = () => ({
  cap_usd: Number(process.env.WORKBENCH_DAILY_CAP_USD || 5),
  ip_cap: Number(process.env.WORKBENCH_IP_CAP || 40),
  in_flight_cap: Number(process.env.WORKBENCH_IN_FLIGHT_CAP || 4),
});

async function snapshot(s, day, h) {
  const k = keys(day);
  const { cap_usd, ip_cap, in_flight_cap } = limits();
  const [spent, calls, mine, inflight] = await Promise.all([
    s.get(k.spent), s.get(k.calls), s.hget(k.ip, h), s.get(k.inflight),
  ]);
  return {
    day, spent_usd: Number((spent || 0).toFixed(4)), cap_usd,
    calls_today: calls || 0, ip_calls: mine || 0, ip_cap,
    in_flight: Math.max(0, inflight || 0), in_flight_cap,
  };
}

/** Where today stands, and whether this address may make another call.
 * Read-only: what the probe reports. */
export async function check(ip, now = new Date()) {
  const s = await store();
  const b = await snapshot(s, dayKey(now), hashIp(ip));
  let reason = null;
  if (b.spent_usd >= b.cap_usd) reason = "daily budget spent";
  else if (b.ip_calls >= b.ip_cap) reason = "this address has used its share for today";
  else if (b.in_flight >= b.in_flight_cap) reason = "the seat is busy; try again in a moment";
  return { ok: reason === null, reason, store: s.kind, budget: b };
}

/** Take a call's maximum out of the day before it is made. Each counter is
 * incremented and the returned value is the check; an increment that
 * overshoots is rolled back and the call refused, so two calls arriving at
 * once cannot both pass on a read neither of them wrote. */
export async function reserve(ip, usd, now = new Date()) {
  const s = await store();
  const day = dayKey(now);
  const k = keys(day);
  const h = hashIp(ip);
  const { cap_usd, ip_cap, in_flight_cap } = limits();
  const refused = async (reason, undo) => {
    await undo();
    return { ok: false, reason, store: s.kind, budget: await snapshot(s, day, h) };
  };

  const inflight = await s.incr(k.inflight, 1);
  await s.expire(k.inflight, INFLIGHT_SECONDS);
  if (inflight > in_flight_cap) {
    return refused("the seat is busy; try again in a moment", () => s.incr(k.inflight, -1));
  }
  const spent = await s.incrbyfloat(k.spent, usd);
  if (spent > cap_usd) {
    return refused("daily budget spent", async () => {
      await s.incrbyfloat(k.spent, -usd); await s.incr(k.inflight, -1);
    });
  }
  const mine = await s.hincrby(k.ip, h, 1);
  if (mine > ip_cap) {
    return refused("this address has used its share for today", async () => {
      await s.hincrby(k.ip, h, -1); await s.incrbyfloat(k.spent, -usd); await s.incr(k.inflight, -1);
    });
  }
  await s.incr(k.calls, 1);
  await Promise.all([k.spent, k.calls, k.ip].map((key) => s.expire(key, KEEP_SECONDS)));
  return {
    ok: true, reason: null, store: s.kind, budget: await snapshot(s, day, h),
    ticket: { day, ip: h, reserved: usd },
  };
}

/** The call is over: replace what it reserved with what it cost, and let the
 * next one in. A call that failed after the request was sent settles at its
 * reservation, which over-counts and never under-counts. */
export async function settle(ticket, usd) {
  const s = await store();
  const k = keys(ticket.day);
  await s.incrbyfloat(k.spent, usd - ticket.reserved);
  await s.incr(k.inflight, -1);
  return snapshot(s, ticket.day, ticket.ip);
}

/** Nothing was sent: give the whole reservation back. */
export async function release(ticket) {
  const s = await store();
  const k = keys(ticket.day);
  await s.incrbyfloat(k.spent, -ticket.reserved);
  await s.hincrby(k.ip, ticket.ip, -1);
  await s.incr(k.calls, -1);
  await s.incr(k.inflight, -1);
}
