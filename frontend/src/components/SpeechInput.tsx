import { useEffect, useRef, useState } from 'react';
import { useLanguage } from '../i18n/LanguageContext';

type SpeechResult = { isFinal: boolean; 0: { transcript: string } };
type SpeechEvent = { resultIndex: number; results: ArrayLike<SpeechResult> };
type SpeechErrorEvent = { error: string };
type BrowserRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechEvent) => void) | null;
  onerror: ((event: SpeechErrorEvent) => void) | null;
  start: () => void;
  stop: () => void;
};

type BrowserRecognitionConstructor = new () => BrowserRecognition;
type SpeechWindow = Window & { SpeechRecognition?: BrowserRecognitionConstructor; webkitSpeechRecognition?: BrowserRecognitionConstructor };

const locales = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN', ta: 'ta-IN', bn: 'bn-IN' } as const;

export function SpeechInput({ value, onTranscript, disabled = false }: { value: string; onTranscript: (value: string) => void; disabled?: boolean }) {
  const { language, t } = useLanguage();
  const recognition = useRef<BrowserRecognition | null>(null);
  const mounted = useRef(true);
  const draft = useRef(value);
  const [listening, setListening] = useState(false);
  const [status, setStatus] = useState(t('speechSpeakNow'));

  const stop = () => {
    recognition.current?.stop();
  };

  useEffect(() => {
    draft.current = value;
  }, [value]);

  useEffect(() => {
    stop();
    if (mounted.current) {
      setListening(false);
      setStatus(t('speechSpeakNow'));
    }
  }, [language, t]);

  useEffect(() => () => {
    mounted.current = false;
    recognition.current?.stop();
    recognition.current = null;
  }, []);

  const start = () => {
    if (disabled || recognition.current) return;
    const SpeechRecognition = (window as SpeechWindow).SpeechRecognition ?? (window as SpeechWindow).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setStatus(t('speechUnsupported'));
      return;
    }

    const instance = new SpeechRecognition();
    recognition.current = instance;
    instance.lang = locales[language];
    instance.continuous = false;
    instance.interimResults = false;
    instance.onstart = () => {
      if (!mounted.current) return;
      setListening(true);
      setStatus(t('speechListening'));
    };
    instance.onresult = event => {
      const transcript = Array.from(event.results)
        .slice(event.resultIndex)
        .filter(result => result.isFinal)
        .map(result => result[0].transcript.trim())
        .filter(Boolean)
        .join(' ');
      if (!transcript || !mounted.current) return;
      const separator = draft.current.trim() ? ' ' : '';
      onTranscript(`${draft.current}${separator}${transcript}`.slice(0, 1000));
    };
    instance.onerror = event => {
      if (!mounted.current) return;
      const key = event.error === 'not-allowed' || event.error === 'service-not-allowed'
        ? 'speechPermissionDenied'
        : event.error === 'no-speech'
          ? 'speechNoSpeech'
          : event.error === 'language-not-supported'
            ? 'speechLanguageUnavailable'
            : 'speechError';
      if (recognition.current === instance) recognition.current = null;
      setListening(false);
      setStatus(t(key));
    };
    instance.onend = () => {
      recognition.current = null;
      if (!mounted.current) return;
      setListening(false);
    };
    try {
      setStatus(t('speechSpeakNow'));
      instance.start();
    } catch {
      recognition.current = null;
      setStatus(t('speechError'));
    }
  };

  return <div className="speech-input">
    <button className="speech-input-button" type="button" disabled={disabled} aria-pressed={listening} onClick={() => listening ? stop() : start()}>
      <span aria-hidden="true">🎙</span>
      <span>{listening ? t('speechStop') : t('speechSpeakNow')}</span>
    </button>
    <p className="speech-status" aria-live="polite">{status}</p>
  </div>;
}
