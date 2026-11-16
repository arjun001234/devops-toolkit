#!/usr/bin/env python3
"""Audit Kubernetes workloads for containers missing CPU/memory requests or limits.

Reads `kubectl get <kinds> -A -o json` output (a List or a single object) from a
file or stdin, prints a table of findings and exits non-zero when any are found.

Exit codes:
  0  no findings
  1  findings (at or above --fail-on)
  2  bad input / usage error
"""
import argparse
import json
import sys

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob", "Pod"}
CHECKS = ("cpu-request", "memory-request", "memory-limit", "cpu-limit")
# Missing memory requests/limits are the ones that cause OOM kills and bad bin-packing;
# a missing CPU limit is often a deliberate choice (avoids CFS throttling), so it is a warning.
SEVERITY = {"cpu-request": "error", "memory-request": "error", "memory-limit": "error", "cpu-limit": "warning"}
SEV_RANK = {"warning": 1, "error": 2}
DEFAULT_SKIP_NAMESPACES = {"kube-system", "kube-public", "kube-node-lease"}


def pod_spec(obj):
    kind = obj.get("kind")
    spec = obj.get("spec") or {}
    if kind == "Pod":
        return spec
    if kind == "CronJob":
        return (((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {}).get("spec") or {}
    return (spec.get("template") or {}).get("spec") or {}


def owned_by_controller(obj):
    """Skip Pods/ReplicaSets/Jobs created by a higher-level controller to avoid duplicate rows."""
    for ref in (obj.get("metadata") or {}).get("ownerReferences") or []:
        if ref.get("controller"):
            return True
    return False


def container_findings(container, check_limits_cpu):
    res = container.get("resources") or {}
    requests = res.get("requests") or {}
    limits = res.get("limits") or {}
    missing = []
    # Kubernetes defaults requests to limits when only limits are set.
    if "cpu" not in requests and "cpu" not in limits:
        missing.append("cpu-request")
    if "memory" not in requests and "memory" not in limits:
        missing.append("memory-request")
    if "memory" not in limits:
        missing.append("memory-limit")
    if check_limits_cpu and "cpu" not in limits:
        missing.append("cpu-limit")
    return missing


def audit(items, skip_ns, check_cpu_limit, include_init):
    rows = []
    for obj in items:
        kind = obj.get("kind")
        if kind not in WORKLOAD_KINDS:
            continue
        if kind in {"Pod", "ReplicaSet", "Job"} and owned_by_controller(obj):
            continue
        meta = obj.get("metadata") or {}
        ns = meta.get("namespace", "default")
        if ns in skip_ns:
            continue
        spec = pod_spec(obj)
        groups = [("container", spec.get("containers") or [])]
        if include_init:
            groups.append(("init", spec.get("initContainers") or []))
        for ctype, containers in groups:
            for c in containers:
                for check in container_findings(c, check_cpu_limit):
                    rows.append({
                        "namespace": ns,
                        "kind": kind,
                        "name": meta.get("name", "?"),
                        "container": c.get("name", "?") + (" (init)" if ctype == "init" else ""),
                        "missing": check,
                        "severity": SEVERITY[check],
                    })
    rows.sort(key=lambda r: (r["namespace"], r["kind"], r["name"], r["container"], CHECKS.index(r["missing"])))
    return rows


def print_table(rows):
    cols = ["namespace", "kind", "name", "container", "missing", "severity"]
    widths = {c: max(len(c), *(len(r[c]) for r in rows)) for c in cols}
    print("  ".join(c.upper().ljust(widths[c]) for c in cols).rstrip())
    for r in rows:
        print("  ".join(r[c].ljust(widths[c]) for c in cols).rstrip())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", default="-", help="kubectl JSON output (default: stdin)")
    p.add_argument("--format", choices=["table", "json"], default="table")
    p.add_argument("--fail-on", choices=["warning", "error", "never"], default="error",
                   help="lowest severity that causes exit code 1 (default: error)")
    p.add_argument("--no-cpu-limit-check", action="store_true",
                   help="do not report missing CPU limits")
    p.add_argument("--include-init", action="store_true", help="also audit initContainers")
    p.add_argument("--include-system", action="store_true",
                   help="include kube-system, kube-public and kube-node-lease")
    p.add_argument("--skip-namespace", action="append", default=[], metavar="NS",
                   help="namespace to skip (repeatable)")
    args = p.parse_args(argv)

    try:
        raw = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read kubectl JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("error: expected a Kubernetes object or List", file=sys.stderr)
        return 2
    items = data.get("items") if "items" in data else [data]

    skip = set(args.skip_namespace)
    if not args.include_system:
        skip |= DEFAULT_SKIP_NAMESPACES
    rows = audit(items, skip, not args.no_cpu_limit_check, args.include_init)

    if args.format == "json":
        print(json.dumps(rows, indent=2))
    elif rows:
        print_table(rows)
        errors = sum(r["severity"] == "error" for r in rows)
        print(f"\n{len(rows)} finding(s): {errors} error, {len(rows) - errors} warning")
    else:
        print("All audited containers set CPU/memory requests and limits.")

    if args.fail_on == "never" or not rows:
        return 0
    threshold = SEV_RANK[args.fail_on]
    return 1 if any(SEV_RANK[r["severity"]] >= threshold for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
