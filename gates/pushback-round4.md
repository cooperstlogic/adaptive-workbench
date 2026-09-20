# Push-back gate: answering the ruling on round 4

| | |
| --- | --- |
| Model | `claude-opus-5` |
| Connectors | `registry` connected, `bioprovider` connected |
| Turns | 33 |
| Wall clock | 486 s |
| Cost | $2.64 |
| Outcome | success |

## The prompt, in full

```
The decision record for round 4 of the project at projects/demo-trastuzumab came back from the scientist ruled more_evidence_requested. Read the record and the ruling, run what was asked for, and propose again with a recommendation they can rule on.

The data/ directory is the simulated laboratory. It holds ground truth the workbench is never allowed to see, so do not read it.
```

## What it did

I'll start by loading the adaptive-optimization skill and looking at the project state.

```
Skill  {
 "skill": "adaptive-optimization"
}
```

```console
$ ls -la /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/adaptive-gate-round4-pushback/ && echo "---" && ls -R /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/adaptive-gate-round4-pushback/projects/demo-trastuzumab 2>/dev/null | head -50
```

```
Read  /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/adaptive-gate-round4-pushback/projects/demo-trastuzumab/decisions/decision_004.json
```

```
Read  /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/adaptive-gate-round4-pushback/projects/demo-trastuzumab/objectives.json
```

```console
$ /Users/dylanwebster/GitHub/adaptive-workbench/.venv/bin/python -c "
import json
d=json.load(open('projects/demo-trastuzumab/decisions/decision_004.json'))
print('top-level keys:', sorted(d.keys()))
print()
print('RECOMMENDATION:'); print(json.dumps(d.get('recommendation'), indent=2))
print()
print('RULING:'); print(json.dumps(d.get('ruling'), indent=2))
print()
print('n_passes', d.get('n_passes'))
for p in d['passes']:
    print('pass at', p.get('at'), 'answering', p.get('answering'), 'keys', sorted(p.keys()))
"
```

```console
$ .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --help 2>&1 | head -40 && echo "=== RECORD ===" && .venv/bin/python skills/adaptive-optimization/scripts/record_decision.py --help 2>&1 | head -60
```

```console
$ .venv/bin/python -c "
import json
s=json.load(open('projects/demo-trastuzumab/evidence/snapshot_004.json'))
print(sorted(s.keys()))
print(json.dumps(s['frame'],indent=2))
print(json.dumps(s['anomaly'],indent=2))
m=s['measurements'][0]
print(json.dumps(m,indent=2))
"
```

Now the requested test — `residual_by_plate` restricted to the fresh designs:

```console
$ .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --project projects/demo-trastuzumab --round 4 --test residual_by_plate --scope fresh
```

```console
$ .venv/bin/python -c "
import json,collections
P='projects/demo-trastuzumab'
s=json.load(open(f'{P}/evidence/snapshot_004.json'))
rows=[(m['design_id'],m.get('bridge'),m.get('fresh'),m.get('slot'),tuple(m.get('plates') or []),m.get('status')) for m in s['measurements']]
print('total measurements', len(rows))
print('bridge/carried-over designs:')
for r in rows:
    if r[1] or not r[2]:
        print('  ',r)
print()
print('plate counts by fresh:')
c=collections.Counter((r[2],r[4]) for r in rows)
for k,v in sorted(c.items(),key=str): print('  ',k,v)
"
```

The requested test is in. Let me check how a second pass is recorded, and run two
supporting cuts.

```console
$ .venv/bin/python - <<'EOF'
import re
src = open('skills/adaptive-optimization/scripts/record_decision.py').read()
print(len(src))
# print the parts about answering / second pass / payload validation
for m in re.finditer(r'answering|requested|second pass|if_wrong|ad_hoc|def \w+', src):
    pass
print(src[:200])
EOF
grep -n "answering\|requested\|if_wrong\|def \|scope\|payload\[" skills/adaptive-optimization/scripts/record_decision.py 2>/dev/null | head -80
```

```
Read  /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/adaptive-gate-round4-pushback/skills/adaptive-optimization/scripts/record_decision.py
```

```console
$ head -3 lims_store/exports/demo-trastuzumab_round4.csv 2>/dev/null; ls lims_store/exports/ 2>/dev/null; echo "--- batch keys ---" && .venv/bin/python -c "
import json
b=json.load(open('projects/demo-trastuzumab/batches/batch_004.json'))
print(sorted(b.keys()))
print(json.dumps(b['selected'][0] if 'selected' in b else b.get('recommended',[{}])[0],indent=2)[:800])
"
```

```
Glob  lims_store/exports/*
```

```console
$ .venv/bin/python -c "
import json
b=json.load(open('projects/demo-trastuzumab/batches/batch_004.json'))
print(sorted(b.keys()))
k='approved' if 'approved' in b else list(b)[0]
for key in b:
    v=b[key]
    if isinstance(v,list) and v and isinstance(v[0],dict):
        print('list field:',key,len(v)); print(json.dumps(v[0],indent=2)[:600]); break
"
```

```console
$ find lims_store -maxdepth 3 | sed -n '1,40p'
```

```
Glob  lims_store/**
```

```console
$ ls -R lims_store
```

```
ToolSearch  {
 "query": "select:mcp__registry__pull_assay_results,mcp__registry__check_run_status",
 "max_results": 2
}
```

```
mcp__registry__check_run_status  {
 "project": "projects/demo-trastuzumab",
 "round_id": "4"
}
```

```console
$ .venv/bin/python -c "
import json,collections
b=json.load(open('projects/demo-trastuzumab/batches/batch_004.json'))
for k in ('composition','policy','slots'):
    if k!='slots': print(k, json.dumps(b[k],indent=2)[:900])
s=b['slots']
print('n slots',len(s))
c=collections.Counter((x['plate_planned'],x['slot']) for x in s)
print(dict(c))
" ; grep -rn "plate" skills/adaptive-optimization/scripts/select_batch.py | head -20
```

```console
$ grep -n "def assign_plates" -A 30 core/acquisition.py
```

```console
$ .venv/bin/python -c "
import json
e=json.load(open('projects/demo-trastuzumab/batches/batch_004.eval.json'))
print(sorted(e.keys()))
print(json.dumps(e['per_design'][0],indent=2))
print('n per_design',len(e['per_design']))
"
```

```
Write  /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/adaptive-gate-round4-pushback/adhoc_a.py
```

```
Write  /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/adaptive-gate-round4-pushback/adhoc_b.py
```

```console
$ .venv/bin/python - <<'PYEOF'
# The ruling's question, made quantitative. All three bridge members and the
# incumbent sit on R4P1, so if the -1.014 were a property of that plate rather
# than of the run, the fresh designs on R4P2 -- which carry no cross-version
# anchor at all -- would sit about 1.01 pKD ABOVE the fresh designs on R4P1.
# residual_by_plate --scope fresh gives the gap; this asks what that gap rules
# out, and how large an R4P1-local component it still permits.
import json

import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
meas = {m["design_id"]: m for m in snap["measurements"]}
BR = snap["frame"]["offset_estimate"]["offset"]

print("designs measured on v1.2 and again in this round, by plate:")
for m in snap["measurements"]:
    if not m["fresh"] and m["status"] == "ok":
        print("  %s  %s  bridge=%-5s slot=%s" % (m["design_id"], m["plates"][0], m["bridge"], m["slot"]))
print("-> all four sit on R4P1. R4P2 carries no cross-version anchor, so the")
print("   offset cannot be measured on R4P2 directly -- only inferred from the")
print("   fresh designs, which is what the requested test does.")

g = {}
for p in ev["per_design"]:
    m = meas[p["design_id"]]
    if m["fresh"]:
        g.setdefault(m["plates"][0], []).append(p["residual"])
a, b = np.array(g["R4P1"]), np.array(g["R4P2"])
gap = a.mean() - b.mean()
se = float(np.sqrt(a.var(ddof=1) / a.size + b.var(ddof=1) / b.size))
print("\nfresh designs only (reproduces residual_by_plate --scope fresh):")
print("  R4P1 n=%2d mean %+.3f   R4P2 n=%2d mean %+.3f" % (a.size, a.mean(), b.size, b.mean()))
print("  observed gap P1-P2 %+.3f, se %.3f" % (gap, se))
print("\nthe two readings, as predictions about that gap:")
print("  'the shift is the run'                    -> gap  0.000 : observed is %.1f se away" % (abs(gap - 0.0) / se))
print("  'the shift is the plate the bridge is on' -> gap %+.3f : observed is %.1f se away"
      % (BR, abs(gap - BR) / se))
print("\nan R4P1-local component A of the bridge estimate is bounded by the gap:")
print("  A = %+.3f +/- %.3f (1 se); |A| < %.3f at 2 se, against a bridge estimate of %+.3f"
      % (gap, se, abs(gap) + 2 * se, BR))
print("  so at most %.0f%% of the correction could be plate rather than run, and the"
      % (100 * (abs(gap) + 2 * se) / abs(BR)))
print("  point estimate says %.0f%%." % (100 * abs(gap) / abs(BR)))
print("\nnote: the snapshot records plate, not well. A within-plate position")
print("effect is not testable from the project directory.")
PYEOF
```

```console
$ .venv/bin/python - <<'PYEOF'
# Equal residuals on two plates only mean equal displacement if the two plates
# hold the same kind of design. core/acquisition.py assign_plates lays a batch
# out in slot order, 24 per plate, so R4P1 took the controls, the replicates,
# the two exploration slots and the first 18 picks while R4P2 took the last 24
# picks. If picks are ordered by acquisition score the plates differ in what
# the model expected of them. Are they comparable, and does the null gap
# survive restricting to like for like?
import collections
import json

import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
batch = json.load(open(f"{P}/batches/batch_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
des = {d["design_id"]: d for d in json.load(open(f"{P}/designs.json"))["designs"]}
meas = {m["design_id"]: m for m in snap["measurements"]}
slots = {s["design_id"]: s for s in batch["slots"]}

rows = [(meas[p["design_id"]]["plates"][0], p) for p in ev["per_design"] if meas[p["design_id"]]["fresh"]]

print("fresh designs, what each plate is made of")
for pl in ("R4P1", "R4P2"):
    rs = [r for r in rows if r[0] == pl]
    pred = np.array([p["pred_mean"] for _, p in rs])
    print("  %-6s n=%2d  G102L %2d  pred %.2f-%.2f (mean %.2f)  pred_sd %.3f  extrap %d  %s"
          % (pl, len(rs), sum("G102L" in des[p["design_id"]]["mutations"] for _, p in rs),
             pred.min(), pred.max(), pred.mean(),
             np.mean([p["pred_sd"] for _, p in rs]),
             sum(p["extrapolation"] for _, p in rs),
             dict(collections.Counter(slots[p["design_id"]]["slot"] for _, p in rs))))

print("\npartner positions (the non-G102L mutation), by plate")
for pl in ("R4P1", "R4P2"):
    c = collections.Counter(m[1:-1] for q, p in rows if q == pl
                            for m in des[p["design_id"]]["mutations"] if m != "G102L")
    print("  %-6s %s" % (pl, dict(sorted(c.items()))))


def gap(rs, label):
    a = np.array([p["residual"] for pl, p in rs if pl == "R4P1"])
    b = np.array([p["residual"] for pl, p in rs if pl == "R4P2"])
    se = float(np.sqrt(a.var(ddof=1) / a.size + b.var(ddof=1) / b.size))
    d = a.mean() - b.mean()
    print("  %-38s P1 n=%2d %+.3f | P2 n=%2d %+.3f | gap %+.3f se %.3f (%.1f se from zero)"
          % (label, a.size, a.mean(), b.size, b.mean(), d, se, abs(d) / se))


print("\nthe gap under restrictions that remove the ways the plates differ")
gap(rows, "all fresh")
gap([r for r in rows if slots[r[1]["design_id"]]["slot"] == "pick"], "pick slots only")
gap([r for r in rows if "G102L" in des[r[1]["design_id"]]["mutations"]], "G102L doubles only")
lo = max(min(p["pred_mean"] for pl, p in rows if pl == "R4P1"),
         min(p["pred_mean"] for pl, p in rows if pl == "R4P2"))
hi = min(max(p["pred_mean"] for pl, p in rows if pl == "R4P1"),
         max(p["pred_mean"] for pl, p in rows if pl == "R4P2"))
gap([r for r in rows if lo <= r[1]["pred_mean"] <= hi], "overlapping predicted range %.2f-%.2f" % (lo, hi))
PYEOF
```

```console
$ grep -n "^READINGS\|^ACTIONS\|^CONFIDENCE\|^VERDICTS" -A 4 skills/adaptive-optimization/scripts/record_decision.py
```

```console
$ .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --project projects/demo-trastuzumab --round 4 --test calibration_by_region --scope fresh 2>/dev/null | .venv/bin/python -c "import json,sys; r=json.load(sys.stdin)['result']; print({k:r[k] for k in ('coverage','mean_residual','n','nominal_coverage')})"
```

```
Write  /tmp/build_pass2.py
```

```console
$ .venv/bin/python /tmp/build_pass2.py && .venv/bin/python skills/adaptive-optimization/scripts/record_decision.py --project projects/demo-trastuzumab --round 4 --propose /tmp/pass2.json
```

```console
$ .venv/bin/python -c "
import json
d=json.load(open('projects/demo-trastuzumab/decisions/decision_004.json'))
p=d['passes'][-1]
print('pass',p['pass'],'answering',p['answering'],'at',p['at'])
h=p['hypotheses'][0]
print(h['id'],h['diagnostic'],h['args'])
print(json.dumps({k:h['result'][k] for k in ('by_plate','max_gap','se_of_gap','z_of_gap','n','scope','overall')},indent=2))
print('status',d['status'],'n_passes',d['n_passes'])
print('rounds.json link:')
r=json.load(open('projects/demo-trastuzumab/rounds.json'))
print(json.dumps([x for x in r.get('rounds',r) if str(x.get('round'))=='4'],indent=2)[:700])
"
```

Round 4, pass 2 is recorded and open for your ruling. Here's what came back.

## The test you asked for

`residual_by_plate --scope fresh` — the carried-over designs out, so the plate comparison
contains no bridge member and no incumbent:

| plate | n fresh | mean residual |
| --- | --- | --- |
| R4P1 | 19 | −2.089 pKD |
| R4P2 | 23 | −2.011 pKD |

Gap **0.079 pKD, se 0.218, z = 0.36**.

Your premise was right and slightly understated: it isn't only the three bridge members on
R4P1 — the incumbent is too, so R4P2 carries **no** cross-version design of any kind. That
makes it the clean test. If the −1.014 were carried by the plate the bridge sits on,
R4P2's fresh designs should sit ~1.01 pKD *above* R4P1's. They sit 0.08 below — 4.3 se
from the plate reading, 0.4 se from the run reading. Both halves of the round are
displaced equally, and one half never saw a bridge well.

I also checked the plates are comparable, since `assign_plates` fills in slot order rather
than at random (R4P1 got the controls, replicates, both exploration slots and 17 picks;
R4P2 got 23 picks). Restricted to pick slots only the gap is 0.166 (0.8 se); to G102L
doubles only, 0.166; to the overlapping predicted range 10.29–10.90, 0.095 (0.5 se).
Nothing moves it near 1.01.

**The condition you named — "if it is not, say so and do not correct" — did not obtain.** Recommendation unchanged: `apply_offset_correction` by the recorded −1.014, confidence high.

## What it does not settle

The gap resolves 0.218 pKD per se, so a *smaller* plate-1 component isn't excluded: up to
0.51 pKD — half the correction — survives at 2 se, point estimate 0.08 pKD, below the
round's read noise of 0.171. If one exists, a uniform correction over-corrects R4P2 by
that much. I considered correcting per plate and rejected it: a 0.4-se gap is read noise,
and the shift applied has to be the recorded bridge estimate, not one assembled while
reading the round. Within-plate position is untestable from here — the snapshot records
plate, not well.

## One finding worth your attention beyond round 4

The bridge sitting entirely on one plate is structural, not bad luck. `core/acquisition.py
assign_plates` lays a batch out in slot order at 24 per plate and controls/replicates are
the first slots, so **every round of this template puts its whole bridging set on plate
1**, and every future offset estimate has exactly the blind spot you pointed at. Round 4
could answer it only because both plates happened to hold the same kind of design.
Splitting the bridge across plates from round 5 fixes it by construction — that's a
template change, so it's flagged for you rather than made.

The second half of the diagnosis is unchanged: after correcting, the 42 fresh designs are
still −1.032 pKD low at coverage 0.524, which is the additive recipe over-crediting G102L
from one observation. Round 4 advanced nothing — best corrected fresh design 11.245 vs
incumbent 11.837.

All numbers synthetic — generated landscape, mock LIMS, oracle assay with noise. Nothing
has moved: pass 2 is open and no data changes without your ruling.

```
# accept
.venv/bin/python skills/adaptive-optimization/scripts/record_decision.py \
  --project projects/demo-trastuzumab --round 4 --rule accepted --by d.webster \
  --note "plate test clears the bridge; correct and refit"
```

On `accepted` I'll re-import with `--offset always --authority decision_004`, re-run
`evaluate_prior`, then fit round 4 and select round 5 — and I'd propose putting bridge
members on both plates in that batch if you want the layout change made.

## What it reported back

Round 4, pass 2 is recorded and open for your ruling. Here's what came back.

## The test you asked for

`residual_by_plate --scope fresh` — the carried-over designs out, so the plate comparison contains no bridge member and no incumbent:

| plate | n fresh | mean residual |
| --- | --- | --- |
| R4P1 | 19 | −2.089 pKD |
| R4P2 | 23 | −2.011 pKD |

Gap **0.079 pKD, se 0.218, z = 0.36**.

Your premise was right and slightly understated: it isn't only the three bridge members on R4P1 — the incumbent is too, so R4P2 carries **no** cross-version design of any kind. That makes it the clean test. If the −1.014 were carried by the plate the bridge sits on, R4P2's fresh designs should sit ~1.01 pKD *above* R4P1's. They sit 0.08 below — 4.3 se from the plate reading, 0.4 se from the run reading. Both halves of the round are displaced equally, and one half never saw a bridge well.

I also checked the plates are comparable, since `assign_plates` fills in slot order rather than at random (R4P1 got the controls, replicates, both exploration slots and 17 picks; R4P2 got 23 picks). Restricted to pick slots only the gap is 0.166 (0.8 se); to G102L doubles only, 0.166; to the overlapping predicted range 10.29–10.90, 0.095 (0.5 se). Nothing moves it near 1.01.

**The condition you named — "if it is not, say so and do not correct" — did not obtain.** Recommendation unchanged: `apply_offset_correction` by the recorded −1.014, confidence high.

## What it does not settle

The gap resolves 0.218 pKD per se, so a *smaller* plate-1 component isn't excluded: up to 0.51 pKD — half the correction — survives at 2 se, point estimate 0.08 pKD, below the round's read noise of 0.171. If one exists, a uniform correction over-corrects R4P2 by that much. I considered correcting per plate and rejected it: a 0.4-se gap is read noise, and the shift applied has to be the recorded bridge estimate, not one assembled while reading the round. Within-plate position is untestable from here — the snapshot records plate, not well.

## One finding worth your attention beyond round 4

The bridge sitting entirely on one plate is structural, not bad luck. `core/acquisition.py assign_plates` lays a batch out in slot order at 24 per plate and controls/replicates are the first slots, so **every round of this template puts its whole bridging set on plate 1**, and every future offset estimate has exactly the blind spot you pointed at. Round 4 could answer it only because both plates happened to hold the same kind of design. Splitting the bridge across plates from round 5 fixes it by construction — that's a template change, so it's flagged for you rather than made.

The second half of the diagnosis is unchanged: after correcting, the 42 fresh designs are still −1.032 pKD low at coverage 0.524, which is the additive recipe over-crediting G102L from one observation. Round 4 advanced nothing — best corrected fresh design 11.245 vs incumbent 11.837.

All numbers synthetic — generated landscape, mock LIMS, oracle assay with noise. Nothing has moved: pass 2 is open and no data changes without your ruling.

```
# accept
.venv/bin/python skills/adaptive-optimization/scripts/record_decision.py \
  --project projects/demo-trastuzumab --round 4 --rule accepted --by d.webster \
  --note "plate test clears the bridge; correct and refit"
```

On `accepted` I'll re-import with `--offset always --authority decision_004`, re-run `evaluate_prior`, then fit round 4 and select round 5 — and I'd propose putting bridge members on both plates in that batch if you want the layout change made.
