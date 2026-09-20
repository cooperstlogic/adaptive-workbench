// The daily spend cap and the per-address counter.
//
// SPEC.md: a global daily spend cap and a per-IP counter live in Netlify Blobs.
// Under the cap the session runs live; over it the site returns to replay,
// which is the default that live calls temporarily upgrade. Nothing here is
// precise to the cent -- two requests can race past the cap by one call --
// and it does not need to be: the cap exists so a public URL cannot run up a
// bill, not to meter anyone.
//
// Off Netlify (the Vite dev server, check.py's harness) there is no blob
// store, so the counter lives in memory and resets with the process. That is
// the honest local behaviour and it is labelled in the probe as `store`.

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

export const dayKey = (now = new Date()) => now.toISOString().slice(0, 10);

export const hashIp = (ip) =>
  createHash("sha256").update(String(ip || "unknown")).digest("hex").slice(0, 16);

const memory = new Map();

async function store() {
  // Netlify Blobs needs the site context the platform injects; anywhere else
  // getStore throws before it is used, and the counter is process memory.
  if (process.env.NETLIFY || process.env.NETLIFY_BLOBS_CONTEXT) {
    try {
      const { getStore } = await import("@netlify/blobs");
      const blobs = getStore({ name: "workbench-budget", consistency: "strong" });
      return {
        kind: "netlify-blobs",
        get: async (key) => (await blobs.get(key, { type: "json" })) || null,
        set: async (key, value) => blobs.setJSON(key, value),
      };
    } catch {
      /* fall through to memory */
    }
  }
  return {
    kind: "memory",
    get: async (key) => memory.get(key) || null,
    set: async (key, value) => { memory.set(key, value); },
  };
}

const empty = () => ({ spent_usd: 0, calls: 0, by_ip: {} });

export const limits = () => ({
  cap_usd: Number(process.env.WORKBENCH_DAILY_CAP_USD || 5),
  ip_cap: Number(process.env.WORKBENCH_IP_CAP || 40),
});

/** Where today stands, and whether this address may make another call. */
export async function check(ip, now = new Date()) {
  const s = await store();
  const day = (await s.get(dayKey(now))) || empty();
  const { cap_usd, ip_cap } = limits();
  const mine = day.by_ip[hashIp(ip)] || 0;
  let reason = null;
  if (day.spent_usd >= cap_usd) reason = "daily budget spent";
  else if (mine >= ip_cap) reason = "this address has used its share for today";
  return {
    ok: reason === null,
    reason,
    store: s.kind,
    budget: {
      day: dayKey(now), spent_usd: Number(day.spent_usd.toFixed(4)), cap_usd,
      calls_today: day.calls, ip_calls: mine, ip_cap,
    },
  };
}

/** Record one completed call. */
export async function account(ip, usd, now = new Date()) {
  const s = await store();
  const key = dayKey(now);
  const day = (await s.get(key)) || empty();
  day.spent_usd += usd;
  day.calls += 1;
  const h = hashIp(ip);
  day.by_ip[h] = (day.by_ip[h] || 0) + 1;
  await s.set(key, day);
  const { cap_usd, ip_cap } = limits();
  return {
    day: key, spent_usd: Number(day.spent_usd.toFixed(4)), cap_usd,
    calls_today: day.calls, ip_calls: day.by_ip[h], ip_cap,
  };
}
