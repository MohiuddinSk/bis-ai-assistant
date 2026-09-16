# Free ngrok demo: Netlify + account-assigned development domain

This is a **demo-only** transport for one laptop. It is not the production scaling design. The existing Cloudflare named-tunnel workflow remains an optional alternative in `docs/SECURE_DEMO_DEPLOYMENT.md`; this guide does not replace or weaken it.

The backend stays bound to `127.0.0.1`. ngrok forwards the exact free development HTTPS domain assigned to the operator's ngrok account. No purchased or owned DNS domain is required.

## Account and local authentication

Create a free ngrok account, install the official ngrok agent, and complete authentication separately with ngrok's local configuration, following ngrok's current account instructions. Do this outside the repository. Never put the credential in a script argument, `.env` file, repository configuration, terminal transcript, or log. The demo scripts never authenticate, read, print, store, or pass an ngrok credential.

Keep ngrok configuration in its normal user-local location, not this checkout. If a credential is exposed, revoke it in the ngrok dashboard, remove the local configuration, and create a replacement before the next demo.

## Discover the assigned domain

In the ngrok dashboard, find the account-assigned free development domain. Copy only its hostname, for example `your-assigned-domain.ngrok-free.dev` or `your-assigned-domain.ngrok-free.app`; do not use a random or agent-generated URL. The free-plan agent selects its assigned development domain automatically. The script starts `ngrok http http://127.0.0.1:8000`, then queries only the local agent API at `http://127.0.0.1:4040/api/tunnels` and verifies the expected HTTPS URL and loopback upstream without displaying agent data.

## Configure Netlify and this shell

Set Netlify's public build variable, then rebuild/deploy the frontend:

```text
VITE_API_BASE_URL=https://your-assigned-domain.ngrok-free.dev
```

In the PowerShell process that will start the demo, set the exact values (the frontend value is an origin, including `https://`):

```powershell
$env:FREE_NGROK_HTTPS_HOSTNAME = "your-assigned-domain.ngrok-free.dev"
$env:FREE_NGROK_FRONTEND_ORIGIN = "https://bis-saarthi-ai-assistant.netlify.app"
```

`FREE_NGROK_FRONTEND_ORIGIN` must be the exact Netlify origin `https://bis-saarthi-ai-assistant.netlify.app`: no wildcard, path, comma list, query, fragment, port, or trailing slash. The start script sets `ALLOWED_ORIGINS` to only that value for the demo container. The assigned ngrok hostname is also exact and must not include a scheme, path, port, query, fragment, or wildcard.

## Start and validate

From the repository root, start with generation disabled (the default):

```powershell
.\deploy\free-ngrok-demo\start.ps1
.\deploy\free-ngrok-demo\check.ps1
```

The check validates local and public legacy/versioned health routes, the public CORS preflight for the exact Netlify origin, legacy and versioned retrieve/chat routes, echoed request IDs, and empty provider-key environment entries. It emits fixed, non-secret reason codes such as `missing-api-hostname`, `cors-origin-mismatch`, and `provider-secret-present` on failure.

For free-tier browser interstitials, public demo probes and the frontend send `ngrok-skip-browser-warning: 1`. The backend CORS allowlist permits that explicit request header only for the configured frontend origin. Loopback probes never send it. A public non-JSON/interstitial reply reports the fixed `public-health-non-json-response` code without exposing its body; a network timeout reports `public-health-network-timeout`.

Generation remains off unless an operator intentionally supplies the existing provider configuration and invokes `start.ps1 -EnableGeneration`. Do not use that option for a public demo unless provider-secret handling has been approved separately.

## Shut down

```powershell
.\deploy\free-ngrok-demo\stop.ps1
```

The workflow records only the PID and start time of the ngrok process it started, in ignored local runtime state. Stop verifies both before stopping it, and stops only the `free-ngrok-demo` Compose project. It never kills other ngrok processes, Docker containers, images, or volumes.

## Limits and operating conditions

Free ngrok development domains, quotas, policy controls, and availability are account/provider controlled; verify the current limits in the ngrok dashboard before a demo. The laptop must remain powered, awake, connected to the internet, and able to run Docker and the locally authenticated ngrok agent. Sleep, shutdown, network changes, agent failure, or exhausted account limits make the public endpoint unavailable. This is not a production availability, scaling, identity, rate-limiting, monitoring, secret-management, or incident-response design.
