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
  part?: string | null;
  section?: string | null;
  source_publication_date?: string | null;
  official_detail_url?: string | null;
  source_row?: number | null;
}

export interface CatalogueSearchResponse {
  query: string;
  results: CatalogueStandard[];
  record_count: number;
  last_updated: string | null;
  coverage_note: string;
  total_matches: number;
  page: number;
  page_size: number;
  categories: string[];
}

export interface Laboratory {
  id: string;
  code: string | null;
  name: string;
  location: string | null;
  state: string | null;
  official_url: string;
  directory_valid_until: string | null;
  recognition_status: string | null;
  lab_type: string | null;
  retrieved_at: string;
  provenance: string;
}

export interface LaboratoryCapability {
  id: string;
  laboratory_id: string;
  standard_identifier: string;
  product_title: string | null;
  grade_type: string | null;
  testing_facility: string | null;
  exclusions: string | null;
  scope_valid_until: string | null;
  search_validity_date: string | null;
  charge_amount: string | null;
  charge_currency: string | null;
  charge_basis: string | null;
  tax_treatment: string | null;
  charge_note: string | null;
  effective_date: string | null;
  remarks: string | null;
  source_url: string;
  retrieved_at: string;
  provenance: string;
}

export interface LaboratoryResult {
  laboratory: Laboratory;
  capabilities: LaboratoryCapability[];
}

export interface LaboratorySearchResponse {
  query: string;
  results: LaboratoryResult[];
  laboratory_count: number;
  capability_count: number;
  total_matches: number;
  page: number;
  page_size: number;
  last_updated: string | null;
  coverage_note: string;
}
