# BIS Bandhu screening walkthrough (locally observed 29 September 2026)

These are example **questions**, not stored answers. Select one on Home, review the editable text, then choose **Ask Bandhu**. Both go through the existing manufacturer `/api/chat` request. Recheck the response before recording because retrieval and source availability may change.

| Question | Observed live response | Observed citations | Recording caveat |
| --- | --- | --- | --- |
| Which standard applies to a battery-operated toy? | Grounded, extractive fallback. It identified IS 15644 as primary for the electric-toy context and cited additional IS 9873 parts only where applicable. | S3, `product_manual_2026.pdf` p. 4; S2, same PDF p. 3. | This is not a universal determination for every toy. Show the cited source and applicability wording. The PDF action opened a local blob URL ending in `#page=4`; the browser PDF viewer page indicator could not be inspected in the automated browser. |
| What documents are required for a new toy series? | Grounded, extractive fallback. It gave a **partial** checklist: new-series declaration, model/age details, and fee declaration. | S3 and S4, `product_manual_2026.pdf` p. 58; S5, same PDF p. 59. | Do not describe this as a complete application package. Confirm current requirements with BIS before submission. |

Manufacturer Wizard profile exercised live: battery-operated toy car for children aged 3–8; power **Battery-operated**; age **3 to 8**; stage **Researching**; goal **Identify applicable standards**. It produced a grounded result and an informational Compliance Passport with S3 p. 4 and S2 p. 3. The Passport is **not a BIS certificate**.

The locally verified catalogue contains **three distinct metadata records** in this working tree: IS 4151:2015 (helmet), IS 15644:2006 (electric toys), and IS 9873 Part 1:2019 (toy mechanical/physical safety). Their official source URLs and provenance are in `backend/catalogue_records.json`. Catalogue metadata does not itself establish product applicability or provide the standard's technical text. The already-running Docker/ngrok backend image still reports its previous single record until it is rebuilt; this task does **not** deploy it. A separate local backend on port 8010 served all three records for validation.

For an unrelated pressure-cooker question, the revised working-tree backend returns an uncited, toy-scope limitation rather than a toy-power clarification. The running Docker image still has the old wording until rebuilt. Use the official BIS standards catalogue for broader discovery; BIS Bandhu does not list every Indian Standard.
