# Secure SIH demo deployment: Netlify + Cloudflare named tunnel

This is a **demo-only** deployment transport. It is not the production architecture, a BIS/NIC approval, a security certification, or an availability commitment. The backend remains on the demo machine in Docker Compose and is reachable publicly only through a Cloudflare **named tunnel**. Do not use a Quick Tunnel.

The real frontend hostname, API hostname, tunnel name, and local Cloudflare configuration location are deployment decisions. They are intentionally required through environment variables; this repository supplies no placeholders, credentials, tokens, certificates, generated tunnel configuration, or machine-specific paths.

## 1. Authenticate Cloudflare

On the demo operator's computer, install the official `cloudflared` binary and authenticate with an account allowed to manage the intended Cloudflare zone:

```powershell
cloudflared tunnel login
```

Complete the browser authorization. The resulting certificate and all Cloudflare credentials are local secrets: keep them outside this repository and never paste them into a terminal transcript, issue, commit, `.env` file, script, or log.

## 2. Create the named tunnel

Choose an approved, stable tunnel name and create it once:

```powershell
cloudflared tunnel create <approved-tunnel-name>
```

Create a local Cloudflare configuration outside the repository. It must identify that named tunnel, reference its locally stored credential file, and use a narrow ingress rule that sends the approved API hostname to `http://127.0.0.1:8000`; include a final catch-all `http_status:404` rule. Do not put the configuration under this repository. If a configuration is accidentally created in `.cloudflared/`, it is ignored by Git, but move it outside the checkout before continuing.

## 3. Route DNS hostname

Create the stable API DNS route for the named tunnel, using the same approved API hostname:

```powershell
cloudflared tunnel route dns <approved-tunnel-name> <approved-api-hostname>
```

Verify it in the Cloudflare dashboard. Configure the tunnel's public hostname/ingress only for that exact hostname and local service. Do not create a broad wildcard route. This DNS action, the tunnel name, and the hostname are operator-controlled decisions.

## 4. Start the backend and tunnel

Set the required values in the current PowerShell process. The config path is local-only and must not be committed.

```powershell
$env:SIH_FRONTEND_HOSTNAME = "<approved-netlify-hostname>"
$env:SIH_API_HOSTNAME = "<approved-api-hostname>"
$env:SIH_TUNNEL_NAME = "<approved-tunnel-name>"
$env:SIH_CLOUDFLARED_CONFIG = "<local-config-path>"
.\deploy\start-secure-sih-demo.ps1
```

The script starts the existing `compose.yaml` backend as the isolated `sih-secure-demo` project. Its published port is bound to `127.0.0.1` only, and the tunnel configuration must target that loopback address. The script starts `cloudflared tunnel run <name>` without supplying or displaying a token. It neither authenticates nor changes Cloudflare resources.

Generation is disabled by default, and provider keys are cleared for that run. Enable it only after deliberately supplying the appropriate provider configuration and secret in the current process:

```powershell
.\deploy\start-secure-sih-demo.ps1 -EnableGeneration
```

For `groq`, that requires `LLM_PROVIDER=groq` and `GROQ_API_KEY`; for `openai_compatible`, it requires `LLM_PROVIDER=openai_compatible` and `LLM_API_KEY` (plus the existing provider safety settings). Never print those values.

## 5. Configure Netlify

In Netlify, set the frontend build environment variable to the stable API origin exactly, with no trailing slash:

```text
VITE_API_BASE_URL=https://<approved-api-hostname>
```

Rebuild/redeploy the frontend through Netlify after changing it. Do not use a `trycloudflare.com` URL.

## 6. Configure ALLOWED_ORIGINS

The start script sets `ALLOWED_ORIGINS` for Compose to exactly `https://$SIH_FRONTEND_HOSTNAME`. Set `SIH_FRONTEND_HOSTNAME` to the actual Netlify hostname only—without scheme, slash, path, wildcard, or comma-separated alternatives. This keeps backend CORS narrow for the frontend URL.

## 7. Configure Cloudflare rate limiting

Before a public demo, create a Cloudflare WAF custom rate-limit rule scoped to the exact API hostname. Choose a conservative per-IP threshold appropriate for the audience, include the API paths that need protection, and use a short mitigation duration. Keep health monitoring viable by explicitly deciding whether `/api/v1/health` is excluded. Review Cloudflare's current dashboard and plan requirements with the zone administrator; thresholds and action mode are operational decisions, so this repository does not guess them.

## 8. Validate

Run local and named-tunnel health checks after the tunnel and Netlify configuration are live:

```powershell
.\deploy\check-secure-sih-demo.ps1
```

It checks `http://127.0.0.1:8000/api/v1/health` and `https://$SIH_API_HOSTNAME/api/v1/health` without printing environment values. Confirm in a browser that the Netlify frontend can make an allowed request. Also run the repository validation commands before the demo:

```powershell
python -m unittest discover -v
.\scripts\test_real_index.ps1
.\scripts\test_container.ps1
git diff --check
```

## 9. Shut down

Stop only the isolated demo Compose project and the tunnel process PID recorded by this demo:

```powershell
.\deploy\stop-secure-sih-demo.ps1
```

It does not prune Docker resources, delete images or volumes, or target any other Compose project. Remove the DNS route or disable the public hostname in Cloudflare when the demo ends.

## 10. Revoke credentials and roll back

If a Cloudflare credential, tunnel configuration, or provider secret may have been exposed, revoke or rotate it immediately in its provider console; remove the named tunnel and its DNS route only after confirming they are the demo resources. Roll back the demo by stopping it, removing the exact demo hostname route, and reverting the Netlify `VITE_API_BASE_URL` to its previous approved value. Do not use repository history to store replacement secrets.

## 11. Production boundary

This named-tunnel workflow is intentionally limited to a single demo machine and is **not** a production deployment design. A production system needs approved hosting, identity and access controls, managed secrets, observability, data lifecycle controls, backups, capacity planning, incident response, and formal security review.
