import { useEffect, useRef, useState } from 'react';
import { askQuestion, getHealth } from './services/api';
import type { AssistantContext, Audience, ChatResponse } from './types/chat';
import { ChatHeader } from './components/ChatHeader';
import { ChatInput } from './components/ChatInput';
import { ChatMessage } from './components/ChatMessage';
import { SuggestedQuestions } from './components/SuggestedQuestions';
import { LoadingMessage } from './components/LoadingMessage';
import { ErrorMessage } from './components/ErrorMessage';
import { ComplianceWizard } from './components/ComplianceWizard';
import { builtInSuggestedActions, normalizeSuggestedActions, questionForSuggestedAction } from './suggestedActions';
import type { SuggestedAction } from './suggestedActions';
import { LanguageProvider, useLanguage } from './i18n/LanguageContext';
import type { Language, TranslationKey } from './i18n/translations';

type AssistantRequest = { question: string; audience: Audience; assistantContext?: AssistantContext };
type Message = { id: number; role: 'user' | 'assistant'; text: string; response?: ChatResponse; suggestedActions?: SuggestedAction[]; request?: AssistantRequest };

function isIndependentQuestion(value: string): boolean {
  const text = value.trim();
  return /^(?:what|which|how|ow\s+many|when|why|where|can|does|do|is|are|will|should)\b/i.test(text);
}

function isStandardFollowUp(value: string): boolean {
  return /\b(?:this|that|the)\s+standards?\b|\bprimary standard\b|\bsimpler language\b|\bin simple(?:r)?(?:\s+words|\s+language)?\b|\bmore simply\b|\bafter identifying\b|\btell me about the is\b/i.test(value);
}

const builtInSuggestionKeys: TranslationKey[] = ['suggestionBattery', 'suggestionHandmade', 'suggestionDocuments', 'suggestionTransition'];

function AppContent() {
  const { t, language } = useLanguage();
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [last, setLast] = useState('');
  const [lastDisplay, setLastDisplay] = useState('');
  const [lastContext, setLastContext] = useState<AssistantContext | undefined>();
  const [pendingContext, setPendingContext] = useState<AssistantContext | null>(null);
  const [sessionContext, setSessionContext] = useState<AssistantContext | undefined>();
  const [audience, setAudience] = useState<Audience>('general');
  const [mode, setMode] = useState<'chat' | 'wizard'>('chat');
  const [status, setStatus] = useState<'ready' | 'degraded' | 'unavailable'>('unavailable');
  const [updatingAnswers, setUpdatingAnswers] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const chatController = useRef<AbortController | null>(null);
  const localizationController = useRef<AbortController | null>(null);
  const localizationVersion = useRef(0);
  const messageId = useRef(0);
  const responseVariants = useRef(new Map<number, Map<Language, ChatResponse>>());
  const requestPending = useRef(false);
  const wizardEntry = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function loadHealth() {
      try {
        const result = await getHealth(controller.signal);
        if (!controller.signal.aborted) setStatus(result.status === 'ready' ? 'ready' : 'degraded');
      } catch {
        if (!controller.signal.aborted) setStatus('unavailable');
      }
    }
    void loadHealth();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, busy]);

  useEffect(() => () => {
    chatController.current?.abort();
    localizationController.current?.abort();
  }, []);

  useEffect(() => {
    const assistantMessages = messages.filter((message): message is Message & { request: AssistantRequest } => message.role === 'assistant' && Boolean(message.request));
    if (assistantMessages.length === 0) return;

    localizationController.current?.abort();
    const controller = new AbortController();
    localizationController.current = controller;
    const version = ++localizationVersion.current;
    const missing = assistantMessages.filter((message) => !responseVariants.current.get(message.id)?.has(language));

    setMessages((items) => items.map((message) => {
      if (message.role !== 'assistant') return message;
      const cached = responseVariants.current.get(message.id)?.get(language);
      return cached ? { ...message, text: cached.answer, response: cached } : message;
    }));
    if (missing.length === 0) {
      setUpdatingAnswers(false);
      return () => controller.abort();
    }

    setUpdatingAnswers(true);
    void Promise.all(missing.map(async (message) => {
      try {
        const response = await askQuestion(message.request.question, message.request.audience, message.request.assistantContext, controller.signal, language);
        if (controller.signal.aborted || localizationVersion.current !== version) return;
        const variants = responseVariants.current.get(message.id) ?? new Map<Language, ChatResponse>();
        variants.set(language, response);
        responseVariants.current.set(message.id, variants);
        setMessages((items) => items.map((item) => item.id === message.id && item.role === 'assistant'
          ? { ...item, text: response.answer, response }
          : item));
      } catch {
        // Retain the last verified response. Backend error bodies are never surfaced here.
      }
    })).finally(() => {
      if (!controller.signal.aborted && localizationVersion.current === version) setUpdatingAnswers(false);
    });

    return () => controller.abort();
  }, [language]);

  useEffect(() => {
    if (mode === 'wizard') {
      wizardEntry.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      wizardEntry.current?.focus({ preventScroll: true });
    }
  }, [mode]);

  const send = async (question: string, suppliedContext?: AssistantContext, displayText = question) => {
    if (busy || requestPending.current) return;
    requestPending.current = true;
    const continuing = Boolean(pendingContext && !isIndependentQuestion(question));
    const followUp = Boolean(sessionContext && isStandardFollowUp(question));
    const assistantContext = suppliedContext ?? (continuing ? pendingContext ?? undefined : followUp ? sessionContext : undefined);
    if (!continuing && !suppliedContext && !followUp) setPendingContext(null);
    setBusy(true);
    setError('');
    setLast(question);
    setLastDisplay(displayText);
    setLastContext(assistantContext);
    setMessages((items) => [...items, { id: ++messageId.current, role: 'user', text: displayText }]);
    const controller = new AbortController();
    chatController.current = controller;
    try {
      const response = await askQuestion(question, audience, assistantContext, controller.signal, language);
      const id = ++messageId.current;
      responseVariants.current.set(id, new Map([[language, response]]));
      setMessages((items) => [...items, { id, role: 'assistant', text: response.answer, response, suggestedActions: normalizeSuggestedActions(response), request: { question, audience, assistantContext } }]);
      setSessionContext(response.assistant_context ?? undefined);
      setPendingContext(response.needs_clarification
        ? (response.assistant_context ?? { original_question: assistantContext?.original_question ?? question, expected_slots: [] })
        : null);
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : 'Unable to complete that request.');
      }
    } finally {
      if (chatController.current === controller) chatController.current = null;
      requestPending.current = false;
      setBusy(false);
    }
  };

  const resetConversation = () => {
    chatController.current?.abort();
    localizationController.current?.abort();
    localizationVersion.current += 1;
    responseVariants.current.clear();
    requestPending.current = false;
    setMessages([]); setPendingContext(null); setSessionContext(undefined); setLastContext(undefined); setLast(''); setLastDisplay(''); setError(''); setBusy(false); setUpdatingAnswers(false);
  };

  const switchMode = (next: 'chat' | 'wizard') => {
    if (next === mode) return;
    resetConversation();
    setMode(next);
  };

  const dispatchSuggestedAction = (action: SuggestedAction, context?: AssistantContext) => {
    if (action.kind === 'open_compliance_wizard') {
      switchMode('wizard');
      return;
    }
    const question = questionForSuggestedAction(action);
    if (question) void send(question, context, action.label);
  };

  const translatedBuiltInActions = builtInSuggestedActions.map((action, index) => ({ ...action, label: t(builtInSuggestionKeys[index]) }));

  return <main>
    <ChatHeader status={status} />
    <nav aria-label={t('guidanceMode')}>
      <button onClick={() => switchMode('chat')} aria-pressed={mode === 'chat'}>{t('askQuestion')}</button>
      <button onClick={() => switchMode('wizard')} aria-pressed={mode === 'wizard'}>{t('complianceWizard')}</button>
    </nav>
    {mode === 'wizard' ? <div ref={wizardEntry} tabIndex={-1}><ComplianceWizard /></div> : <>
      <section className="hero">
        <h2>{t('heroTitle')}</h2>
        <p>{t('heroDescription')}</p>
      </section>
      {messages.length === 0 && <SuggestedQuestions actions={translatedBuiltInActions} busy={busy} onSelect={action => dispatchSuggestedAction(action)} />}
      <section className="chat" aria-live="polite">
        {messages.map((message) => <ChatMessage key={message.id} {...message} busy={busy} onSuggestedAction={message.role === 'assistant' && (message.suggestedActions?.length ?? 0) > 0 ? action => dispatchSuggestedAction(action, pendingContext ?? sessionContext ?? message.response?.assistant_context ?? undefined) : undefined} />)}
        {busy && <LoadingMessage />}
        {updatingAnswers && <p className="answer-update" aria-live="polite">{t('updatingAnswers')}</p>}
        {error && <ErrorMessage message={error} onRetry={() => send(last, lastContext, lastDisplay)} />}
        <div ref={end} />
      </section>
      <ChatInput onSend={send} busy={busy} audience={audience} onAudienceChange={setAudience} />
      {messages.length > 0 && <button type="button" className="secondary reset-conversation" onClick={resetConversation} disabled={busy}>{t('startOver')}</button>}
    </>}
    <footer>{t('footer')}</footer>
  </main>;
}

export default function App() {
  return <LanguageProvider><AppContent /></LanguageProvider>;
}
