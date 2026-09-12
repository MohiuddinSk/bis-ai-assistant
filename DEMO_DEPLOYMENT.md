# Netlify + Cloudflare Quick Tunnel demo

The frontend is deployed to Netlify. FastAPI remains on the demo computer and is exposed temporarily through a Cloudflare Quick Tunnel. Quick Tunnel URLs change whenever the tunnel restarts, so update both allowed origins and the Netlify frontend variable for each demo session.

## 1. Start the backend

Use two PowerShell windows from the repository root. Keep the Groq key only in the backend process environment:

```powershell
$env:PYTHONUTF8 = "1"
$env:GROQ_API_KEY = "<set-this-only-in-this-PowerShell-process>"
$env:ALLOWED_ORIGINS = "https://example-site.netlify.app"
.\venv311\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Never place `GROQ_API_KEY` in Netlify, `netlify.toml`, frontend environment files, or committed files.

## 2. Start the Quick Tunnel

Install the official `cloudflared` binary separately, then run:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Copy the generated `https://<random>.trycloudflare.com` URL. Confirm the tunnel with:

```powershell
Invoke-RestMethod "https://<random>.trycloudflare.com/health"
```

## 3. Configure and deploy Netlify

In the Netlify site settings, set only this public frontend build variable:

```text
VITE_API_BASE_URL=https://<random>.trycloudflare.com
```

Do not add the Groq key to Netlify. Deploy from the repository root; `netlify.toml` builds `frontend` with `npm run build`, publishes `frontend/dist`, and provides the SPA fallback.

If the Netlify hostname changes, restart the backend PowerShell process with `ALLOWED_ORIGINS` set to the exact new `https://...netlify.app` origin. Do not use a wildcard.

## 4. Smoke test

Open the Netlify site, confirm the status becomes Ready, submit a grounded chat question, complete the Compliance Wizard, expand a citation, and open its source PDF. Browser PDF fragments such as `#page=4` stay client-side.

Known limitation: Quick Tunnels are temporary demo transports, not a production hosting or availability solution.
