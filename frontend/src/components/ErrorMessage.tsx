import { useLanguage } from '../i18n/LanguageContext';
export function ErrorMessage({message,onRetry}:{message:string;onRetry:()=>void}){const {t}=useLanguage();return <div className="error" role="alert">{message} <button onClick={onRetry}>{t('retry')}</button></div>}
