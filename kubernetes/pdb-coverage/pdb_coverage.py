#!/usr/bin/env python3
"""Report workloads that no PodDisruptionBudget protects.

During node drains (EKS upgrades, Karpenter consolidation, Spot interruptions) a
Deployment or StatefulSet with more than one replica but no matching PDB can lose
all its pods at once. This script reads the cluster state from kubectl JSON and
lists those gaps.

Usage:
  kubectl get deploy,sts,pdb -A -o json | python3 pdb_coverage.py
  python3 pdb_coverage.py cluster.json            # from a saved file
  python3 pdb_coverage.py cluster.json --min-replicas 1

Exit code is 1 when uncovered workloads are found, so it can gate a CI job.
"""
import argparse
import json
import sys


def selector_matches(selector, labels):
    """Evaluate a Kubernetes label selector (matchLabels + matchExpressions)."""
    if not selector:
        return False  # an empty PDB selector is treated as matching nothing here
    for k, v in (selector.get("matchLabels") or {}).items():
        if labels.get(k) != v:
            return False
    for expr in selector.get("matchExpressions") or []:
        key, op, values = expr["key"], expr["operator"], expr.get("values") or []
        if op == "In" and labels.get(key) not in values:
            return False
        if op == "NotIn" and labels.get(key) in values:
            return False
        if op == "Exists" and key not in labels:
            return False
        if op == "DoesNotExist" and key in labels:
            return False
    return True


def analyse(items, min_replicas=2):
    pdbs = [i for i in items if i.get("kind") == "PodDisruptionBudget"]
    workloads = [i for i in items if i.get("kind") in ("Deployment", "StatefulSet")]
    uncovered = []
    for w in workloads:
        ns = w["metadata"].get("namespace", "default")
        replicas = (w.get("spec") or {}).get("replicas", 1)
        if replicas < min_replicas:
            continue
        pod_labels = (((w.get("spec") or {}).get("template") or {}).get("metadata") or {}).get("labels") or {}
        covered = any(
            p["metadata"].get("namespace", "default") == ns
            and selector_matches((p.get("spec") or {}).get("selector"), pod_labels)
            for p in pdbs
        )
        if not covered:
            uncovered.append((ns, w["kind"], w["metadata"]["name"], replicas))
    return uncovered


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", nargs="?", help="kubectl JSON output (default: stdin)")
    ap.add_argument("--min-replicas", type=int, default=2,
                    help="only check workloads with at least this many replicas (default 2)")
    args = ap.parse_args(argv)
    data = json.load(open(args.file) if args.file else sys.stdin)
    items = data.get("items", [data])
    gaps = analyse(items, args.min_replicas)
    if not gaps:
        print("All multi-replica workloads are covered by a PodDisruptionBudget.")
        return 0
    print(f"{'NAMESPACE':<20} {'KIND':<12} {'NAME':<40} REPLICAS")
    for ns, kind, name, rep in sorted(gaps):
        print(f"{ns:<20} {kind:<12} {name:<40} {rep}")
    print(f"\n{len(gaps)} workload(s) without a PodDisruptionBudget.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
