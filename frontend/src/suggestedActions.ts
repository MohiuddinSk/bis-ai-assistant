import type { ChatResponse } from './types/chat';

export type SuggestedAction =
  | { kind: 'chat_question'; label: string; question: string }
  | { kind: 'standard_explanation'; label: string; standard: string }
  | { kind: 'open_compliance_wizard'; label: string };

const roadmapLabel = 'Show my complete compliance roadmap';
const standardPattern = /^IS\s+\d+(?:\s+Part\s+\d+)?$/i;
const isStandard = (value: string) => standardPattern.test(value);
const clarificationChoices: Record<string, readonly string[]> = {
  power_type: ['Battery-operated', 'Mains-powered', 'Non-electric'],
  role: ['Manufacturer', 'Importer', 'Artisan'],
  age_group: ['Under 3', '3–8', 'Both age groups'],
  application_stage: ['Researching', 'Preparing a new application', 'Existing licence', 'Scope extension', 'First BIS licence', 'Add to an existing licence'],
  goal: ['Identify applicable standards', 'Apply for a new licence', 'Add a model or series', 'Check an exemption', 'Understand a transition order'],
};

export const builtInSuggestedActions: SuggestedAction[] = [
  { kind: 'chat_question', label: 'Which standard applies to a battery-operated toy?', question: 'Which standard applies to a battery-operated toy?' },
  { kind: 'chat_question', label: 'Are all handmade toys exempt?', question: 'Are all handmade toys exempt?' },
  { kind: 'chat_question', label: 'What documents are required for a new toy series?', question: 'What documents are required for a new toy series?' },
  { kind: 'chat_question', label: 'What does the 2026 transition order do?', question: 'What does the 2026 transition order do?' },
];

function selfContainedQuestion(label: string): SuggestedAction | null {
  if (isStandard(label)) return null;
  return /^(?:what|which|how|when|why|where|can|does|do|is|are|will|should)\b/i.test(label)
    ? { kind: 'chat_question', label, question: label }
    : null;
}

/** Convert legacy server labels using only server-validated structured context. */
export function normalizeSuggestedActions(response: ChatResponse): SuggestedAction[] {
  const context = response.assistant_context;
  const standards = (context?.referenced_standards ?? []).filter(isStandard);
  const singleStandard = standards.length === 1 ? standards[0] : undefined;
  const standardSelection = Boolean(response.needs_clarification && context?.expected_slots.includes('standard_reference'));
  const actions: SuggestedAction[] = [];
  for (const label of response.suggested_replies ?? []) {
    let action: SuggestedAction | null = null;
    if (label === roadmapLabel) action = { kind: 'open_compliance_wizard', label };
    else if (standardSelection && standards.includes(label) && isStandard(label)) action = { kind: 'standard_explanation', label, standard: label };
    else if (response.needs_clarification && context?.expected_slots.some((slot) => clarificationChoices[slot]?.includes(label))) action = { kind: 'chat_question', label, question: label };
    else if (label === 'Explain when this standard applies' && singleStandard) action = { kind: 'chat_question', label, question: `Explain when ${singleStandard} applies.` };
    else if (label === 'Explain this in simpler language' && singleStandard) action = { kind: 'standard_explanation', label, standard: singleStandard };
    else if (label === 'Explain that standard' && singleStandard) action = { kind: 'standard_explanation', label, standard: singleStandard };
    else {
      const comparison = /^Compare it with (IS\s+\d+(?:\s+Part\s+\d+)?)$/i.exec(label);
      if (comparison && singleStandard && isStandard(comparison[1])) action = { kind: 'chat_question', label, question: `Compare ${singleStandard} with ${comparison[1]}.` };
      else action = selfContainedQuestion(label);
    }
    if (action) actions.push(action);
  }
  return actions;
}

export function questionForSuggestedAction(action: SuggestedAction): string | null {
  if (action.kind === 'chat_question') return action.question;
  if (action.kind === 'standard_explanation') return `Explain ${action.standard} in simple words.`;
  return null;
}
