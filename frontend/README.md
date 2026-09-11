# BIS AI Assistant frontend

`npm install`, then `npm run dev`. Optional `VITE_API_BASE_URL` changes the API origin; leave it blank to use the local Vite proxy. Run `npm run lint`, `npm run test -- --run`, and `npm run build` before review. No credentials belong in this project.
# Source PDFs

Citation links use `${VITE_API_BASE_URL}/api/documents/<encoded filename>#page=<page>`. The page fragment is handled by the browser PDF viewer and is never sent as a server path.
