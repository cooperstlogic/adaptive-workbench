#!/usr/bin/env python3
"""Instantiate a project directory from a template and write round-1 designs.

    python init_project.py --template antibody-affinity-maturation \
                           --name demo-trastuzumab --lead trastuzumab --target HER2

Project creation is not part of the round loop, so it is not one of the skill's
seven scripts -- the skill operates on a project that already exists.
"""

import argparse
import os
import sys

from core import candidates, encode, project, schema

REPO = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", default="antibody-affinity-maturation")
    ap.add_argument("--name", default="demo-trastuzumab")
    ap.add_argument("--lead", default=None)
    ap.add_argument("--target", default="HER2")
    ap.add_argument("--team", default="")
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--projects-dir", default=os.path.join(REPO, "projects"))
    ap.add_argument("--force", action="store_true", help="overwrite an existing project directory")
    args = ap.parse_args(argv)

    tpl_path = os.path.join(REPO, "templates", args.template, "template.json")
    if not os.path.exists(tpl_path):
        print("no such template: %s" % args.template, file=sys.stderr)
        return 2
    tpl = schema.read_json(tpl_path)
    if tpl.get("status") == "stub":
        print("template %r is a stub and cannot be instantiated" % args.template, file=sys.stderr)
        return 2

    root = os.path.join(args.projects_dir, args.name)
    if os.path.exists(os.path.join(root, "project.json")) and not args.force:
        print("project already exists at %s (use --force)" % root, file=sys.stderr)
        return 2

    team = [t.strip() for t in args.team.split(",") if t.strip()]
    project.create(root, tpl, lead_name=args.lead, target=args.target,
                   team=team, batch_size=args.batch_size)
    state = project.load(root)

    kept, removed, summary = project.feasible_pool(state)
    obj = state["objectives"]
    region, batch = obj["editable_region"], obj["batch"]

    parent = state["designs"]["parent"]
    policy = batch.get("round1_policy", "diversity")
    if policy == "single_mutant_scan":
        draw = [s for s in kept if encode.n_mutations(parent, s, region) <= 1]
    else:
        draw = kept
    seed_idx = candidates.diversity_seed_batch(
        draw, batch["size"], region, seed_index=draw.index(parent)
    )
    seed = [draw[i] for i in seed_idx]
    added = project.add_designs(state, seed, origin="round1_diversity_seed", round_id=1)

    pool_rec = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "round": 1,
        "enumerated": len(kept) + len(removed),
        "feasible": len(kept),
        "removed": len(removed),
        "removed_by_reason": summary,
        "round1_policy": policy,
        "round1_draw_size": len(draw),
        "max_mutations": obj["constraints"]["max_mutations"],
        "editable_region": region,
    }, inputs={"objectives": obj["hash"]})
    schema.write_json(os.path.join(state["paths"]["candidates"], "pool_001.json"), pool_rec)

    print("project         %s" % root)
    print("template        %s v%s" % (tpl["id"], tpl["version"]))
    print("editable region %s -> %s" % (region, parent[region[0]:region[1]]))
    print("enumerated      %d" % (len(kept) + len(removed)))
    print("feasible        %d  (removed %d: %s)" % (len(kept), len(removed), summary))
    print("round 1 policy  %s  (drawing from %d of %d feasible)" % (policy, len(draw), len(kept)))
    print("round 1 designs %d  (%d new), min pairwise distance %.0f"
          % (len(seed), len(added), candidates.max_min_distance(seed, region)))
    print("parent in batch %s" % (parent in seed))
    print("objectives hash %s" % obj["hash"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
