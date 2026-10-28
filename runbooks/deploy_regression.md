# Runbook: Deploy regression

**Applies to:** errors or latency that start within minutes of a deploy.

## 1. Correlate
- Compare the deploy time with the first error. A gap of a few minutes is normal: problems
  often appear only once traffic reaches the new instances or a resource (connections,
  memory, threads) runs out.
- Confirm that errors come from the **new version**: group the failing service's errors by
  `version`.

## 2. Find what changed
- Read the deploy's change description and commit.
- Look for startup log lines from the new version (config loaded, pool sizes, feature flags)
  and compare them with the previous version.

## 3. Roll back
- Roll back to the last known good version. Do not wait for a fix-forward while users are
  affected.
- Verify recovery: within ~5 minutes of the rollback, each status code the incident raised
  (for example 503 at the origin, 502/504 at its callers) falls back to baseline.

## 4. Follow up
- Open a ticket for the owning team with the evidence: deploy, first error, error messages,
  and the config diff.
- Add a pre-deploy check or alert that would have caught it (e.g. connection pool saturation).
