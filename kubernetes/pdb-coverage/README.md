# pdb-coverage

Finds multi-replica Deployments and StatefulSets that no PodDisruptionBudget protects.

Why it matters: node drains happen all the time on EKS (version upgrades, Karpenter consolidation, Spot interruptions). Without a PDB, the eviction API is free to remove every pod of a service at once.

## Usage

```bash
kubectl get deploy,sts,pdb -A -o json | python3 pdb_coverage.py
python3 pdb_coverage.py cluster.json --min-replicas 1
```

Output:

```
NAMESPACE            KIND         NAME                                     REPLICAS
prod                 Deployment   worker                                   2

1 workload(s) without a PodDisruptionBudget.
```

Exit code is `1` when gaps are found, so you can run it as a CI check against a cluster or rendered manifests.

Supports `matchLabels` and `matchExpressions` (`In`, `NotIn`, `Exists`, `DoesNotExist`). Python 3 standard library only.
