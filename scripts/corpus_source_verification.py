"""Fail-closed official-source gate for the incoming corpus (no ingestion)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_OFFICIAL_HOSTS = frozenset({"www.bis.gov.in", "bis.gov.in", "services.bis.gov.in", "lims.bis.gov.in", "dpiit.gov.in", "egazette.nic.in"})

# Each mapping is evidence obtained from an official landing page or direct
# canonical download.  An omitted mapping is intentionally *not* inferred from
# a filename, logo, Drive path, or document title.
OFFICIAL_EVIDENCE = {
    "categories/helmet/IS-4151-Product-Manual helmet.pdf": {
        "url": "https://www.bis.gov.in/wp-content/uploads/2024/12/PM_IS_4151_-Dec-24.pdf",
        "sha256": "bd41710b83fae7a1e159f76cbfdcba6bd632ec220f2caf4ab77032a82a1501f6",
        "match": "no match",
        "authority": "BIS direct official download",
        "scope": "IS 4151 helmet product manual",
        "publication": "December 2024",
        "effective": "Not established by this verification gate",
        "freshness": "current official manual supplied for comparison",
        "decision": "quarantine",
        "reason": "Incoming January 2019, 8-page manual does not byte-match BIS December 2024, 10-page manual.",
        "warning": "Do not retrieve: use the verified current official product manual instead.",
    },
    "categories/jwellery/Guidelines-for-Jewellers.pdf": {
        "url": "https://www.bis.gov.in/wp-content/uploads/2026/07/Guidelines-for-Jewellers.pdf",
        "sha256": "413890d7d28e575f5a57bd5997a6d21ea0c31de5c654425def795a4340d7ca20",
        "match": "exact",
        "authority": "BIS direct official download; Jewellers Registration Scheme page last updated 10 July 2026",
        "scope": "Jewellers Registration Scheme",
        "publication": "2 July 2026 / July 2026 site publication",
        "effective": "Not separately established",
        "freshness": "current at official page update (10 July 2026)",
        "decision": "active",
        "reason": "Incoming SHA-256 exactly matches the canonical BIS download.",
        "warning": "Apply only to the Jewellers Registration Scheme; consult the current BIS page for amendments.",
    },
    "categories/Application Checklist/ApplicationFormV.pdf": {
        "url": "https://www.bis.gov.in/wp-content/uploads/2019/04/Application-Form-V.pdf",
        "sha256": "3d15850b2863091ffe20a18183ca33332ded340c30fe3b6b57c3cf5a499c69a7",
        "match": "exact",
        "authority": "BIS direct official download linked from FMCS How to apply",
        "scope": "FMCS",
        "publication": "April 2019 canonical file; FMCS process page last updated 12 May 2026",
        "effective": "Use only with the current FMCS process page",
        "freshness": "current process page checked 12 May 2026",
        "decision": "active",
        "reason": "Incoming SHA-256 exactly matches the official FMCS form.",
        "warning": "FMCS only — do not generalize this form to domestic Scheme-I applications.",
    },
    "categories/Application Checklist/Checklist_for_Application_for_BIS_Licence.pdf": {
        "url": "https://www.bis.gov.in/wp-content/uploads/2018/08/Checklist_for_Application.pdf",
        "sha256": "b0b16b0a4142fe538a2b142a6752c202b97f1ac4def0ca211024138f442ee104",
        "match": "exact",
        "authority": "BIS direct official download linked from FMCS How to apply",
        "scope": "FMCS",
        "publication": "August 2018 canonical file; FMCS process page last updated 12 May 2026",
        "effective": "Use only with the current FMCS process page",
        "freshness": "current process page checked 12 May 2026",
        "decision": "active",
        "reason": "Incoming SHA-256 exactly matches the official FMCS checklist.",
        "warning": "FMCS only — do not generalize this checklist to domestic Scheme-I applications.",
    },
    "categories/BIS LABS/BIS_Recognised_LAB_Group_1.pdf": {
        "url": "https://lims.bis.gov.in/home/labs/",
        "sha256": None,
        "match": "no match",
        "authority": "BIS LIMS official live recognised-laboratory lookup",
        "scope": "BIS recognised laboratories (dated Group-1 snapshot)",
        "publication": "24 August 2026 visible on incoming snapshot; official live page has no page-level last-updated date",
        "effective": "Snapshot only",
        "freshness": "dated snapshot; live lookup required",
        "decision": "active with freshness warning",
        "reason": "Official live LIMS is authoritative for lookup, but no canonical downloadable snapshot was available for byte comparison.",
        "warning": "Do not recommend a laboratory from this snapshot. Check live LIMS scope and validity first: https://lims.bis.gov.in/home/labs/",
    },
    "categories/BIS LABS/BIS_recognised_lab_Group_2.pdf": {
        "url": "https://lims.bis.gov.in/home/labs/",
        "sha256": None,
        "match": "no match",
        "authority": "BIS LIMS official live recognised-laboratory lookup",
        "scope": "BIS laboratory facilities (dated Group-2 snapshot)",
        "publication": "7 August 2026 visible on incoming snapshot; official live page has no page-level last-updated date",
        "effective": "Snapshot only",
        "freshness": "dated snapshot; live lookup required",
        "decision": "active with freshness warning",
        "reason": "Official live LIMS is authoritative for lookup, but no canonical downloadable snapshot was available for byte comparison.",
        "warning": "Do not recommend a laboratory from this snapshot. Check live LIMS scope and validity first: https://lims.bis.gov.in/home/labs/",
    },
    "categories/Standard Fees/BIS Standrd certification Fees.pdf": {
        "url": "https://www.bis.gov.in/product-certification/product-certification-fee/?lang=en",
        "sha256": None,
        "match": "no match",
        "authority": "BIS Product Certification Fee page (last updated 14 September 2026)",
        "scope": "Scheme-I/product certification marking fees only unless a cited official scheme says otherwise",
        "publication": "Incoming file carries 2026 Gazette material; direct canonical PDF not established",
        "effective": "Not established by byte match",
        "freshness": "time-sensitive; official page lists 2026 amendments",
        "decision": "active with freshness warning",
        "reason": "The official fee page establishes the current lookup location, but not this incoming file as a canonical download.",
        "warning": "State an as-of date and scheme. Never apply an amount to another scheme; check the current official fee page first.",
    },
    "categories/toys/Safety_of_toys.pdf": {
        "url": "https://www.bis.gov.in/wp-content/uploads/2020/09/PM-Toys-v2-Sep2020.pdf",
        "sha256": None,
        "match": "no match",
        "authority": "BIS direct August/September 2020 toy PM available for comparison; later PM-9873 versions exist",
        "scope": "Safety of toys historical summary",
        "publication": "1 September 2020 visible in incoming file",
        "effective": "Historical only",
        "freshness": "superseded/legacy",
        "decision": "historical",
        "reason": "One-page summary is not the official 2020 manual and later PM-9873 versions exist.",
        "warning": "Historical context only; do not use for current compliance conclusions.",
    },
}


def is_allowed_official_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_OFFICIAL_HOSTS


def _fallback(row: dict) -> dict:
    path = row["original_relative_path"]
    classification = row["classification"]
    if path.endswith(".docx"):
        decision, reason = "secondary", "Valid Office container/unsupported extractor does not establish provenance; retain inactive pending primary citations."
    elif classification == "historical/superseded":
        decision, reason = "historical", "Previous version is not eligible for default active retrieval."
    else:
        decision, reason = "secondary", "No exact canonical official download was established; do not use as independent support for compliance claims."
    return {
        "url": None, "sha256": None, "match": "no match", "authority": "No official canonical source verified by this gate",
        "scope": "Unresolved", "publication": "Unresolved", "effective": "Unresolved", "freshness": "unverified",
        "decision": decision, "reason": reason,
        "warning": "Do not use as primary evidence; verify an official canonical source first.",
    }


def build_manifest(review: dict) -> dict:
    records = []
    for row in review["files"]:
        if row["classification"] == "exact duplicate":
            continue
        evidence = OFFICIAL_EVIDENCE.get(row["original_relative_path"], _fallback(row))
        record = {
            "incoming_path": row["original_relative_path"],
            "incoming_sha256": row["sha256"],
            "canonical_official_url": evidence["url"],
            "downloaded_canonical_sha256": evidence["sha256"],
            "match": evidence["match"],
            "authority": evidence["authority"],
            "scheme_product_scope": evidence["scope"],
            "publication_date": evidence["publication"],
            "effective_date": evidence["effective"],
            "freshness_class": evidence["freshness"],
            "decision": evidence["decision"],
            "reason": evidence["reason"],
            "required_runtime_warning": evidence["warning"],
        }
        records.append(record)
    validate_manifest(records)
    return {"scope": "Official-source matching gate only; no ingestion, copying, indexing, or retrieval configuration change.", "records": records,
            "active_approval_list": [record["incoming_path"] for record in records if record["decision"] in {"active", "active with freshness warning"}]}


def validate_manifest(records: list[dict]) -> None:
    for record in records:
        url = record["canonical_official_url"]
        if url is not None and not is_allowed_official_url(url):
            raise ValueError(f"unapproved authority URL: {url}")
        if record["match"] == "exact" and record["incoming_sha256"] != record["downloaded_canonical_sha256"]:
            raise ValueError(f"exact match hash mismatch: {record['incoming_path']}")
        if record["decision"] == "active" and record["match"] != "exact":
            raise ValueError(f"active source requires exact official match: {record['incoming_path']}")
        if record["decision"] == "active with freshness warning" and not record["required_runtime_warning"]:
            raise ValueError(f"freshness warning required: {record['incoming_path']}")
        if record["scheme_product_scope"] == "FMCS" and "FMCS" not in record["required_runtime_warning"]:
            raise ValueError(f"FMCS scope warning required: {record['incoming_path']}")


def write_manifest(manifest: dict, json_path: Path, markdown_path: Path) -> None:
    json_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Corpus v4 official-source manifest", "", manifest["scope"], "", "## Active approvals", ""]
    lines.extend([f"- `{path}`" for path in manifest["active_approval_list"]] or ["- None"])
    lines.extend(["", "## Records", "", "| Incoming file | Match | Decision | Canonical official source |", "| --- | --- | --- | --- |"])
    for record in manifest["records"]:
        lines.append(f"| `{record['incoming_path']}` | {record['match']} | {record['decision']} | {record['canonical_official_url'] or 'Not verified'} |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, default=ROOT / "docs" / "incoming_drive_2026-09-28_review.json")
    parser.add_argument("--json", type=Path, default=ROOT / "docs" / "corpus_v4_source_manifest.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "docs" / "corpus_v4_source_manifest.md")
    args = parser.parse_args()
    manifest = build_manifest(json.loads(args.review.read_text(encoding="utf-8")))
    write_manifest(manifest, args.json, args.markdown)


if __name__ == "__main__":
    main()
