# Eval: 5xx_after_deploy

2026-10-26 16:46 UTC · model `claude-opus-5-5` · 3 runs · **89%** of checks passed

| Check | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| `root_cause_service` | ✅ | ✅ | ✅ |
| `root_cause_explained` | ✅ | ✅ | ✅ |
| `impacted_services` | ✅ | ✅ | ✅ |
| `healthy_ruled_out` | ✅ | ✅ | ✅ |
| `mitigation_first` | ❌ | ❌ | ✅ |
| `evidence_backed` | ✅ | ✅ | ✅ |
| Turns | 6 | 6 | 5 |
| Tool calls | 15 | 15 | 15 |
| Seconds | 47.7 | 50.0 | 44.1 |

## Failures
- Run 1, `mitigation_first`: first step: 'Roll payments back from v2.4.0 to v2.3.0 now (deploy_regression runbook step 3). Do not wait for a fix-forward.'
- Run 2, `mitigation_first`: first step: 'Roll payments back from v2.4.0 to v2.3.0 now, as the deploy_regression runbook says. Do not wait for a fix-forward.'
