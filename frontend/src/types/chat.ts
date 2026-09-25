export type GenerationMode = 'llm' | 'extractive_fallback' | 'abstention' | 'clarification';
export interface Citation { citation_id:string; source_filename:string|null; page_start:number|null; page_end:number|null; chunk_id:string; excerpt:string }
export type Audience = 'general' | 'manufacturer' | 'consumer';
export type ResponseLanguage = 'en' | 'hi' | 'mr';
export interface AnswerSection { type:'direct_answer'|'explanation'|'next_steps'|'important'|'clarification'; title:string; content?:string|null; items:string[]; citation_ids:string[] }
export interface ClarificationContext { original_question:string }
export type ClarificationSlot='role'|'product_description'|'product_scope'|'power_type'|'age_group'|'application_stage'|'goal'|'standard_reference';
export interface AssistantContext { original_question?:string|null; expected_slots:ClarificationSlot[]; role?:'manufacturer'|'importer'|'artisan'|'consumer'|'not_sure'|null; product_description?:string|null; power_type?:'battery_operated'|'mains_electric'|'non_electric'|'electric_unspecified'|'not_sure'|null; age_group?:'under_3'|'3_to_8'|'over_8'|'multiple'|'not_sure'|null; application_stage?:'researching'|'preparing_application'|'existing_licence'|'scope_extension'|'not_sure'|null; current_goal?:'identify_standards'|'new_licence'|'add_new_series'|'check_exemption'|'understand_transition'|'complete_roadmap'|'explain_standard'|'not_sure'|null; referenced_standards?:string[] }
export interface ChatResponse { answer:string; grounded:boolean; insufficient_evidence:boolean; needs_clarification?:boolean; evidence_count:number; citations:Citation[]; model:string|null; generation_mode:GenerationMode; disclaimer:string; answer_sections?:AnswerSection[]; suggested_replies?:string[]; assistant_context?:AssistantContext|null }
export interface HealthResponse { status:string; service:string; collection_count:number|null; detail:string|null }
