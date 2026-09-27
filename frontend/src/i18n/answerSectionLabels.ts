import type { AnswerSection } from '../types/chat';
import type { TranslationKey } from './translations';

export type JourneyCategory = 'standards' | 'summary' | 'checklist' | 'important';

const sectionHeadingKeys = {
  clarification: 'sectionSummary',
  direct_answer: 'sectionSummary',
  explanation: 'sectionExplanation',
  next_steps: 'sectionNextSteps',
  important: 'sectionImportant',
} as const satisfies Record<AnswerSection['type'], TranslationKey>;

const categoryHeadingKeys = {
  standards: 'journeyApplicable',
  summary: 'sectionSummary',
  checklist: 'journeyChecklist',
  important: 'sectionImportant',
} as const satisfies Record<JourneyCategory, TranslationKey>;

export function journeyCategoryFor(section: AnswerSection): JourneyCategory {
  if (section.type === 'direct_answer') return 'standards';
  if (section.type === 'next_steps') return 'checklist';
  if (section.type === 'important') return 'important';
  return 'summary';
}

export function sectionHeadingKey(section: AnswerSection): TranslationKey {
  return sectionHeadingKeys[section.type];
}

export function journeyCategoryHeadingKey(category: JourneyCategory): TranslationKey {
  return categoryHeadingKeys[category];
}
