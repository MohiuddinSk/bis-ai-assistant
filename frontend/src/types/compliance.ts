import type { Audience, ChatResponse } from './chat';
export type Role='manufacturer'|'importer'|'artisan'|'consumer'|'not_sure'; export type PowerType='battery_operated'|'mains_electric'|'non_electric'|'not_sure'; export type AgeGroup='under_3'|'3_to_8'|'over_8'|'multiple'|'not_sure'; export type Goal='identify_standards'|'new_licence'|'add_new_series'|'check_exemption'|'understand_transition'|'not_sure'; export type Stage='researching'|'preparing_application'|'existing_licence'|'scope_extension'|'not_sure';
export interface ComplianceProfile {role:Role;product_description:string;power_type:PowerType;intended_age_group:AgeGroup;goal:Goal;application_stage:Stage;additional_context:string|null}
export interface ComplianceGuideResponse {profile:ComplianceProfile;guidance:ChatResponse}
export const audienceForRole=(role:Role):Audience=>role==='consumer'?'consumer':'manufacturer';
