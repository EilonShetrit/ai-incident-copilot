# Runbook: Memory pressure and OOM kills

**Applies to:** containers restarting with `OOMKilled`, memory near the limit, or 502/503 at
callers that line up with restarts.

## 1. Confirm
- Check the service's memory against its limit and its restart count over the last hour.
- A steady climb ending in restarts is a leak. A sudden jump is a load or payload problem.

## 2. Find when the climb started
- The deploy that introduced a leak is often **not** the latest one: memory can take an hour
  or more to fill. Match the start of the climb, not the start of the errors, to the deploy list.
- Look for startup or config log lines from that version (caches, buffers, pool sizes).

## 3. Mitigate
- If a deploy started the climb: roll it back.
- To buy time first: scale out or raise the memory limit, and restart pods before they hit it.
- Do not just raise the limit and walk away: a leak fills any limit.

## 4. Follow up
- Ask the owning team for a heap profile from the leaking version.
- Add an alert on memory usage above 85% of the limit, so the next leak pages before the OOMs.
