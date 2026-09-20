#!/usr/bin/env python3
"""Instantiate a project directory from a template.

    python init_project.py --template antibody-affinity-maturation \
                           --name demo-trastuzumab --lead trastuzumab --target HER2

Project creation is not part of the round loop, so it is not one of the skill's
seven scripts -- the skill operates on a project that already exists.

It writes no designs and no candidate pool. Round 1 goes through
generate_candidates.py and select_batch.py like every other round, because a
round-1 batch written by a second code path is a round-1 batch with no batch
record, no rationale and no approval. The pool summary printed below is a
report on the template's constraints, not a stored artifact.

``--created`` pins the timestamp the four files carry. Instantiation is
otherwise a pure function of the template and the three facts a person
supplies, so pinning it is what makes "the browser and the terminal
instantiate the same project" a claim somebody can check byte for byte rather
than eyeball. The browser passes it; a person at a terminal has no reason to.
"""

import argparse
import os
import sys

from core import project, schema

REPO = os.path.dirname(os.path.abspath(__file__))


def clear_artifacts(root):
    """Empty the numbered artifacts so --force rebuilds rather than overlays.

    Instantiating rewrites the four top-level files and resets the round
    graph, but the snapshots, batches, pools, models and decisions are
    numbered per round and would otherwise survive. A project that carried
    round 4 from a previous build under a round graph that has never heard of
    it is a chimera: the pipeline reads artifacts by filename, so the stale
    ones are found, used, and silently mixed with the new. Nothing else in the
    build deletes anything, which is why this says how many it removed.
    """
    removed = 0
    for sub in schema.SUBDIRS:
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".json"):
                os.remove(os.path.join(d, name))
                removed += 1
    return removed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", default="antibody-affinity-maturation")
    ap.add_argument("--name", default="demo-trastuzumab")
    ap.add_argument("--lead", default=None)
    ap.add_argument("--target", default="HER2")
    ap.add_argument("--team", default="")
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--projects-dir", default=os.path.join(REPO, "projects"))
    ap.add_argument("--created", default=None,
                    help="pin the creation timestamp, so two surfaces instantiating the "
                         "same template write byte-identical files")
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

    cleared = clear_artifacts(root) if args.force else 0

    team = [t.strip() for t in args.team.split(",") if t.strip()]
    project.create(root, tpl, lead_name=args.lead, target=args.target,
                   team=team, batch_size=args.batch_size, created=args.created)
    state = project.load(root)

    kept, removed, summary = project.feasible_pool(state)
    obj = state["objectives"]
    region, batch = obj["editable_region"], obj["batch"]
    parent = state["designs"]["parent"]

    print("project         %s" % root)
    print("template        %s v%s" % (tpl["id"], tpl["version"]))
    print("editable region %s -> %s" % (region, parent[region[0]:region[1]]))
    print("enumerated      %d" % (len(kept) + len(removed)))
    print("feasible        %d  (removed %d: %s)" % (len(kept), len(removed), summary))
    print("batch policy    %d wells: %d control, %d replicate, %d exploration"
          % (batch["size"], batch["controls"], batch["replicates"], batch["exploration_slots"]))
    print("round 1 policy  %s" % batch.get("round1_policy", "diversity"))
    print("recipes         %s" % ", ".join(obj["model_recipes"]))
    print("diagnostics     %s" % ", ".join(obj["diagnostics"]))
    print("designs         0 -- run generate_candidates.py then select_batch.py for round 1")
    if cleared:
        print("cleared         %d artifacts from a previous build of this project" % cleared)
    print("objectives hash %s" % obj["hash"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
