import { useLanguage } from '../i18n/LanguageContext';
import { languageNames } from '../i18n/translations';

/** The health check remains active in App; it is deliberately not public chrome. */
export function ChatHeader({ status }: { status: 'ready' | 'degraded' | 'unavailable' }) {
  const { language, setLanguage, t } = useLanguage();

  return <header>
    <div><h1>BIS Bandhu</h1><p>{t('appSubtitle')}</p></div>
    <div>
      <label htmlFor="language">{t('languageLabel')}</label>
      <select id="language" value={language} onChange={event => setLanguage(event.target.value as typeof language)}>
        {Object.entries(languageNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </div>
    <span className="visually-hidden" role="status" data-health={status} />
  </header>;
}
