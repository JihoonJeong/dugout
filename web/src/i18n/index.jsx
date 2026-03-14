import { createContext, useContext, useState, useCallback } from 'react';
import en from './en.json';
import ko from './ko.json';
import ja from './ja.json';

const messages = { en, ko, ja };

function detectLocale() {
  const saved = localStorage.getItem('dugout_lang');
  if (saved && messages[saved]) return saved;

  const browserLang = navigator.language?.slice(0, 2) || 'en';
  if (messages[browserLang]) return browserLang;
  return 'en';
}

function get(obj, path) {
  return path.split('.').reduce((o, k) => o?.[k], obj);
}

const LanguageContext = createContext();

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(detectLocale);

  const setLang = useCallback((l) => {
    if (messages[l]) {
      setLangState(l);
      localStorage.setItem('dugout_lang', l);
    }
  }, []);

  const t = useCallback((key, params) => {
    let str = get(messages[lang], key) || get(messages.en, key) || key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        str = str.replace(`{${k}}`, v);
      }
    }
    return str;
  }, [lang]);

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
  return ctx;
}

export const SUPPORTED_LANGS = [
  { code: 'en', label: 'EN' },
  { code: 'ko', label: '한국어' },
  { code: 'ja', label: '日本語' },
];
