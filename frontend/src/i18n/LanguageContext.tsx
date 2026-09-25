import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { isLanguage, translations } from './translations';
import type { Language, TranslationKey } from './translations';

const storageKey = 'bis-assistant-language';
type LanguageContextValue = { language: Language; setLanguage: (language: Language) => void; t: (key: TranslationKey) => string };
const defaultLanguageContext: LanguageContextValue = { language: 'en', setLanguage: () => undefined, t: (key) => translations.en[key] };
const LanguageContext = createContext<LanguageContextValue>(defaultLanguageContext);

function savedLanguage(): Language {
  try {
    const value = window.localStorage.getItem(storageKey);
    return isLanguage(value) ? value : 'en';
  } catch {
    return 'en';
  }
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState<Language>(savedLanguage);
  useEffect(() => {
    document.documentElement.lang = language;
    try { window.localStorage.setItem(storageKey, language); } catch { /* Storage is optional. */ }
  }, [language]);
  const value = useMemo(() => ({ language, setLanguage, t: (key: TranslationKey) => translations[language][key] }), [language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  return useContext(LanguageContext);
}
