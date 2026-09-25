import { StatusBadge } from './StatusBadge';
import { useLanguage } from '../i18n/LanguageContext';
import { languageNames } from '../i18n/translations';
export function ChatHeader({status}:{status:'ready'|'degraded'|'unavailable'}){const {language,setLanguage,t}=useLanguage();return <header><div><h1>{t('appTitle')}</h1><p>{t('appSubtitle')}</p></div><div><label htmlFor="language">{t('languageLabel')}</label><select id="language" value={language} onChange={event=>setLanguage(event.target.value as typeof language)}>{Object.entries(languageNames).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><StatusBadge status={status}/></div></header>}
