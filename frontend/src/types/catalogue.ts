export interface CatalogueStandard {
  identifier: string;
  title: string;
  category: string | null;
  edition_year: string | null;
  status: string | null;
  official_url: string;
  retrieved_at: string;
  provenance: string;
  evidence_filename: string | null;
  evidence_page: number | null;
}

export interface CatalogueSearchResponse {
  query: string;
  results: CatalogueStandard[];
  record_count: number;
  last_updated: string | null;
  coverage_note: string;
}
