# devops-toolkit

Small, practical tools and snippets for running platforms on AWS and Kubernetes: cluster hygiene checks, Terraform patterns, CI/CD templates, observability and automation scripts.

Each entry is self-contained, has its own README with usage, and is tested before it lands here.

| Area | Entry | What it does |
|------|-------|--------------|
| Kubernetes | [pdb-coverage](kubernetes/pdb-coverage) | Lists Deployments/StatefulSets with no PodDisruptionBudget, so node drains during EKS upgrades or Karpenter consolidation can't take a whole service down. |
| Kubernetes | [resource-requests-audit](kubernetes/resource-requests-audit) | Flags containers missing CPU/memory requests or limits, the usual cause of bad bin-packing, Karpenter mis-sizing and OOM kills on shared nodes. |

## Layout

```
kubernetes/   cluster checks, manifests, Helm snippets
terraform/    modules and patterns
ci/           GitLab CI / GitHub Actions templates
observability/ Prometheus rules, Grafana dashboards, alerting
scripts/      general automation (Python, Bash, Go)
```

## Author

Arjun Kanojia, DevOps / Platform Engineer (AWS SA Pro, CKA) · [arjunkanojia.com](https://arjunkanojia.com) · [LinkedIn](https://www.linkedin.com/in/arjunkanojia)

MIT licensed.
