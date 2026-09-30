# BIS public directory metadata snapshot

This snapshot contains metadata, not the text of Indian Standards or a live
laboratory-recognition feed. The published-standards XLSX was downloaded with
the public **Download** control on the [BIS Published Standards List](https://standards.bis.gov.in/website/published-standards/published-standards-list?selectedType=7&totalRow=1).
The 39 public LIMS HTML snapshots were obtained by following the directory's
own pagination and a bounded set of ten [IS-number searches](https://lims.bis.gov.in/home/search_is_number/).
`manifest.json` records the exact URLs, UTC retrieval times, SHA-256 hashes,
byte lengths and parser version. The Excel's “Date of Publish” is stored as a
*source* publication date, separately from retrieval time. Absent source dates
stay absent.

On 2026-09-30, the import accepted 23,813 distinct published-standards rows,
429 laboratory-directory rows plus 12 search-only identities, and 362 distinct
lab-to-standard search rows. Of the latter, 342 had a parseable top-level listed
amount. This is not a reconciled count of every active BIS standard, laboratory,
or laboratory test scope. In particular, the LIMS search column “Validity Date”
does not identify itself as a per-IS scope expiry; it is retained separately as
`search_validity_date`. No imported record asserts current recognition.

## Reproduce or refresh

Install the importer dependencies in a project Python environment:

```powershell
python -m pip install -r scripts/requirements-directory.txt
```

Open the official Published Standards List in a browser, use **Download**, and
save its public XLSX. Use the URL from the actual download (the temporary object
URL changes). An authorized CSV or JSON metadata export may also be used when
it has `Standard Number`/`Title` columns or `identifier`/`title` keys. Optional
columns are `Date of Publish`, `Type of Standard`, and `official_detail_url`;
the latter must be an official BIS HTTPS host. No technical description or
applicability fact is derived from these fields.

```powershell
python scripts/sync_bis_directories.py acquire --standards-file C:\path\to\official-export.xlsx --standards-url 'https://URL-returned-by-BIS-download'
python scripts/sync_bis_directories.py import
python scripts/sync_bis_directories.py validate
```

For a fresh LIMS snapshot, use the same acquire command with `--refresh`,
then `import` and `validate`. Without `--refresh`, verified raw downloads are
reused from the manifest as a resume cache. The importer uses bounded pages,
one-second request spacing, three retries with backoff and a 20 MB response
limit. A failed acquisition leaves the prior manifest and normalized datasets
in place. Review `import_report.json` for source, accepted and rejected rows and
reasons. Do not promote a malformed or unexpectedly small import.

`standards.json.gz` and `laboratories.json.gz` are the normalized runtime
datasets copied into the backend image. The raw source files and Excel are
excluded from the Docker build context. Backend startup does not re-download
anything. The three earlier individually verified standards remain in
`backend/catalogue_records.json` and retain their stronger provenance
when merged with an identical export identity. Metadata-only records do not
give the Assistant evidence for technical requirements.

## Coverage limitations

The public Excel has no per-record detail URL, withdrawal status, amendment,
reaffirmation date, or technical text column. The importer therefore links
these records to the official published-standards listing and leaves those
fields unset. LIMS coverage includes all 22 pages of the public lab-directory
view at acquisition time, but individual testing capabilities come only from
ten selected IS-number searches (17 pages). Those searches do not establish
all capabilities for any lab. Listed charges are source-row observations,
excluding taxes when the source says so, not a total quotation. Verify current
scope, validity and price with BIS LIMS and the laboratory before acting.
