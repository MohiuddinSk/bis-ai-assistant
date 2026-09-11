import { useEffect, useRef, useState } from 'react';
import { askQuestion, getHealth } from './services/api';
import type { ChatResponse } from './types/chat';
import { ChatHeader } from './components/ChatHeader';
import { ChatInput } from './components/ChatInput';
import { ChatMessage } from './components/ChatMessage';
import { SuggestedQuestions } from './components/SuggestedQuestions';
import { LoadingMessage } from './components/LoadingMessage';
import { ErrorMessage } from './components/ErrorMessage';
type Message={role:'user'|'assistant';text:string;response?:ChatResponse};
export default function App(){
 const [messages,setMessages]=useState<Message[]>([]);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [last,setLast]=useState('');const [status,setStatus]=useState<'ready'|'degraded'|'unavailable'>('unavailable');const end=useRef<HTMLDivElement>(null);
 useEffect(()=>{const controller=new AbortController();async function loadHealth(){try{const result=await getHealth(controller.signal);if(!controller.signal.aborted)setStatus(result.status==='ready'?'ready':'degraded')}catch{if(!controller.signal.aborted)setStatus('unavailable')}}void loadHealth();return()=>controller.abort()},[]);
 useEffect(()=>{end.current?.scrollIntoView({behavior:'smooth'})},[messages,busy]);
 const send=async(question:string)=>{if(busy)return;setBusy(true);setError('');setLast(question);setMessages(items=>[...items,{role:'user',text:question}]);try{const response=await askQuestion(question);setMessages(items=>[...items,{role:'assistant',text:response.answer,response}])}catch(e){setError(e instanceof Error?e.message:'Unable to complete that request.')}finally{setBusy(false)}};
 return <main><ChatHeader status={status}/><section className="hero"><h2>Practical standards guidance, with evidence</h2><p>AI-generated informational guidance grounded in indexed BIS documents. Verify final compliance requirements with BIS or a qualified professional.</p></section>{messages.length===0&&<SuggestedQuestions onSelect={send}/>}<section className="chat" aria-live="polite">{messages.map((m,i)=><ChatMessage key={i} {...m}/>)}{busy&&<LoadingMessage/>}{error&&<ErrorMessage message={error} onRetry={()=>send(last)}/>}<div ref={end}/></section><ChatInput onSend={send} busy={busy}/><footer>Informational guidance only. Final compliance requirements should be verified with BIS or a qualified professional.</footer></main>
}
