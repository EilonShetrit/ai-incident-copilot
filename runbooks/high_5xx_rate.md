# Runbook: High 5xx rate

**Applies to:** any monitor on HTTP 5xx error rate (e.g. `api-gateway 5xx rate > 5%`).

## 1. Confirm and scope
- Check the error rate and request volume for the alerted service over the last 30 minutes.
- Note when the rate first rose above baseline. That time anchors the rest of the investigation.

## 2. Look for a recent change
- List deploys and config changes in the 30 minutes before the rise.
- A deploy that lines up with the rise is the leading suspect. Continue with the
  [deploy regression runbook](deploy_regression.md).

## 3. Follow the errors downstream
- Read the error messages on the alerted service. A gateway returning 502/504 is usually
  reporting a failure from a service it calls, not failing itself.
- Use the service map to walk the dependency chain. Repeat steps 1–3 on each downstream
  service until you find the first one whose errors are not explained by something it calls.

## 4. Rule out the healthy paths
- Check sibling dependencies too. A healthy sibling narrows the blast radius and confirms the
  problem is specific to one path.

## 5. Mitigate
- If a deploy is the cause: roll back first, investigate after.
- If no change explains it: scale the failing service, check its dependencies (DB, cache,
  third-party APIs), and page the owning team.

## 6. Communicate
- Post impact (which endpoints, % of requests failing, since when) and the current hypothesis
  in the incident channel. Update every 15 minutes.
