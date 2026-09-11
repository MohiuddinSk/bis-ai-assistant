export type GenerationMode = 'llm' | 'extractive_fallback' | 'abstention';
export interface Citation { citation_id:string; source_filename:string|null; page_start:number|null; page_end:number|null; chunk_id:string; excerpt:string }
export interface ChatResponse { answer:string; grounded:boolean; insufficient_evidence:boolean; evidence_count:number; citations:Citation[]; model:string|null; generation_mode:GenerationMode; disclaimer:string }
export interface HealthResponse { status:string; service:string; collection_count:number|null; detail:string|null }
