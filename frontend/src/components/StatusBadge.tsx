import { useLanguage } from '../i18n/LanguageContext';
export function StatusBadge({status}:{status:'ready'|'degraded'|'unavailable'}){const {t}=useLanguage();const label=status==='ready'?t('statusReady'):status==='degraded'?t('statusDegraded'):t('statusUnavailable'); return <span className={`status ${status}`} role="status">{label}</span>}
