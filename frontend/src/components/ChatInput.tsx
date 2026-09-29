import { useState } from 'react';
import type { RefObject } from 'react';
import type { Audience } from '../types/chat';
import { useLanguage } from '../i18n/LanguageContext';
import { SpeechInput } from './SpeechInput';
export function ChatInput({
  onSend,
  busy,
  audience,
  onAudienceChange,
  autoFocus = false,
  inputRef,
}: {
  onSend: (question: string) => void;
  busy: boolean;
  audience: Audience;
  onAudienceChange: (audience: Audience) => void;
  autoFocus?: boolean;
  inputRef?: RefObject<HTMLTextAreaElement | null>;
}) {
  const [value, setValue] = useState('');
  const { t } = useLanguage();

  const submit = () => {
    const question = value.trim();
    if (question && !busy) {
      onSend(question);
      setValue('');
    }
  };

  return <div className="input-wrap">
    <label htmlFor="audience">{t('audienceLabel')}</label>
    <select id="audience" value={audience} disabled={busy} onChange={event => onAudienceChange(event.target.value as Audience)}>
      <option value="general">{t('audienceGeneral')}</option>
      <option value="manufacturer">{t('audienceManufacturer')}</option>
      <option value="consumer">{t('audienceConsumer')}</option>
    </select>
    <label htmlFor="question">{t('shellSearchLabel')}</label>
    <textarea
      ref={inputRef}
      id="question"
      autoFocus={autoFocus}
      value={value}
      maxLength={1000}
      disabled={busy}
      onChange={event => setValue(event.target.value)}
      onKeyDown={event => {
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault();
          submit();
        }
      }}
    />
    <div>
      <small>{value.length}/1000</small>
      <div className="composer-actions">
        <SpeechInput value={value} onTranscript={setValue} disabled={busy} />
        <button onClick={submit} disabled={busy || !value.trim()}>{busy ? t('sending') : t('send')}</button>
      </div>
    </div>
  </div>;
}
