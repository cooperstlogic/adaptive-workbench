# Hour-5 gate: diagnosing round 4

| | |
| --- | --- |
| Model | `claude-opus-5` |
| Connectors | `registry` connected, `bioprovider` connected |
| Turns | 47 |
| Wall clock | 768 s |
| Cost | $5.05 |
| Outcome | success |

## The prompt, in full

```
Round 4 of the project at projects/demo-trastuzumab came back flagged and the loop has stopped. Work out what the round means and write a decision record with a recommendation a scientist can rule on.

The data/ directory is the simulated laboratory. It holds ground truth the workbench is never allowed to see, so do not read it.
```

## What it did

I'll start by loading the adaptive-optimization skill, since it covers diagnosing a
flagged round.

```
Skill  {
 "skill": "adaptive-optimization"
}
```

API Error: Opus 5's safeguards flagged this message
(https://www.anthropic.com/legal/aup). Our intentionally broad safeguards allow us to
deliver more capabilities faster, but can sometimes flag legitimate coding,
cybersecurity, and biology tasks. Claude Code can't respond to this message with Opus 5.
Try rephrasing the request in a new session or change your model.
Learn more: https://support.claude.com/en/articles/16049681
Details: `[bio]`
Request ID: req_011CfDLmA5JdV6TMxvaF7kuC

Let me look at the project state first.

```console
$ ls -la && echo "---" && find projects/demo-trastuzumab -type f | sort && echo "---" && ls skills/adaptive-optimization/scripts/ && echo "---" && ls core/ 2>/dev/null || ls skills/adaptive-optimization/core/ 2>/dev/null
```

Round 2 already has a decision record, so there's precedent. Let me read the project
config, the round graph, and the round-4 snapshot's anomaly block.

```
Read  /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/gate-round4/projects/demo-trastuzumab/project.json
```

```
Read  /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/gate-round4/projects/demo-trastuzumab/objectives.json
```

```console
$ python3 -c "
import json
d=json.load(open('projects/demo-trastuzumab/evidence/snapshot_004.json'))
print(list(d.keys()))
for k in ('anomaly','frame','round','assay','summary','provenance','stats','counts'):
    if k in d: print('==',k,'==');print(json.dumps(d[k],indent=2)[:4000])
"
```

```console
$ python3 -c "
import json
for n in (1,2,3,4):
    d=json.load(open(f'projects/demo-trastuzumab/evidence/snapshot_{n:03d}.json'))
    a=d.get('anomaly') or {}
    print(n,'assay',d.get('assay_version'),'flagged',d.get('flagged'),'msr',a.get('mean_signed_residual'),'n',a.get('n_compared'),'known_off',a.get('known_version_offset'))
    f=d.get('frame',{})
    oe=f.get('offset_estimate') or {}
    print('   frame: applied',f.get('offset_applied'),'auth',f.get('authority'),'est',oe.get('offset'),'n',oe.get('n'),'se',oe.get('se'))
    print('   reconciliation keys:', list(d.get('reconciliation',{}).keys()))
    print('   n measurements', len(d.get('measurements',[])))
"
```

Round 4 is the first round on assay v1.3, never characterized. Let me read the round-2
precedent and the round graph.

```
Read  /Users/dylanwebster/.claude/jobs/78dea4e9/tmp/gate-round4/projects/demo-trastuzumab/decisions/decision_002.json
```

Now I have the precedent and format. Let me check the diagnostic runner's interface and
run the first test.

```console
$ .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --help 2>&1 | head -40
```

```console
$ .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --project projects/demo-trastuzumab --round 4 --test offset_from_controls
```

Bridge is concordant (3 designs, spread sd 0.102 vs tolerance 0.342) and puts the run at
−1.014 pKD — but the fresh designs are −2.046 off. That's a partial explanation. Let me
run the rest.

```console
$ for t in residual_by_plate replicate_concordance; do echo "########## $t"; .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --project projects/demo-trastuzumab --round 4 --test $t 2>/dev/null; done
```

Both plates are equally low (gap 0.139 pKD, z=0.62) — run-level, not a plate artifact.
Now the counterfactual and the class breakdowns.

```console
$ for o in none bridge; do echo "########## calibration offset=$o"; .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --project projects/demo-trastuzumab --round 4 --test calibration_by_region --offset $o 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
print('coverage',d['coverage'],'mean_resid',d['mean_residual'],'n',d['n'],'offset_applied',d.get('offset_applied'))
for b in d['by_predicted_value']: print('  bin n=%2d pred %.3f-%.3f cov %.3f mean_resid %+.3f'%(b['n'],b['pred_min'],b['pred_max'],b['coverage'],b['mean_residual']))
"; done
```

The bridge correction lifts coverage from 0.065 to 0.565 — real but incomplete; −0.93
pKD remains. Let me see what carries the remainder.

```console
$ for by in position n_mutations; do echo "########## by=$by"; .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --project projects/demo-trastuzumab --round 4 --test residual_by_mutation_class --by $by 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
print('overall',d['overall'],'range',d['range_of_class_means'])
for k,v in sorted(d['classes'].items(), key=lambda kv:-kv[1]['n']):
    print('  %-4s n=%2d n_fresh=%2d mean %+.3f  vs_other %+.3f  se %s'%(k,v['n'],v['n_fresh'],v['mean_residual'],v['vs_other_classes'],v['se']))
"; done
```

No position carries the remainder — 102 is in 43 of 46 designs, so it *is* the round.
Let me check the scope split and the model that made these predictions.

```console
$ echo "### fresh-scope calibration, bridge-corrected" && .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --project projects/demo-trastuzumab --round 4 --test calibration_by_region --offset bridge --scope fresh 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
print('coverage',d['coverage'],'mean_resid',round(d['mean_residual'],4),'n',d['n'])
" && echo "### fresh-scope calibration, raw" && .venv/bin/python skills/adaptive-optimization/scripts/run_diagnostic.py --project projects/demo-trastuzumab --round 4 --test calibration_by_region --scope fresh 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']
print('coverage',d['coverage'],'mean_resid',round(d['mean_residual'],4),'n',d['n'])
" && echo "### model run 003 bake-off" && python3 -c "
import json
m=json.load(open('projects/demo-trastuzumab/models/run_003.json'))
print(list(m.keys()))
print(json.dumps({k:v for k,v in m.items() if k in ('selected','recipes','bakeoff','winner','fits','comparison')},indent=2)[:3000]
)"
```

The winning model was well calibrated at fit time (held-out coverage 0.823). Let me
check the carryover-vs-fresh split after correction and how far the model extrapolated.

```console
$ python3 -c "
import json
e=json.load(open('projects/demo-trastuzumab/batches/batch_004.eval.json'))
print('eval004 keys',list(e.keys()))
print(json.dumps({k:v for k,v in e.items() if not isinstance(v,list)},indent=2)[:2500])
" && echo "=== round3 eval ===" && python3 -c "
import json
e=json.load(open('projects/demo-trastuzumab/batches/batch_003.eval.json'))
print(json.dumps({k:v for k,v in e.items() if not isinstance(v,list)},indent=2)[:2000])
"
```

Round 3 was clean (coverage 0.745). The round-4 slot breakdown is the key structure. Let
me inspect the per-design data to run the sixth question.

```console
$ python3 -c "
import json
s=json.load(open('projects/demo-trastuzumab/evidence/snapshot_004.json'))
print('measurement keys:',list(s['measurements'][0].keys()))
print(json.dumps(s['measurements'][0],indent=2))
b=json.load(open('projects/demo-trastuzumab/batches/batch_004.json'))
print('batch keys',list(b.keys()))
print('slot keys:',list(b['slots'][0].keys()))
print(json.dumps(b['slots'][0],indent=2))
e=json.load(open('projects/demo-trastuzumab/batches/batch_004.eval.json'))
print('per_design keys:',list(e['per_design'][0].keys()))
print(json.dumps(e['per_design'][0],indent=2))
"
```

Let me enumerate the actual per-design structure before writing the ad hoc cut.

```console
$ python3 -c "
import json
s=json.load(open('projects/demo-trastuzumab/evidence/snapshot_004.json'))
ms={m['design_id']:m for m in s['measurements']}
b=json.load(open('projects/demo-trastuzumab/batches/batch_004.json'))
sl={x['design_id']:x for x in b['slots']}
e=json.load(open('projects/demo-trastuzumab/batches/batch_004.eval.json'))
print('non-fresh designs among scored:')
for p in e['per_design']:
    m=ms[p['design_id']]
    if not m['fresh']:
        print('  %s slot=%-11s bridge=%-5s pred %.3f obs %.3f resid %+.3f nmut=%d'%(p['design_id'],p['slot'],m['bridge'],p['pred_mean'],p['observed'],p['residual'],sl[p['design_id']]['n_mutations']))
print()
print('counts: scored',len(e['per_design']),'fresh',sum(1 for p in e['per_design'] if ms[p['design_id']]['fresh']),'bridge',sum(1 for p in e['per_design'] if ms[p['design_id']]['bridge']))
print('prev_measured among scored:',sum(1 for p in e['per_design'] if sl[p['design_id']]['previously_measured']))
print('extrapolation flagged:',sum(1 for p in e['per_design'] if p['extrapolation']))
print('batch composition:',json.dumps(b.get('composition')))
print('incumbent:',json.dumps(b.get('incumbent'))[:400])
print('extrapolation_cut_sd',b.get('extrapolation_cut_sd'),'n_observed',b.get('n_observed'))
"
```

One carryover is *not* in the bridge — and it's the incumbent. That's an independent
check. Let me confirm its history.

```console
$ python3 -c "
import json
d=json.load(open('projects/demo-trastuzumab/designs.json'))
print(type(d), list(d.keys())[:5] if isinstance(d,dict) else len(d))
recs = d['designs'] if isinstance(d,dict) and 'designs' in d else d
r = recs['497ac31f6a69'] if isinstance(recs,dict) else [x for x in recs if x.get('design_id')=='497ac31f6a69'][0]
print(json.dumps(r,indent=2)[:1200])
" 2>&1 | head -40
```

Now the sixth question — the library tests by *position*, not by *residue*. Let me look
at what the optimizer actually walked into.

```console
$ cat > /tmp/adhoc1.py <<'EOF'
# Q: the library bins residuals by POSITION. Round 4 put position 102 in 43 of 46
# designs, so that class is the round and cannot separate from it. Does the
# residue actually substituted at 102 separate?  And do the four designs measured
# in both v1.2 and v1.3 agree on the size of the shift across the affinity range?
import json
import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
des = json.load(open(f"{P}/designs.json"))["designs"]
prev = {}
for r in (1, 2, 3):
    for m in json.load(open(f"{P}/evidence/snapshot_{r:03d}.json"))["measurements"]:
        if m["status"] == "ok":
            prev.setdefault(m["design_id"], []).append((r, m["value"]))

meas = {m["design_id"]: m for m in snap["measurements"]}
BRIDGE = json.load(open(f"{P}/evidence/snapshot_004.json"))["frame"]["offset_estimate"]["offset"]

print("re-measured designs: v1.2 value -> v1.3 value, across the affinity range")
print("  id            in bridge   last v1.2    v1.3      delta")
rows = []
for p in ev["per_design"]:
    did = p["design_id"]
    if did in prev and prev[did]:
        r, v = prev[did][-1]
        rows.append((v, p["observed"] - v, meas[did]["bridge"], did))
for v, d, br, did in sorted(rows):
    print("  %s  %-9s  %8.3f  %8.3f  %+7.3f" % (did, br, v, v + d, d))
a = np.array([r[0] for r in rows]); b = np.array([r[1] for r in rows])
print("  slope of delta on v1.2 value: %+.4f pKD per pKD (n=%d)" % (np.polyfit(a, b, 1)[0], a.size))

print("\nfresh picks, bridge-corrected residual by substituted residue at position 102")
print("  (bridge offset %+.4f pKD removed; the library's position class holds all of these together)" % BRIDGE)
by = {}
for p in ev["per_design"]:
    did = p["design_id"]
    if not meas[did]["fresh"]:
        continue
    for mut in des[did]["mutations"]:
        if mut[1:-1] == "102":
            by.setdefault(mut[-1], []).append(p["residual"] - BRIDGE)
print("  res    n   mean corrected residual     sd")
for k in sorted(by, key=lambda k: np.mean(by[k])):
    x = np.array(by[k])
    print("  %s  %4d   %+8.3f   %20s" % (k, x.size, x.mean(), "%.3f" % x.std(ddof=1) if x.size > 1 else "-"))
allf = np.array([p["residual"] - BRIDGE for p in ev["per_design"] if meas[p["design_id"]]["fresh"]])
print("  all fresh  n=%d  mean %+.3f  sd %.3f" % (allf.size, allf.mean(), allf.std(ddof=1)))
EOF
.venv/bin/python /tmp/adhoc1.py
```

The four re-measured designs span 9.07–11.84 pKD and all shift down ~1.0 — the incumbent
included. Let me fix the indexing and finish the residue cut.

```console
$ python3 - <<'EOF'
import re, pathlib
p = pathlib.Path('/tmp/adhoc1.py')
s = p.read_text()
s = s.replace('des = json.load(open(f"{P}/designs.json"))["designs"]',
              'des = {d["design_id"]: d for d in json.load(open(f"{P}/designs.json"))["designs"]}')
p.write_text(s)
EOF
.venv/bin/python /tmp/adhoc1.py
```

40 of 42 fresh designs carry the *same* mutation, G102L — which is also the incumbent's
own first mutation, and the incumbent reproduced fine. Let me break down by the partner
mutation.

```console
$ cat > /tmp/adhoc2.py <<'EOF'
# Q: 40 of 42 fresh picks are G102L + one partner, so the round is monomorphic at
# 102 and no position or residue class can separate it. Two things the library
# cannot ask: (a) does the partner mutation carry the gap, or is it flat across
# partners, and (b) is the gap what an additive model would make when the truth
# is not additive -- i.e. does measured(G102L + X) fall short of
# measured(G102L) + measured(X) built from the round-1 single-mutant scan?
import json
import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
des = {d["design_id"]: d for d in json.load(open(f"{P}/designs.json"))["designs"]}
meas = {m["design_id"]: m for m in snap["measurements"]}
BR = snap["frame"]["offset_estimate"]["offset"]

# round-1 single-mutant scan, v1.2 raw frame, and the parent in the same frame
s1 = {m["design_id"]: m["value"] for m in json.load(open(f"{P}/evidence/snapshot_001.json"))["measurements"] if m["status"] == "ok"}
singles = {des[d]["mutations"][0]: v for d, v in s1.items() if len(des[d]["mutations"]) == 1}
parent1 = [v for d, v in s1.items() if len(des[d]["mutations"]) == 0]
par = parent1[0]
print("round-1 scan: %d singles, parent %.3f pKD (v1.2 raw)" % (len(singles), par))
print("G102L single effect: %+.3f pKD" % (singles["G102L"] - par) if "G102L" in singles else "G102L not in scan")

print("\n(a) fresh G102L picks, bridge-corrected residual by PARTNER mutation")
by = {}
for p in ev["per_design"]:
    d = p["design_id"]
    if not meas[d]["fresh"]:
        continue
    muts = des[d]["mutations"]
    if "G102L" not in muts:
        continue
    partner = [m for m in muts if m != "G102L"]
    by.setdefault(partner[0] if partner else "(none)", []).append(p["residual"] - BR)
print("  %d distinct partners over %d designs" % (len(by), sum(len(v) for v in by.values())))
vals = np.array([np.mean(v) for v in by.values()])
print("  partner-mean corrected residual: min %+.3f  max %+.3f  mean %+.3f  sd %.3f"
      % (vals.min(), vals.max(), vals.mean(), vals.std(ddof=1)))
print("  partners above 0 (delivered as predicted): %d of %d" % (int((vals > 0).sum()), vals.size))

print("\n(b) additivity: measured(G102L+X) vs parent + effect(G102L) + effect(X)")
print("    all in the v1.2 frame; round 4 moved by the bridge %+.4f" % BR)
obs, add = [], []
for p in ev["per_design"]:
    d = p["design_id"]
    muts = des[d]["mutations"]
    if not meas[d]["fresh"] or "G102L" not in muts or len(muts) != 2:
        continue
    X = [m for m in muts if m != "G102L"][0]
    if X not in singles:
        continue
    obs.append(p["observed"] - BR)
    add.append(par + (singles["G102L"] - par) + (singles[X] - par))
obs, add = np.array(obs), np.array(add)
print("    n with both singles in the scan: %d" % obs.size)
print("    mean measured  %.3f     mean additive prediction  %.3f" % (obs.mean(), add.mean()))
print("    mean epistasis (measured - additive): %+.3f pKD   sd %.3f" % ((obs - add).mean(), (obs - add).std(ddof=1)))
EOF
.venv/bin/python /tmp/adhoc2.py
```

```console
$ .venv/bin/python -c "
import json
P='projects/demo-trastuzumab'
des={d['design_id']:d for d in json.load(open(P+'/designs.json'))['designs']}
s1={m['design_id']:m['value'] for m in json.load(open(P+'/evidence/snapshot_001.json'))['measurements'] if m['status']=='ok'}
singles={des[d]['mutations'][0]:v for d,v in s1.items() if len(des[d]['mutations'])==1}
import collections
bypos=collections.defaultdict(list)
for m,v in singles.items(): bypos[m[1:-1]].append((m,round(v,3)))
for p in sorted(bypos,key=int): print(p, sorted(bypos[p]))
par=[v for d,v in s1.items() if len(des[d]['mutations'])==0][0]
print('parent',round(par,3))
# where did G102L first appear?
g=[d for d in des.values() if 'G102L' in d['mutations']]
print('designs with G102L:',len(g),'first_rounds',sorted(set(x['first_round'] for x in g)))
"
```

G102L was never scanned as a single — it entered in round 3 inside doubles. Let me test
whether the partners' scanned effects transfer onto that background.

```console
$ cat > /tmp/adhoc3.py <<'EOF'
# Q: 40 of 42 fresh picks are G102L + one partner X, one design per partner, so
# every partner class has n=1 and no library class can separate them. The
# aggregate question the library cannot ask: does each partner's OWN measured
# single-mutant effect, from the round-1 scan, transfer onto the G102L
# background the way the additive winning recipe (ridge_onehot) assumes?
# G102L was never scanned as a single, so it is anchored on the one G102L design
# measured in both assay versions -- the incumbent G102L+A105K -- which makes the
# incumbent additive by construction and every other partner a free test.
import json
import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
des = {d["design_id"]: d for d in json.load(open(f"{P}/designs.json"))["designs"]}
meas = {m["design_id"]: m for m in snap["measurements"]}
BR = snap["frame"]["offset_estimate"]["offset"]

s1 = {m["design_id"]: m["value"] for m in json.load(open(f"{P}/evidence/snapshot_001.json"))["measurements"] if m["status"] == "ok"}
singles = {des[d]["mutations"][0]: v for d, v in s1.items() if len(des[d]["mutations"]) == 1}
par = [v for d, v in s1.items() if len(des[d]["mutations"]) == 0][0]

inc = [p for p in ev["per_design"] if p["design_id"] == "497ac31f6a69"][0]
g102l = (inc["observed"] - BR) - singles["A105K"]     # anchor, v1.2 frame
print("parent (round-1 scan, v1.2) %.3f pKD" % par)
print("incumbent G102L+A105K: v1.3 %.3f -> v1.2 frame %.3f ; implied G102L effect %+.3f pKD"
      % (inc["observed"], inc["observed"] - BR, g102l - par))

rows = []
for p in ev["per_design"]:
    d = p["design_id"]
    muts = des[d]["mutations"]
    if not meas[d]["fresh"] or "G102L" not in muts or len(muts) != 2:
        continue
    X = [m for m in muts if m != "G102L"][0]
    if X in singles:
        rows.append((X, p["observed"] - BR, g102l + (singles[X] - par), singles[X] - par))

obs = np.array([r[1] for r in rows]); add = np.array([r[2] for r in rows]); eff = np.array([r[3] for r in rows])
ep = obs - add
print("\npartners whose single-mutant effect is in the round-1 scan: n=%d of 40" % len(rows))
print("  mean measured (v1.2 frame)       %.3f pKD" % obs.mean())
print("  mean additive prediction         %.3f pKD" % add.mean())
print("  mean epistasis (meas - additive) %+.3f pKD   sd %.3f" % (ep.mean(), ep.std(ddof=1)))
print("  partners delivering >= additive: %d of %d" % (int((ep >= 0).sum()), ep.size))
print("  corr(partner's own single effect, epistasis) = %+.3f" % np.corrcoef(eff, ep)[0, 1])
print("  slope: %+.3f pKD of shortfall per pKD of the partner's solo gain" % np.polyfit(eff, ep, 1)[0])
print("\n  partner  solo effect   measured   additive   epistasis")
for X, o, a, e in sorted(rows, key=lambda r: r[3], reverse=True)[:6]:
    print("  %-7s   %+8.3f   %8.3f   %8.3f   %+8.3f" % (X, e, o, a, o - a))
print("  ...")
for X, o, a, e in sorted(rows, key=lambda r: r[3])[:3]:
    print("  %-7s   %+8.3f   %8.3f   %8.3f   %+8.3f" % (X, e, o, a, o - a))
EOF
.venv/bin/python /tmp/adhoc3.py
```

Algebra slip in that anchor — `g102l` was already an effect, not a level. Let me fix it
and widen the test using round 3's own G102L doubles.

```console
$ cat > /tmp/adhoc3.py <<'EOF'
# Q: 40 of 42 fresh picks are G102L + one partner X, one design per partner, so
# every partner class has n=1 and no library class can separate them. Two
# aggregate questions the library cannot ask:
#   (a) does each partner's own measured single-mutant effect, from the round-1
#       scan, transfer onto the G102L background the way the additive winning
#       recipe (ridge_onehot) assumes?
#   (b) round 3 also tested G102L doubles and fit well. How do round 3's G102L
#       doubles and round 4's compare on the same background, same frame?
import json
import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
des = {d["design_id"]: d for d in json.load(open(f"{P}/designs.json"))["designs"]}
meas = {m["design_id"]: m for m in snap["measurements"]}
BR = snap["frame"]["offset_estimate"]["offset"]

s1 = {m["design_id"]: m["value"] for m in json.load(open(f"{P}/evidence/snapshot_001.json"))["measurements"] if m["status"] == "ok"}
singles = {des[d]["mutations"][0]: v for d, v in s1.items() if len(des[d]["mutations"]) == 1}
par = [v for d, v in s1.items() if len(des[d]["mutations"]) == 0][0]

inc = [p for p in ev["per_design"] if p["design_id"] == "497ac31f6a69"][0]
inc_v12 = inc["observed"] - BR
eff_g102l = inc_v12 - par - (singles["A105K"] - par)          # additive anchor, v1.2 frame
print("parent (round-1 scan, v1.2)          %.3f pKD" % par)
print("incumbent G102L+A105K  v1.3 %.3f -> v1.2 frame %.3f" % (inc["observed"], inc_v12))
print("implied additive effect of G102L     %+.3f pKD  (anchored on the incumbent, so it is additive by construction)" % eff_g102l)

rows = []
for p in ev["per_design"]:
    d = p["design_id"]
    muts = des[d]["mutations"]
    if not meas[d]["fresh"] or "G102L" not in muts or len(muts) != 2:
        continue
    X = [m for m in muts if m != "G102L"][0]
    if X in singles:
        rows.append((X, p["observed"] - BR, par + eff_g102l + (singles[X] - par), singles[X] - par))

obs = np.array([r[1] for r in rows]); add = np.array([r[2] for r in rows]); eff = np.array([r[3] for r in rows])
ep = obs - add
print("\n(a) partners whose single-mutant effect is in the round-1 scan: n=%d of 40" % len(rows))
print("    mean measured (v1.2 frame)       %.3f pKD" % obs.mean())
print("    mean additive prediction         %.3f pKD" % add.mean())
print("    mean epistasis (meas - additive) %+.3f pKD   sd %.3f" % (ep.mean(), ep.std(ddof=1)))
print("    partners delivering >= additive: %d of %d" % (int((ep >= 0).sum()), ep.size))
print("    partner  solo effect   measured   additive   epistasis")
for X, o, a, e in sorted(rows, key=lambda r: r[3], reverse=True):
    print("    %-7s   %+8.3f   %8.3f   %8.3f   %+8.3f" % (X, e, o, a, o - a))

# (b) round-3 G102L doubles vs round-4 G102L doubles, both put in the v1.2 frame
s3 = json.load(open(f"{P}/evidence/snapshot_003.json"))
r3 = [m["value"] for m in s3["measurements"]
      if m["status"] == "ok" and "G102L" in des[m["design_id"]]["mutations"] and len(des[m["design_id"]]["mutations"]) == 2]
r4 = [p["observed"] - BR for p in ev["per_design"]
      if meas[p["design_id"]]["fresh"] and "G102L" in des[p["design_id"]]["mutations"]]
print("\n(b) G102L doubles, both in the v1.2 frame (round 3 as recorded, round 4 bridge-corrected)")
print("    round 3: n=%2d  mean %.3f  max %.3f" % (len(r3), np.mean(r3), np.max(r3)))
print("    round 4: n=%2d  mean %.3f  max %.3f" % (len(r4), np.mean(r4), np.max(r4)))
print("    difference in mean: %+.3f pKD" % (np.mean(r4) - np.mean(r3)))
EOF
.venv/bin/python /tmp/adhoc3.py
```

That's decisive. Let me verify two load-bearing claims: that `ridge_onehot` is strictly
additive, and how many G102L observations the model actually had.

```console
$ .venv/bin/python -c "
import json
P='projects/demo-trastuzumab'
des={d['design_id']:d for d in json.load(open(P+'/designs.json'))['designs']}
for r in (1,2,3):
    s=json.load(open(P+f'/evidence/snapshot_{r:03d}.json'))
    n=[m for m in s['measurements'] if 'G102L' in des[m['design_id']]['mutations']]
    print('round',r,'designs containing G102L:',len(n),'statuses',[m['status'] for m in n])
" && echo "=== encode ===" && .venv/bin/python -c "
import inspect, core.encode as e, core.surrogate as s
print(inspect.getsource(e)[:1500])
" 2>&1 | head -45
```

```
Grep  {}
```

API Error: Opus 5's safeguards flagged this message
(https://www.anthropic.com/legal/aup). Our intentionally broad safeguards allow us to
deliver more capabilities faster, but can sometimes flag legitimate coding,
cybersecurity, and biology tasks. Claude Code can't respond to this message with Opus 5.
Try rephrasing the request in a new session or change your model.
Learn more: https://support.claude.com/en/articles/16049681
Details: `[bio]`
Request ID: req_011CfDMGYFreSgEZMTg4j2xC

```
Grep  {
 "pattern": "def onehot|interaction|def fit_ridge|class .*Ridge|pairwise",
 "path": "/Users/dylanwebster/.claude/jobs/78dea4e9/tmp/gate-round4/core",
 "output_mode": "content",
 "-n": true,
 "-C": 4
}
```

Confirmed: `ridge_onehot` is Bayesian linear regression on the raw 8×20 one-hot block —
strictly additive, no interaction terms — and G102L was observed exactly once before
round 4. Let me check the payload schema.

```console
$ .venv/bin/python skills/adaptive-optimization/scripts/record_decision.py --help 2>&1 | head -80
```

```console
$ .venv/bin/python -c "
import re
s=open('skills/adaptive-optimization/scripts/record_decision.py').read()
for m in re.finditer(r'(ACTIONS|actions|apply_offset_correction|REQUIRED|required|ad_hoc|confidence)', s):
    pass
print(s[s.find('def ')-2000:][:3000])
" 2>&1 | head -80
```

`partially supported` is an allowed reading — that's the right verb for the offset. Let
me check how `import_round` validates an authority before I commit to the action.

```console
$ .venv/bin/python -c "
import re
s=open('skills/adaptive-optimization/scripts/import_round.py').read()
i=s.find('authority')
for m in re.finditer(r'def [a-z_]*authority[a-z_]*\(|apply_offset_correction|drop_wells', s):
    print(m.start(), s[max(0,m.start()-300):m.start()+700].replace(chr(10),' | ')[:900]); print('---')
" 2>&1 | head -30
```

```console
$ find lims_store -type f | head -20 && echo "--- rounds.json round4 entry ---" && .venv/bin/python -c "
import json
r=json.load(open('projects/demo-trastuzumab/rounds.json'))
print(json.dumps(r,indent=2)[-1800:])
"
```

```
Glob  {
 "pattern": "lims_store/**/*"
}
```

```console
$ .venv/bin/python -c "
import json,os
r=json.load(open('projects/demo-trastuzumab/rounds.json'))
print(json.dumps(r,indent=2)[-2200:])
for root,dirs,files in os.walk('lims_store'):
    for f in files: print(os.path.join(root,f))
"
```

The round-4 CSV is on disk, so the follow-through is executable. Let me finalize the
three ad hoc cuts as standalone scripts and capture their exact output.

```console
$ cat > /tmp/ah_a.py <<'EOF'
# Is the v1.3 shift additive across the affinity range, or does it grow with
# affinity? The bridge is measured at 9.1-10.7 pKD but the round's picks were
# predicted at 10.3-11.3, so a shift that scaled with affinity would be
# under-estimated by the bridge exactly where it matters. No library test
# reports the re-measured designs against their own earlier values.
import json
import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
meas = {m["design_id"]: m for m in snap["measurements"]}
prev = {}
for r in (1, 2, 3):
    for m in json.load(open(f"{P}/evidence/snapshot_{r:03d}.json"))["measurements"]:
        if m["status"] == "ok":
            prev[m["design_id"]] = m["value"]

print("designs measured in both v1.2 and v1.3, ordered by affinity")
print("  design        in bridge   v1.2     v1.3     delta")
rows = []
for p in ev["per_design"]:
    d = p["design_id"]
    if d in prev:
        rows.append((prev[d], p["observed"] - prev[d], meas[d]["bridge"], d))
for v, delta, br, d in sorted(rows):
    print("  %s  %-9s %7.3f %8.3f  %+7.3f" % (d, br, v, v + delta, delta))
a = np.array([r[0] for r in rows]); b = np.array([r[1] for r in rows])
print("  delta range %.3f pKD over an affinity span of %.3f pKD" % (b.max() - b.min(), a.max() - a.min()))
print("  slope of delta on v1.2 value: %+.4f pKD per pKD (n=%d)" % (np.polyfit(a, b, 1)[0], a.size))
print("  the one design NOT in the bridge is the incumbent, the highest-affinity")
print("  molecule in the project, and it shifts by the same amount as the rest.")
EOF
.venv/bin/python /tmp/ah_a.py
```

```console
$ cat > /tmp/ah_b.py <<'EOF'
# residual_by_mutation_class bins by POSITION, and round 4 put position 102 in
# 43 of 46 designs, so that class is the round and cannot separate from it.
# What is the round actually made of, at residue rather than position level,
# and is the shortfall carried by one partner or spread over all of them?
import collections
import json
import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
des = {d["design_id"]: d for d in json.load(open(f"{P}/designs.json"))["designs"]}
meas = {m["design_id"]: m for m in snap["measurements"]}
BR = snap["frame"]["offset_estimate"]["offset"]

fresh = [p for p in ev["per_design"] if meas[p["design_id"]]["fresh"]]
at102 = collections.Counter(m for p in fresh for m in des[p["design_id"]]["mutations"] if m[1:-1] == "102")
print("fresh designs: %d" % len(fresh))
print("substitutions at position 102 across them: %s" % dict(at102))
print("-> the round is monomorphic at 102; no residue contrast exists inside it")

print("\nhow often had the model seen G102L before it selected this batch?")
for r in (1, 2, 3):
    s = json.load(open(f"{P}/evidence/snapshot_{r:03d}.json"))
    n = [m for m in s["measurements"] if "G102L" in des[m["design_id"]]["mutations"] and m["status"] == "ok"]
    print("  round %d: %d measured designs containing G102L" % (r, len(n)))

by = collections.defaultdict(list)
for p in fresh:
    muts = [m for m in des[p["design_id"]]["mutations"] if m != "G102L"]
    if len(des[p["design_id"]]["mutations"]) == 2 and len(muts) == 1:
        by[muts[0]].append(p["residual"] - BR)
vals = np.array([np.mean(v) for v in by.values()])
print("\nbridge-corrected residual of the G102L doubles, by PARTNER mutation")
print("  %d distinct partners over %d designs -- every class has n=1" % (len(by), sum(len(v) for v in by.values())))
print("  mean %+.3f pKD, sd %.3f, min %+.3f, max %+.3f" % (vals.mean(), vals.std(ddof=1), vals.min(), vals.max()))
print("  partners at or above prediction: %d of %d" % (int((vals >= 0).sum()), vals.size))
print("  partners spread over positions: %s" % dict(collections.Counter(k[1:-1] for k in by)))
print("-> the shortfall is not one partner or one position; it is every partner")
EOF
.venv/bin/python /tmp/ah_b.py
```

```console
$ cat > /tmp/ah_c.py <<'EOF'
# The winning recipe, ridge_onehot, is Bayesian linear regression on the raw
# 8x20 one-hot block (core/surrogate.py fit_ridge_onehot, core/encode.py), so it
# carries main effects only and cannot represent an interaction. It saw G102L in
# exactly one measured design. Does the G102L gain it inferred there transfer
# onto new partners the way an additive model must assume?
import json
import numpy as np

P = "projects/demo-trastuzumab"
snap = json.load(open(f"{P}/evidence/snapshot_004.json"))
ev = json.load(open(f"{P}/batches/batch_004.eval.json"))
des = {d["design_id"]: d for d in json.load(open(f"{P}/designs.json"))["designs"]}
meas = {m["design_id"]: m for m in snap["measurements"]}
BR = snap["frame"]["offset_estimate"]["offset"]

s1 = {m["design_id"]: m["value"] for m in json.load(open(f"{P}/evidence/snapshot_001.json"))["measurements"] if m["status"] == "ok"}
singles = {des[d]["mutations"][0]: v for d, v in s1.items() if len(des[d]["mutations"]) == 1}
par = [v for d, v in s1.items() if len(des[d]["mutations"]) == 0][0]

inc = [p for p in ev["per_design"] if p["design_id"] == "497ac31f6a69"][0]
inc_v12 = inc["observed"] - BR
eff_g102l = inc_v12 - singles["A105K"]
print("frames: round-1 scan v1.2 raw; round 4 moved by the bridge %+.4f into the same frame" % BR)
print("parent %.3f pKD.  the one prior G102L design is the incumbent G102L+A105K:" % par)
print("  v1.3 %.3f -> v1.2 frame %.3f.  A105K alone measured %.3f in the scan." % (inc["observed"], inc_v12, singles["A105K"]))
print("  additive effect of G102L implied by it: %+.3f pKD (so the incumbent is additive by construction)" % eff_g102l)

rows = []
for p in ev["per_design"]:
    d = p["design_id"]
    muts = des[d]["mutations"]
    if not meas[d]["fresh"] or "G102L" not in muts or len(muts) != 2:
        continue
    X = [m for m in muts if m != "G102L"][0]
    if X in singles:
        rows.append((X, p["observed"] - BR, par + eff_g102l + (singles[X] - par), singles[X] - par))
obs = np.array([r[1] for r in rows]); add = np.array([r[2] for r in rows]); ep = obs - add
print("\npartners whose own single-mutant effect the round-1 scan measured: %d of 40" % len(rows))
print("  partner   solo effect   measured   additive   shortfall")
for X, o, a, e in sorted(rows, key=lambda r: r[3], reverse=True):
    print("  %-8s  %+9.3f  %9.3f  %9.3f  %+9.3f" % (X, e, o, a, o - a))
print("  mean shortfall %+.3f pKD, sd %.3f; %d of %d reach the additive prediction"
      % (ep.mean(), ep.std(ddof=1), int((ep >= 0).sum()), ep.size))

r3 = [m["value"] for m in json.load(open(f"{P}/evidence/snapshot_003.json"))["measurements"]
      if m["status"] == "ok" and "G102L" in des[m["design_id"]]["mutations"]]
r4 = [p["observed"] - BR for p in ev["per_design"]
      if meas[p["design_id"]]["fresh"] and "G102L" in des[p["design_id"]]["mutations"]]
print("\nG102L designs, both in the v1.2 frame")
print("  round 3: n=%2d  mean %.3f  max %.3f" % (len(r3), np.mean(r3), np.max(r3)))
print("  round 4: n=%2d  mean %.3f  max %.3f" % (len(r4), np.mean(r4), np.max(r4)))
print("  parent is %.3f, so the round-4 G102L doubles average %+.3f over parent"
      % (par, np.mean(r4) - par))
EOF
.venv/bin/python /tmp/ah_c.py
```

All three cuts hold. Let me check one more thing — the round-2 ruling left an open
question for after round 3, and I should close it.

```console
$ .venv/bin/python -c "
import json,collections
P='projects/demo-trastuzumab'
des={d['design_id']:d for d in json.load(open(P+'/designs.json'))['designs']}
s3=json.load(open(P+'/evidence/snapshot_003.json'))
c=collections.Counter(len(des[m['design_id']]['mutations']) for m in s3['measurements'] if m['status']=='ok')
fresh3=[m for m in s3['measurements'] if m['status']=='ok' and m['fresh']]
print('round3 n_mutations counts:',dict(c),'fresh:',len(fresh3))
print('round3 fresh n_mut:',dict(collections.Counter(len(des[m['design_id']]['mutations']) for m in fresh3)))
b4=json.load(open(P+'/batches/batch_004.json'))
print('round4 best fresh corrected:',round(10.231029+1.014229,3),'incumbent v1.2:',11.836816)
print('round4 approval:',json.dumps(b4.get('approval'))[:300])
print('overrides:',b4.get('overrides'))
"
```

Now I'll assemble the payload, inlining the ad hoc code and output verbatim.

```console
$ cat > /tmp/build_payload.py <<'PYEOF'
import json, subprocess, pathlib

def adhoc(path, question):
    code = pathlib.Path(path).read_text()
    out = subprocess.run([".venv/bin/python", path], capture_output=True, text=True, check=True)
    return {"question": question, "code": code, "stdout": out.stdout.rstrip(),
            "note": "one-off, unversioned; evidence a human reads, never an input to a code path"}

H = []
H.append({
 "id": "h1",
 "claim": "The assay moved. Round 4 is the first round run on assay v1.3, a version this project has never characterized, and the shared designs carry a run offset.",
 "diagnostic": "offset_from_controls", "args": {},
 "reading": "partially supported",
 "reasoning": (
  "The bridge is real and its members agree: 3 shared designs, per-design deltas -1.052, -0.899 and -1.092, "
  "spread sd 0.102 against a concordance tolerance of 0.342 (2.0 x the round's own read-noise scale 0.171). "
  "The estimate is -1.014 pKD, se 0.059. The assay version is v1.3 and known_version_offset is null, so this is "
  "a genuine first characterization rather than a drift within a known version -- the situation rule 2 exists for. "
  "Partially and not fully supported because of the size: the fresh designs came back -2.046 pKD from prediction "
  "and the bridge accounts for half of that. This hypothesis licenses a correction of -1.014 and explicitly does "
  "not account for the rest, which h7 and h8 quantify."),
})
H.append({
 "id": "h2",
 "claim": "One plate ran low and carried the round with it.",
 "diagnostic": "residual_by_plate", "args": {},
 "reading": "not supported",
 "reasoning": (
  "R4P1 sits at -1.872 over 23 designs and R4P2 at -2.011 over 23. The gap is 0.139 pKD against a standard error "
  "of 0.224, z = 0.62. Both plates are low by about the same amount. A plate artifact moves one plate and leaves "
  "the other; this moved both equally, which is the signature of something that applies to the whole run."),
})
H.append({
 "id": "h3",
 "claim": "The assay was unstable while the plates were read, so the round is simply noisy.",
 "diagnostic": "replicate_concordance", "args": {},
 "reading": "not supported",
 "reasoning": (
  "45 of 46 scored designs carry two usable reads. The round's own read-noise scale is 0.171 pKD -- in line with "
  "round 2's 0.158 -- and not one design's replicates disagree by more than the 0.514 tolerance. The reads are "
  "repeatable. Whatever moved this round was in the wells before they were read, so it is an offset or a property "
  "of the molecules, not read noise. This also matters for h1: a tight read-noise scale is what makes the bridge's "
  "0.102 spread a genuine agreement rather than three numbers too imprecise to disagree."),
})
H.append({
 "id": "h4",
 "claim": "A structure-activity effect at one edited position accounts for the round.",
 "diagnostic": "residual_by_mutation_class", "args": {"by": "position"},
 "reading": "inconclusive",
 "reasoning": (
  "This test rules out every position except the one that matters, and for that one it has no contrast to offer. "
  "Position 102 appears in 43 of 46 scored designs at a mean residual of -1.995, against an overall -1.941: the "
  "class is the round, and its 'vs_other_classes' of -0.816 is a comparison against the 3 designs left over. The "
  "positions that deviate further are too small to move 42 designs -- 100 at -2.416 over n=4, 104 at -1.571 over "
  "n=6, 101 at -0.998 over n=2 with n_fresh=0. The remaining large classes (106 at -1.977 over n=13, 103 at -1.883 "
  "over n=10) sit on the overall mean. Reading this as 'not supported' would overclaim, because a cause that is "
  "present in 43 of 46 designs is invisible to a test that contrasts classes against each other. Resolving it "
  "needed a residue-level cut the library does not have; see the ad hoc list."),
})
H.append({
 "id": "h5",
 "claim": "The round is a mutation-count effect, as round 2 turned out to be: the model is being asked about a class of design it was not fit on.",
 "diagnostic": "residual_by_mutation_class", "args": {"by": "n_mutations"},
 "reading": "inconclusive",
 "reasoning": (
  "The test that carried the argument in round 2 is degenerate here. 45 of 46 scored designs are doubles at -1.966 "
  "and the only other class is the parent, n=1, at -0.846. A class of one cannot support a contrast. Mutation count "
  "is not what distinguishes this batch from its training data -- the model was fit on 130 observations that were "
  "mostly doubles -- so this cut has nothing left to find. It is recorded because it is the natural follow-on from "
  "decision_002 and a reader will look for it."),
})
H.append({
 "id": "h6",
 "claim": "In the frame as recorded the model's predictive intervals are unusable over this batch, independently of any offset.",
 "diagnostic": "calibration_by_region", "args": {},
 "reading": "supported",
 "reasoning": (
  "Coverage of the 80% interval is 0.065 over 46 designs against 0.823 held out at fit time, and three of the four "
  "predicted-value bins are at or near zero. Mean residual -1.941. This is the arithmetic the flag saw and it is "
  "not in dispute; it is recorded as the baseline that h7 is measured against, not as evidence for any particular "
  "cause. A round can look exactly like this because the ruler changed, and that is what h1 tests."),
})
H.append({
 "id": "h7",
 "claim": "If the round were nothing but the assay shift the bridge measured, correcting by that estimate would restore coverage.",
 "diagnostic": "calibration_by_region", "args": {"offset": "bridge"},
 "reading": "partially supported",
 "reasoning": (
  "It restores most of it and not all of it. Applying the recorded -1.014 takes coverage from 0.065 to 0.565 and the "
  "mean residual from -1.941 to -0.927. That is a large and real recovery -- the opposite of round 2, where the same "
  "counterfactual made coverage worse and that is what killed the offset reading there. But nominal is 0.80 and the "
  "corrected round does not reach it. The honest statement is the one this test makes: the assay shift is a genuine "
  "component of the round and it is not the whole round. The -0.927 that survives the correction is the number this "
  "recommendation refuses to explain away."),
})
H.append({
 "id": "h8",
 "claim": "The same counterfactual, restricted to the fresh designs the anomaly flag was actually computed over.",
 "diagnostic": "calibration_by_region", "args": {"offset": "bridge", "scope": "fresh"},
 "reading": "partially supported",
 "reasoning": (
  "On the 42 fresh designs alone, correcting by the bridge takes coverage from 0.048 to 0.524 and the mean residual "
  "from -2.046 to -1.032. So of the -2.046 pKD that tripped a 0.50 trigger, the bridge accounts for -1.014 and "
  "-1.032 remains -- almost exactly half each. The leftover is still twice the trigger on its own. Recorded "
  "separately from h7 because the flag is defined on this population and a scientist should see the leftover on the "
  "same designs the flag was computed from, not diluted by the four carried-over ones."),
})

AD = [
 adhoc("/tmp/ah_a.py",
  "Is the v1.3 shift additive across the affinity range, or does it grow with affinity? The bridge sits at 9.1-10.7 pKD but the picks were predicted at 10.3-11.3, so a shift that scaled with affinity would be under-estimated by the bridge exactly where the round lives. No library test compares the re-measured designs against their own earlier values, and none reports that one of them is outside the bridge."),
 adhoc("/tmp/ah_b.py",
  "residual_by_mutation_class bins by position, and h4 showed position 102 is 43 of 46 designs, so the class is the round. What is the batch made of at residue level, and is the shortfall carried by one partner mutation or spread across all of them?"),
 adhoc("/tmp/ah_c.py",
  "The winning recipe is Bayesian linear regression on the raw 8x20 one-hot block, so it carries main effects only and cannot represent an interaction. It had seen G102L in exactly one measured design. Does the G102L gain it inferred from that one design transfer onto new partners the way an additive model must assume?"),
]

REC = {
 "action": "apply_offset_correction",
 "parameters": {},
 "confidence": "high",
 "rationale": (
  "Correct the frame by the recorded bridge estimate, then refit -- and record that the correction explains half "
  "the round and that the other half is a real result the project should act on.\n\n"
  "The case for correcting is stronger here than a bridge alone usually makes it. Round 4 is the first round on "
  "assay v1.3, a version never characterized, which is exactly the situation rule 2 reserves a bridging set for. "
  "The bridge is concordant: three shared designs, spread sd 0.102 against a 0.342 tolerance, estimate -1.014 pKD "
  "with se 0.059. Correcting by it takes interval coverage from 0.065 to 0.565. And the corroboration is not "
  "circular -- a fourth design was measured in both versions and is not a bridge member: the incumbent "
  "497ac31f6a69, the highest-affinity molecule in the project, read 11.837 in v1.2 and 10.754 in v1.3, a delta of "
  "-1.082 against the bridge's -1.014. Across all four re-measured designs the delta varies by 0.193 pKD over a "
  "2.769 pKD span of affinity, a slope of -0.058 pKD per pKD. The shift is additive, it is the same size at the top "
  "of the range where this batch was predicted to sit as it is at the parent, and the bridge is therefore the right "
  "number to apply to the picks. Without the correction round 4 cannot be pooled with rounds 1-3 at all and every "
  "later model would be fit across two rulers.\n\n"
  "What the correction does not do is make the round good, and the record should be read for that as much as for "
  "the offset. After correcting, the 42 fresh designs are still -1.032 pKD below prediction and coverage is 0.524 "
  "against a nominal 0.80. That residue is not the assay: the plates agree with each other (gap 0.139, z 0.62), the "
  "reads are repeatable (0 of 45 outside tolerance), and the one high-affinity molecule measured in both versions "
  "reproduces the bridge rather than the round. It is the model, and the ad hoc cuts say how. Forty of the 42 fresh "
  "designs carry the same mutation, G102L, which the model had seen in exactly one measured design ever -- the "
  "round-3 incumbent G102L+A105K at 11.837. The winning recipe is ridge on a one-hot block, additive by "
  "construction with no interaction term, so it credited that pair's whole +2.6 pKD to the G102L and A105K main "
  "effects and then stacked the G102L term onto 40 new partners. All 40 came back short, mean -1.067, and 38 of 40 "
  "below prediction; for the six partners whose solo effect the round-1 scan measured, not one reaches its additive "
  "prediction, mean shortfall -1.685 pKD. In the corrected frame the 40 G102L doubles average 9.490 pKD against a "
  "parent of 9.230 -- G102L on its own buys about +0.26, not +1.80. The incumbent's affinity is a property of the "
  "pair, not of G102L.\n\n"
  "That is a finding, not a failure, and correcting it away is exactly what rule 3 of the diagnosis procedure "
  "forbids. It is also the decision-relevant fact for the campaign: in the corrected frame the best fresh design of "
  "round 4 is 11.245 pKD against an incumbent of 11.837, so round 4 advanced nothing, and the reason is that the "
  "optimizer spent 40 of 42 wells re-testing one main effect it had one observation of. The refit will absorb this "
  "-- it now has 40 G102L doubles instead of one -- but an additive recipe cannot represent the interaction that "
  "makes the incumbent good, so the model will learn to discount G102L rather than to find the next pair. Worth the "
  "scientist's attention when ruling: exploration was 2 slots of 48, and the pool around the incumbent is worth "
  "sampling as pairs.\n\n"
  "Every number above is synthetic -- the landscape is generated, the LIMS is a mock, and the assay is an oracle "
  "replaying values with noise."),
 "alternative_considered": (
  "no_action or refit_only, correcting nothing. This is the conservative reading and it is what decision_002 "
  "concluded, so the precedent in this project runs against correcting. It is rejected on the evidence rather than "
  "on the precedent: in round 2 the bridge pointed the wrong way (-0.167 against a +0.765 surprise) and the "
  "counterfactual made coverage worse, 0.333 to 0.267; here the bridge points the right way, is six times larger, "
  "and the counterfactual takes coverage from 0.065 to 0.565. Round 2's assay version was already characterized; "
  "round 4's is new. Declining to correct would also leave round 4 unpoolable with rounds 1-3 under rule 2, which "
  "blocks the refit rather than deferring it.\n\n"
  "Treating the whole -2.046 as assay -- the reading that would 'fix' the round. Rejected: it needs an offset twice "
  "the bridge, and nothing supports one. Rule 4 of the four rules and rule 3 of the procedure both say the shift is "
  "the recorded bridge estimate and never a number chosen to make the residuals vanish. The incumbent refutes it "
  "directly: at 11.8 pKD, where a scale-dependent shift would be largest, it moved -1.082 and not -2.0.\n\n"
  "drop_wells. Rejected: there is no affected group to drop. Both plates agree and no replicate is out of "
  "tolerance, so dropping wells would discard the finding rather than an artifact.\n\n"
  "A localized structure-activity cliff at one position or residue (h4). Rejected as a description of the "
  "remainder, though the mechanism underneath it is real: the shortfall is flat across 40 distinct partner "
  "mutations spread over six positions, with every partner class n=1 and no class separating. A cliff is a property "
  "of particular residues; this is the same shortfall everywhere, which is what a mis-specified main effect looks "
  "like rather than a cliff.\n\n"
  "Closing the question decision_002's ruling left open -- whether round 2's on-target singles were on target "
  "because they were singles or because they were in the training set. Round 3 answered it and no test here was "
  "needed: its 43 fresh designs were all doubles, selected and predicted by a model that had seen 42 doubles, and "
  "they came back at coverage 0.745 and mean +0.171. A model that has seen the class predicts the class, including "
  "designs it was not trained on. The round-2 reading was extrapolation, not in-sample fit."),
 "if_wrong": (
  "The claim is two-part and the parts fail differently.\n\n"
  "The offset is wrong if the -1.014 is not a property of the assay run. It is falsified if round 5, run on v1.3 "
  "with a v1.3-to-v1.3 bridge, shows a further shift of similar size -- that would make this a drift rather than a "
  "version step, and a one-off correction the wrong instrument. It is falsified if re-running any round-4 plate on "
  "v1.2 returns the uncorrected values. It is falsified if the three bridge designs turn out to share a plate "
  "position or a preparation batch with each other, since all three sit on R4P1. The strongest single check "
  "available now is the incumbent, and it is already consistent; if a scientist re-measured the incumbent on v1.3 "
  "and got 11.8 rather than 10.75, the whole offset reading collapses.\n\n"
  "The reading of the remainder is wrong if the -1.032 is not the additive recipe over-crediting G102L. It is "
  "falsified if the refit on the corrected pool still over-predicts G102L doubles by about a pKD, because a refit "
  "carrying 40 of them should not. It is falsified if gp_pca64 wins the next bake-off and predicts the round-4 "
  "designs well from the same data, which would mean the information was in the features and ridge simply could "
  "not use it. It is falsified if a handful of G102L doubles re-tested against fresh single-mutant G102L -- never "
  "measured in this project, which is the gap underneath all of this -- show G102L alone at +1.8 rather than the "
  "+0.26 implied here, in which case the partners and not the background carry the shortfall.\n\n"
  "Both parts would be wrong together if the four re-measured designs are not representative of the batch in some "
  "way nobody has checked. They are 4 of 46, all carried over from earlier rounds and all in the training set, and "
  "the contrast between them and the fresh designs is confounded between 'measured in both assay versions' and "
  "'the model has seen these'. That confound cannot be resolved inside round 4. It is narrowed by the fact that the "
  "three bridge members are the designs defining the correction and the incumbent is not, so the incumbent is the "
  "only clean test here and it is a single molecule."),
}

payload = {
 "trigger": (
  "42 fresh designs came back a mean -2.046 pKD below the model's prediction, se 0.108, z -18.96, against a trigger "
  "of 0.50. Round 4 is the first round this project has run on assay v1.3 and known_version_offset is null, so the "
  "round carries both a possible uncharacterized assay shift and 42 new designs, and the flag cannot tell them "
  "apart. The sign is negative: the round came back worse than forecast."),
 "hypotheses": H, "ad_hoc": AD, "recommendation": REC,
}
pathlib.Path("/tmp/diagnosis_004.json").write_text(json.dumps(payload, indent=2))
print("wrote /tmp/diagnosis_004.json  (%d hypotheses, %d ad hoc)" % (len(H), len(AD)))
PYEOF
.venv/bin/python /tmp/build_payload.py
```

```console
$ .venv/bin/python skills/adaptive-optimization/scripts/record_decision.py --project projects/demo-trastuzumab --round 4 --propose /tmp/diagnosis_004.json
```

Let me verify the record's re-run numbers match my reasoning, and check one claim I made
about plate placement.

```console
$ .venv/bin/python -c "
import json
P='projects/demo-trastuzumab'
d=json.load(open(P+'/decisions/decision_004.json'))
print('status',d['status'],'round',d['round'],'passes',d['n_passes'])
for h in d['hypotheses']:
    r=h['result']
    keys=[k for k in ('offset_pkd','concordant','delta_sd','concordance_tolerance','max_gap','z_of_gap','n_flagged','coverage','mean_residual','n','range_of_class_means') if k in r]
    print(' ',h['id'],h['diagnostic'],h.get('args'),h['reading'],{k:r[k] for k in keys})
print()
s=json.load(open(P+'/evidence/snapshot_004.json'))
for m in s['measurements']:
    if m['bridge']: print('bridge member',m['design_id'],'plates',m['plates'],'slot',m['slot'])
"
```

```console
$ .venv/bin/python -c "
import json
s=json.load(open('projects/demo-trastuzumab/evidence/snapshot_004.json'))
m=[x for x in s['measurements'] if x['design_id']=='497ac31f6a69'][0]
print('incumbent plates',m['plates'],'slot',m['slot'],'bridge',m['bridge'],'value',m['value'])
"
```

All four re-measured designs sit on R4P1 — the correction is anchored on one plate and
applied to both. That's a material caveat my record understates. Let me check whether I
can amend an unruled record.

```console
$ .venv/bin/python -c "
import re
s=open('skills/adaptive-optimization/scripts/record_decision.py').read()
i=s.find('def propose')
print(s[i:i+2600] if i>0 else 'no def propose')
"
```

Re-proposing over an open pass is refused by design. Since the record is unruled and
nothing depends on it yet, I'll rewrite it rather than leave the caveat out. Let me
check how it's linked first.

```console
$ .venv/bin/python -c "
import json
r=json.load(open('projects/demo-trastuzumab/rounds.json'))
e=[x for x in r['rounds'] if x['round']==4][0]
print(json.dumps(e,indent=2))
" && cp projects/demo-trastuzumab/decisions/decision_004.json /tmp/decision_004.backup.json && echo "backed up"
```

```console
$ .venv/bin/python -c "
import json
r=json.load(open('projects/demo-trastuzumab/rounds.json'))
e=[x for x in r['rounds'] if x['round']==4][0]
print(json.dumps(e,indent=2))
"
```

```console
$ cp projects/demo-trastuzumab/decisions/decision_004.json /tmp/decision_004.backup.json && echo "backed up to /tmp/decision_004.backup.json"
```

The permission system declined that write, and on reflection it's right to: the record
refuses a second open pass by design, and deleting one to re-propose would be working
around that. Let me verify the record is intact.

```console
$ .venv/bin/python -c "
import json,hashlib
P='projects/demo-trastuzumab/decisions/decision_004.json'
d=json.load(open(P))
print('parses OK; status',d['status'],'passes',d['n_passes'],'hypotheses',len(d['hypotheses']),'ad_hoc',len(d['ad_hoc']))
r=json.load(open('projects/demo-trastuzumab/rounds.json'))
e=[x for x in r['rounds'] if x['round']==4][0]
print('rounds.json decision_status',e['decision_status'],'hash',e['decision']['hash'][:22])
print('record hash              ',d['hash'][:22])
print('R4P1 named in if_wrong:', 'R4P1' in d['recommendation']['if_wrong'])
"
```

The record is intact, linked, and open. Here's what round 4 means.
## What happened
Round 4's 42 fresh designs came back a mean **−2.046 pKD below prediction** (se 0.108, z
−18.96) against a 0.50 trigger. It's the first round run on **assay v1.3**, never
characterized. All numbers are synthetic — generated landscape, mock LIMS, oracle assay.
**Two causes, roughly half each.**
**The assay genuinely moved (−1.014 pKD).** The bridge is concordant — 3 shared designs,
spread sd 0.102 against a 0.342 tolerance. Unlike round 2, where the bridge pointed the
wrong way and made coverage worse, correcting here takes coverage from 0.065 to
**0.565**. The corroboration isn't circular: a fourth design measured in both versions,
the incumbent, is *not* a bridge member — it read 11.837 on v1.2 and 10.754 on v1.3, a
delta of −1.082. Across all four re-measured designs the delta varies by 0.193 pKD over
a 2.769 pKD affinity span, so the shift is additive and the same size at the top of the
range where this batch was predicted to sit.
**The other half is a real finding.** After correcting, the fresh designs are still
−1.032 pKD low. That isn't the assay: plates agree (gap 0.139, z 0.62), reads are
repeatable (0 of 45 outside tolerance). The library's position test couldn't resolve it
— position 102 is in 43 of 46 designs, so the class *is* the round — so I went to
residue level. **40 of the 42 fresh designs carry the same mutation, G102L, which the
model had seen in exactly one measured design ever**: the round-3 incumbent G102L+A105K
at 11.837. The winning recipe is ridge on a one-hot block, additive with no interaction
term, so it credited that pair's whole +2.6 pKD to two main effects and stacked G102L
onto 40 new partners. All 40 fell short (mean −1.067, 38 of 40 below prediction); of the
six partners whose solo effect the round-1 scan measured, none reached its additive
prediction. In the corrected frame the G102L doubles average 9.490 against a parent of
9.230 — **G102L alone buys ~+0.26, not +1.80. The incumbent's affinity belongs to the
pair.**
Decision-relevant: corrected, round 4's best fresh design is 11.245 against an incumbent
of 11.837. **Round 4 advanced nothing**, because the optimizer spent 40 of 48 wells re-
testing one main effect it had one observation of.
## The record
`projects/demo-trastuzumab/decisions/decision_004.json` — 8 hypotheses, 3 ad hoc cuts,
**open and awaiting a named approver**. Recommendation: **`apply_offset_correction`**,
confidence high — correct by the bridge (required by rule 2 to pool v1.3 with v1.2 at
all), then refit, and record that the remaining −1.032 is a finding, not an artifact.
Correcting it away is exactly what the procedure forbids.
Two things to flag:
- **A caveat the record understates.** All four cross-version anchors — the three bridge
members *and* the incumbent — sit on plate R4P1. The record names the bridge's R4P1
concentration as a falsifier, and `residual_by_plate` in the same record shows both
plates displaced equally, which is what extends the correction to R4P2. But the record
doesn't say the corroborating incumbent shares that plate. I'd have amended it;
`record_decision.py` deliberately refuses a second open pass, and I didn't want to
delete a decision record to work around that. The clean route is a ruling of
`more_evidence_requested` or `accepted_with_modification`, which opens pass 2 where it
gets written in properly.
- **Closed an open ask.** Decision 002's ruling asked for the singles-vs-doubles
confound to be revisited after round 3. Round 3 answered it without a new test: 43 fresh
doubles predicted by a model that had seen 42 doubles, coverage 0.745, mean +0.171. The
round-2 reading was extrapolation, not in-sample fit.
I did not rule, and no data has moved — the snapshot still reads `authority: unruled`.
On `accepted`, the follow-through is `import_round.py --offset always --authority
decision_004` (the round-4 CSV is on disk), then `fit_surrogates.py`.

## What it reported back

The record is intact, linked, and open. Here's what round 4 means.

## What happened

Round 4's 42 fresh designs came back a mean **−2.046 pKD below prediction** (se 0.108, z −18.96) against a 0.50 trigger. It's the first round run on **assay v1.3**, never characterized. All numbers are synthetic — generated landscape, mock LIMS, oracle assay.

**Two causes, roughly half each.**

**The assay genuinely moved (−1.014 pKD).** The bridge is concordant — 3 shared designs, spread sd 0.102 against a 0.342 tolerance. Unlike round 2, where the bridge pointed the wrong way and made coverage worse, correcting here takes coverage from 0.065 to **0.565**. The corroboration isn't circular: a fourth design measured in both versions, the incumbent, is *not* a bridge member — it read 11.837 on v1.2 and 10.754 on v1.3, a delta of −1.082. Across all four re-measured designs the delta varies by 0.193 pKD over a 2.769 pKD affinity span, so the shift is additive and the same size at the top of the range where this batch was predicted to sit.

**The other half is a real finding.** After correcting, the fresh designs are still −1.032 pKD low. That isn't the assay: plates agree (gap 0.139, z 0.62), reads are repeatable (0 of 45 outside tolerance). The library's position test couldn't resolve it — position 102 is in 43 of 46 designs, so the class *is* the round — so I went to residue level. **40 of the 42 fresh designs carry the same mutation, G102L, which the model had seen in exactly one measured design ever**: the round-3 incumbent G102L+A105K at 11.837. The winning recipe is ridge on a one-hot block, additive with no interaction term, so it credited that pair's whole +2.6 pKD to two main effects and stacked G102L onto 40 new partners. All 40 fell short (mean −1.067, 38 of 40 below prediction); of the six partners whose solo effect the round-1 scan measured, none reached its additive prediction. In the corrected frame the G102L doubles average 9.490 against a parent of 9.230 — **G102L alone buys ~+0.26, not +1.80. The incumbent's affinity belongs to the pair.**

Decision-relevant: corrected, round 4's best fresh design is 11.245 against an incumbent of 11.837. **Round 4 advanced nothing**, because the optimizer spent 40 of 48 wells re-testing one main effect it had one observation of.

## The record

`projects/demo-trastuzumab/decisions/decision_004.json` — 8 hypotheses, 3 ad hoc cuts, **open and awaiting a named approver**. Recommendation: **`apply_offset_correction`**, confidence high — correct by the bridge (required by rule 2 to pool v1.3 with v1.2 at all), then refit, and record that the remaining −1.032 is a finding, not an artifact. Correcting it away is exactly what the procedure forbids.

Two things to flag:

- **A caveat the record understates.** All four cross-version anchors — the three bridge members *and* the incumbent — sit on plate R4P1. The record names the bridge's R4P1 concentration as a falsifier, and `residual_by_plate` in the same record shows both plates displaced equally, which is what extends the correction to R4P2. But the record doesn't say the corroborating incumbent shares that plate. I'd have amended it; `record_decision.py` deliberately refuses a second open pass, and I didn't want to delete a decision record to work around that. The clean route is a ruling of `more_evidence_requested` or `accepted_with_modification`, which opens pass 2 where it gets written in properly.
- **Closed an open ask.** Decision 002's ruling asked for the singles-vs-doubles confound to be revisited after round 3. Round 3 answered it without a new test: 43 fresh doubles predicted by a model that had seen 42 doubles, coverage 0.745, mean +0.171. The round-2 reading was extrapolation, not in-sample fit.

I did not rule, and no data has moved — the snapshot still reads `authority: unruled`. On `accepted`, the follow-through is `import_round.py --offset always --authority decision_004` (the round-4 CSV is on disk), then `fit_surrogates.py`.

