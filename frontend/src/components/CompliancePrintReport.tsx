import { forwardRef } from 'react';
import type { ChatResponse } from '../types/chat';
import type { ComplianceProfile } from '../types/compliance';
import { useLanguage } from '../i18n/LanguageContext';
import { CompliancePassportContent } from './CompliancePassport';

/** The iframe receives this exact same finalized passport content as the screen. */
export const CompliancePrintReport = forwardRef<HTMLElement, { profile: ComplianceProfile; guidance: ChatResponse; generatedAt: Date }>(function CompliancePrintReport({ profile, guidance, generatedAt }, ref) {
  const { t } = useLanguage();
  return <article ref={ref} className="compliance-print-report print-only" aria-label={t('printReportAria')}>
    <CompliancePassportContent profile={profile} guidance={guidance} generatedAt={generatedAt} />
  </article>;
});
