# Runbook: DNS resolution failure

**Applies to:** errors like `lookup <host>: i/o timeout`, `no such host` or `server misbehaving`,
or calls stuck at the DNS timeout (about 5 seconds).

## 1. Scope it by name, not by service
- List which hostnames fail. If only external names fail and in-cluster names resolve, the
  problem is in forwarding to upstream resolvers, not in the cluster DNS as a whole.
- Errors can start a few minutes after the change, once cached records expire (TTL).

## 2. Look for a DNS or network change
- Check deploys for the DNS service itself (CoreDNS config: forwarders, stub zones, plugins)
  and for network policy or security group changes.
- Read the resolver logs. `no healthy upstreams` or upstream timeouts point at the forwarders.

## 3. Mitigate
- Roll back the DNS config change first. This restores every affected service at once.
- If there is no change to roll back, point forwarders at known-good resolvers and page the
  network owner.

## 4. Verify and follow up
- Resolve the failing hostname from a pod. The timeouts and the 502/504s at callers should stop
  within a minute or two.
- Add a synthetic check that resolves each critical external hostname.
