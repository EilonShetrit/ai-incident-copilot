# Runbook: Log pipeline lag

**Applies to:** a log ingestion lag alert, missing recent logs, or log-based monitors that went
quiet while traffic looks normal.

## 1. Check whether users are affected
- Look at metrics, not logs: request counts, error rates and latency come from a separate
  pipeline. If they are normal, this is a visibility incident, not an outage.
- Until the lag clears, log searches undercount. Do not conclude "no errors" from logs alone.

## 2. Find what flooded the pipeline
- Check the shipper's own logs: paused inputs, full buffers, retries, HTTP 429 from the log store.
- Look for a jump in log volume and the change behind it: a debug log level, a new noisy log
  line, or an error loop. The shipper logs often name the container writing the most.

## 3. Mitigate
- Cut the volume at the source: set the log level back to INFO or roll back the noisy change.
- If the log store is the bottleneck, scale it or raise its bulk queue. Let the backlog drain.

## 4. Follow up
- Cap log volume per container in the shipper, and alert on volume per service.
- Prefer a temporary debug flag scoped to a few requests over a service-wide debug level.
