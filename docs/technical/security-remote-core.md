## Remote Core Security (Auth/TLS Guidance)

This guide defines the **minimum security posture** when running Core (`core/api.py`) outside localhost.

---

## Threat Model (What Changes in Remote Mode)

Local mode assumes trusted loopback networking. Remote Core introduces:

- traffic exposure over non-local networks,
- replay/abuse risk on unauthenticated endpoints,
- accidental API key leakage in logs or intermediary hops.

For that reason, Core should be treated as a **private service behind an authenticated gateway**.

---

## Required Controls

### 1) TLS Everywhere

- Terminate TLS at your ingress/reverse proxy (Nginx, Traefik, API Gateway, etc.).
- Enforce HTTPS only (redirect HTTP -> HTTPS or disable plain HTTP listener).
- Use modern TLS configuration (TLS 1.2+; prefer TLS 1.3 where available).

### 2) Strong Service-to-Service Authentication

Use one of:

- mTLS between Platform and Core, **or**
- signed service token (short-lived JWT/OIDC token) validated at gateway.

Do **not** expose Core publicly without one of the above.

### 3) Network Segmentation

- Bind Core to private network interfaces only.
- Restrict inbound access to Platform hosts (security group / firewall allowlist).
- Block direct internet access to Core runtime if possible.

### 4) Secret Handling

- Do not store provider keys in source control.
- Keep provider keys in secure secret stores / environment variables.
- Redact secrets from logs, traces, and error payloads.

### 5) Observability + Abuse Detection

- Log request IDs and status codes (without sensitive payload contents).
- Track 4xx/5xx spikes and repeated auth failures.
- Add per-caller rate limiting at gateway layer when exposed beyond localhost.

---

## Recommended Deployment Pattern

```
Client -> Platform (local runtime) -> TLS + Auth Gateway -> Core API
```

- Clients never call Core directly.
- Platform remains the orchestration boundary and failure-handling surface.
- Gateway enforces auth, TLS, and policy controls before traffic reaches Core.

---

## Rollback/Safety Notes

- If remote mode has operational issues, revert Platform Core base URL to localhost-only deployment.
- Keep auth controls in place before re-enabling remote endpoint exposure.
