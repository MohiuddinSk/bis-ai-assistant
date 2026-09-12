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

type Message = { role: 'user' | 'assistant'; text: string; response?: ChatResponse };

function isIndependentQuestion(value: string): boolean {
  const text = value.trim();
  return /^(?:what|which|how|ow\s+many|when|why|where|can|does|do|is|are|will|should)\b/i.test(text);
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [last, setLast] = useState('');
  const [lastContext, setLastContext] = useState<AssistantContext | undefined>();
  const [pendingContext, setPendingContext] = useState<AssistantContext | null>(null);
  const [audience, setAudience] = useState<Audience>('general');
  const [mode, setMode] = useState<'chat' | 'wizard'>('chat');
  const [status, setStatus] = useState<'ready' | 'degraded' | 'unavailable'>('unavailable');
  const end = useRef<HTMLDivElement>(null);
  const chatController = useRef<AbortController | null>(null);

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

  useEffect(() => () => chatController.current?.abort(), []);

  const send = async (question: string, suppliedContext?: AssistantContext) => {
    if (busy) return;
    const continuing = Boolean(pendingContext && !isIndependentQuestion(question));
    const assistantContext = suppliedContext ?? (continuing ? pendingContext ?? undefined : undefined);
    if (!continuing && !suppliedContext) setPendingContext(null);
    setBusy(true);
    setError('');
    setLast(question);
    setLastContext(assistantContext);
    setMessages((items) => [...items, { role: 'user', text: question }]);
    const controller = new AbortController();
    chatController.current = controller;
    try {
      const response = await askQuestion(question, audience, assistantContext, controller.signal);
      setMessages((items) => [...items, { role: 'assistant', text: response.answer, response }]);
      setPendingContext(response.needs_clarification
        ? (response.assistant_context ?? { original_question: assistantContext?.original_question ?? question, expected_slots: [] })
        : null);
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : 'Unable to complete that request.');
      }
    } finally {
      if (chatController.current === controller) chatController.current = null;
      setBusy(false);
    }
  };

  const resetConversation = () => {
    chatController.current?.abort();
    setMessages([]); setPendingContext(null); setLastContext(undefined); setLast(''); setError(''); setBusy(false);
  };

  return <main>
    <ChatHeader status={status} />
    <nav aria-label="Guidance mode">
      <button onClick={() => setMode('chat')} aria-pressed={mode === 'chat'}>Ask a question</button>
      <button onClick={() => setMode('wizard')} aria-pressed={mode === 'wizard'}>Compliance Wizard</button>
    </nav>
    {mode === 'wizard' ? <ComplianceWizard /> : <>
      <section className="hero">
        <h2>Practical standards guidance, with evidence</h2>
        <p>AI-generated informational guidance grounded in indexed BIS documents. Verify final compliance requirements with BIS or a qualified professional.</p>
      </section>
      {messages.length === 0 && <SuggestedQuestions onSelect={send} />}
      <section className="chat" aria-live="polite">
        {messages.map((message, index) => <ChatMessage key={index} {...message} busy={busy} onSuggestedReply={message.role === 'assistant' && pendingContext ? (reply) => void send(reply, pendingContext) : undefined} />)}
        {busy && <LoadingMessage />}
        {error && <ErrorMessage message={error} onRetry={() => send(last, lastContext)} />}
        <div ref={end} />
      </section>
      <ChatInput onSend={send} busy={busy} audience={audience} onAudienceChange={setAudience} />
      {messages.length > 0 && <button type="button" className="secondary reset-conversation" onClick={resetConversation} disabled={busy}>Start over</button>}
    </>}
    <footer>Informational guidance only. Final compliance requirements should be verified with BIS or a qualified professional.</footer>
  </main>;
}
