import { useLanguage } from '../i18n/LanguageContext';
export function LoadingMessage(){const {t}=useLanguage();return <p className="loading" aria-live="polite">{t('loading')}</p>}
