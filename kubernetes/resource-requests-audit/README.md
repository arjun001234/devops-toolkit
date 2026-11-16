# resource-requests-audit

Finds containers that are missing CPU/memory **requests** or **limits** in Deployments, StatefulSets, DaemonSets, CronJobs, Jobs and standalone Pods. It reads `kubectl ... -o json`, prints a table and returns a non-zero exit code, so it works both as a quick cluster check and as a CI gate.

## Why it matters on EKS

- **Scheduling and bin-packing.** The scheduler, Cluster Autoscaler and Karpenter all size nodes from *requests*. Pods without requests look free, get packed onto nodes that cannot actually hold them, and Karpenter consolidation can move them onto nodes that are too small.
- **OOM kills and noisy neighbours.** A container without a memory limit can take memory from everything else on the node until the kubelet starts evicting pods or the kernel OOM-kills something unrelated.
- **QoS class.** Pods with no requests are `BestEffort` and are evicted first under node pressure.
- **Cost.** Without requests you cannot reason about utilisation per namespace, and right-sizing (or Spot vs on-demand planning) becomes guesswork.

Missing CPU **limits** are reported as a *warning*, not an error: many teams leave CPU limits off on purpose to avoid CFS throttling. Use `--no-cpu-limit-check` to hide them entirely.

## What it checks

| Check | Severity | Notes |
|---|---|---|
| `cpu-request` | error | satisfied by a CPU limit too, since Kubernetes defaults requests to limits |
| `memory-request` | error | same defaulting rule as above |
| `memory-limit` | error | |
| `cpu-limit` | warning | off with `--no-cpu-limit-check` |

Pods, ReplicaSets and Jobs that are owned by a controller are skipped so each finding is reported once, against the object you actually edit. `kube-system`, `kube-public` and `kube-node-lease` are skipped by default.

## Usage

Python 3.8+, no third-party packages.

```bash
# Whole cluster
kubectl get deploy,sts,ds,cronjob,job,pod -A -o json | ./resource_requests_audit.py

# One namespace, include init containers, ignore CPU limits
kubectl get deploy,sts -n payments -o json \
  | ./resource_requests_audit.py --include-init --no-cpu-limit-check

# Rendered Helm chart in CI (fails the job on errors)
helm template ./chart | kubectl create --dry-run=client -o json -f - \
  | ./resource_requests_audit.py

# JSON output for further processing, never fail
./resource_requests_audit.py --format json --fail-on never workloads.json
```

| Option | Description |
|---|---|
| `file` | kubectl JSON file (default: stdin) |
| `--format table\|json` | output format (default: table) |
| `--fail-on error\|warning\|never` | lowest severity that makes the exit code 1 (default: error) |
| `--no-cpu-limit-check` | do not report missing CPU limits |
| `--include-init` | also audit initContainers |
| `--include-system` | include the kube-* system namespaces |
| `--skip-namespace NS` | skip a namespace (repeatable) |

Exit codes: `0` no findings at or above `--fail-on`, `1` findings, `2` unreadable input.

## Example output

Using [`examples/sample-workloads.json`](examples/sample-workloads.json):

```text
$ ./resource_requests_audit.py examples/sample-workloads.json
NAMESPACE  KIND        NAME            CONTAINER  MISSING         SEVERITY
analytics  CronJob     nightly-report  report     memory-limit    error
analytics  CronJob     nightly-report  report     cpu-limit       warning
payments   Deployment  checkout-api    app        cpu-limit       warning
payments   Deployment  checkout-api    envoy      cpu-request     error
payments   Deployment  checkout-api    envoy      memory-request  error
payments   Deployment  checkout-api    envoy      memory-limit    error
payments   Deployment  checkout-api    envoy      cpu-limit       warning

7 finding(s): 4 error, 3 warning
$ echo $?
1
```

The `redis` StatefulSet sets only limits, so its requests default to them and it is not reported. The `checkout-api` Pod is owned by a ReplicaSet and is covered by the Deployment row, and `aws-node` lives in `kube-system`, which is skipped by default.
