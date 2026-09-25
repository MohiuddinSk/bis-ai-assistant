import type { SuggestedAction } from '../suggestedActions';
import { useLanguage } from '../i18n/LanguageContext';
export function SuggestedQuestions({actions,onSelect,busy}:{actions:SuggestedAction[];onSelect:(action:SuggestedAction)=>void;busy:boolean}){const {t}=useLanguage();return <section className="suggestions"><h2>{t('suggestedQuestions')}</h2>{actions.map(action=><button key={action.label} disabled={busy} onClick={()=>onSelect(action)}>{action.label}</button>)}</section>}
