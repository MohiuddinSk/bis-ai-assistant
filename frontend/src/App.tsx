import { FormEvent, useEffect, useRef, useState } from 'react';
import { askQuestion, getHealth } from './services/api';
import type { AssistantContext, Audience, ChatResponse } from './types/chat';
import { ChatHeader } from './components/ChatHeader';
import { ChatInput } from './components/ChatInput';
import { SpeechInput } from './components/SpeechInput';
import { ChatMessage } from './components/ChatMessage';
import { SuggestedQuestions } from './components/SuggestedQuestions';
import { LoadingMessage } from './components/LoadingMessage';
import { ErrorMessage } from './components/ErrorMessage';
import { ComplianceWizard } from './components/ComplianceWizard';
import { builtInSuggestedActions, normalizeSuggestedActions, questionForSuggestedAction } from './suggestedActions';
import type { SuggestedAction } from './suggestedActions';
import { LanguageProvider, useLanguage } from './i18n/LanguageContext';
import type { Language, TranslationKey } from './i18n/translations';
type View='home'|'assistant'|'wizard';
type AssistantRequest={question:string;
audience:Audience;
assistantContext?:AssistantContext};
type Message={id:number;
role:'user'|'assistant';
text:string;
response?:ChatResponse;
suggestedActions?:SuggestedAction[];
request?:AssistantRequest};
const suggestionKeys:TranslationKey[]=['suggestionBattery','suggestionHandmade','suggestionDocuments','suggestionTransition'];
const actionKeys:Record<string,TranslationKey>={'Explain when this standard applies':'suggestedExplainApplies','Explain this in simpler language':'suggestedSimpler','Explain that standard':'suggestedExplainStandard','Show my complete compliance roadmap':'suggestedRoadmap'};
const consumerServiceLabel: Record<Language, string> = {
  en: 'Official BIS consumer information ↗',
  hi: 'आधिकारिक BIS उपभोक्ता जानकारी ↗',
  mr: 'अधिकृत BIS ग्राहक माहिती ↗',
  ta: 'அதிகாரப்பூர்வ BIS நுகர்வோர் தகவல் ↗',
  bn: 'সরকারি BIS ভোক্তা তথ্য ↗',
};
const prototypeCoverage: Record<Language, string> = {
  en: 'Prototype coverage currently focuses on indexed toy documents and processes; it does not cover every BIS service or standard.',
  hi: 'यह प्रोटोटाइप अभी सूचीबद्ध खिलौना दस्तावेज़ों और प्रक्रियाओं पर केंद्रित है; यह हर BIS सेवा या मानक को कवर नहीं करता।',
  mr: 'हा प्रोटोटाइप सध्या अनुक्रमित खेळणी दस्तऐवज आणि प्रक्रियांवर केंद्रित आहे; तो प्रत्येक BIS सेवा किंवा मानक समाविष्ट करत नाही.',
  ta: 'இந்த முன்மாதிரி தற்போது குறியிடப்பட்ட பொம்மை ஆவணங்கள் மற்றும் செயல்முறைகளில் கவனம் செலுத்துகிறது; இது ஒவ்வொரு BIS சேவை அல்லது தரநிலையையும் உள்ளடக்காது.',
  bn: 'এই প্রোটোটাইপটি বর্তমানে সূচিবদ্ধ খেলনা-সংক্রান্ত নথি ও প্রক্রিয়ার উপর কেন্দ্রীভূত; এটি প্রতিটি BIS পরিষেবা বা মানকে অন্তর্ভুক্ত করে না।',
};
const independent=(q:string)=>/^(?:what|which|how|when|why|where|can|does|do|is|are|will|should)\b/i.test(q.trim());
const followup=(q:string)=>/\b(?:this|that|the)\s+standards?\b|\bprimary standard\b|\bsimpler language\b|\bin simple(?:r)?(?:\s+words|\s+language)?\b|\bmore simply\b|\bafter identifying\b|\btell me about the is\b/i.test(q);
function Home({ ask, go, findStandard, startAudienceJourney }: { ask: (q: string, a?: Audience) => void;
go: (v: View) => void;
findStandard: () => void;
startAudienceJourney: (audience: Audience) => void }) {
  const { t, language } = useLanguage();
const [q, setQ] = useState('');
const submit = (e: FormEvent) => { e.preventDefault();
if (q.trim()) ask(q.trim());
};
return <>
    <section className="bandhu-hero">
<div>
<p className="eyebrow">{t('shellKicker')}
</p>
<h1>{t('shellHero')}
</h1>
<p className="hero-lead">{t('shellHeroLead')}
</p>
<p className="prototype-scope">{prototypeCoverage[language]}
</p>
<div className="hero-actions">
<button onClick={() => go('assistant')}>{t('shellAskBandhu')}
</button>
<button className="secondary" onClick={findStandard}>{t('shellFindStandard')}
</button>
<button className="example-action" onClick={() => ask('Which standard applies to a battery-operated toy?', 'manufacturer')}>{t('shellTryExample')}
</button>
</div>
<form className="hero-search" onSubmit={submit}>
<label htmlFor="bandhu-search">{t('shellSearchLabel')}
</label>
<div>
<input id="bandhu-search" value={q} onChange={e => setQ(e.target.value)} placeholder={t('shellSearchPlaceholder')} />
<SpeechInput value={q} onTranscript={setQ} />
<button>{t('shellAskBandhu')}
</button>
</div>
</form>
</div>
<div className="hero-proof">
<div className="seal">BIS<br />
<small>BANDHU</small>
</div>
<p>{t('shellEvidenceKicker')}
</p>
<strong>{t('shellEvidenceTitle')}
</strong>
<span>{t('shellEvidenceLead')}
</span>
</div>
</section>
    <section className="intent-section">
<div className="section-heading">
<p className="eyebrow">{t('shellStartKicker')}
</p>
<h2>{t('shellJourneyTitle')}
</h2>
<p>{t('shellJourneyLead')}
</p>
</div>
<div className="intent-grid">
<button className="intent-card" onClick={() => startAudienceJourney('manufacturer')}>
<span className="intent-icon">⌘</span>
<h3>{t('shellIndustryTitle')}
</h3>
<p>{t('shellIndustryLead')}
</p>
<b>{t('shellIndustryAction')} →</b>
</button>
<button className="intent-card" onClick={() => startAudienceJourney('consumer')}>
<span className="intent-icon">◌</span>
<h3>{t('shellConsumerTitle')}
</h3>
<p>{t('shellConsumerLead')}
</p>
<b>{t('shellConsumerAction')} →</b>
</button>
<button className="intent-card featured" onClick={() => go('wizard')}>
<span className="intent-icon">✓</span>
<h3>{t('shellPassportTitle')}
</h3>
<p>{t('shellPassportLead')}
</p>
<b>{t('shellPassportAction')} →</b>
</button>
</div>
</section>
    <section className="evidence-journey">
<div>
<p className="eyebrow">{t('shellPathKicker')}
</p>
<h2>{t('shellPathTitle')}
</h2>
</div>
<ol>
<li>
<b>01</b>
<span>{t('shellStepOne')}
</span>
</li>
<li>
<b>02</b>
<span>{t('shellStepTwo')}
</span>
</li>
<li>
<b>03</b>
<span>{t('shellStepThree')}
</span>
</li>
<li>
<b>04</b>
<span>{t('shellStepFour')}
</span>
</li>
</ol>
</section>
  </>;
}
function AppContent(){const{t,language}=useLanguage();
const[view,setView]=useState<View>('home');
const[menu,setMenu]=useState(false);
const[messages,setMessages]=useState<Message[]>([]);
const[busy,setBusy]=useState(false);
const[error,setError]=useState('');
const[last,setLast]=useState('');
const[lastDisplay,setLastDisplay]=useState('');
const[lastContext,setLastContext]=useState<AssistantContext>();
const[pending,setPending]=useState<AssistantContext|null>(null);
const[session,setSession]=useState<AssistantContext>();
const[audience,setAudience]=useState<Audience>('general');
const[findingStandard,setFindingStandard]=useState(false);
const[status,setStatus]=useState<'ready'|'degraded'|'unavailable'>('unavailable');
const[updating,setUpdating]=useState(false);
const[theme,setTheme]=useState<'light'|'dark'>('light');
const end=useRef<HTMLDivElement>(null),questionInput=useRef<HTMLTextAreaElement>(null),chatAbort=useRef<AbortController|null>(null),localeAbort=useRef<AbortController|null>(null),localeVersion=useRef(0),id=useRef(0),variants=useRef(new Map<number,Map<Language,ChatResponse>>()),pendingRequest=useRef(false);
useEffect(()=>{const c=new AbortController();
void getHealth(c.signal).then(x=>!c.signal.aborted&&setStatus(x.status==='ready'?'ready':'degraded')).catch(()=>!c.signal.aborted&&setStatus('unavailable'));
return()=>c.abort()},[]);
useEffect(()=>{end.current?.scrollIntoView({behavior:'smooth'})},[messages,busy]);
useEffect(()=>{document.getElementById('main-content')?.scrollIntoView({behavior:'smooth',block:'start'})},[view]);
useEffect(()=>()=>{chatAbort.current?.abort();
localeAbort.current?.abort()},[]);
useEffect(()=>{document.documentElement.dataset.theme=theme},[theme]);
useEffect(()=>{
if(view==='assistant'&&findingStandard){
questionInput.current?.focus();
questionInput.current?.scrollIntoView({block:'center'});
setFindingStandard(false);
}
},[view,audience,findingStandard]);
useEffect(()=>{const items=messages.filter((m):m is Message&{request:AssistantRequest}=>m.role==='assistant'&&!!m.request);
if(!items.length)return;
localeAbort.current?.abort();
const c=new AbortController(),version=++localeVersion.current;
localeAbort.current=c;
const missing=items.filter(m=>!variants.current.get(m.id)?.has(language));
setMessages(all=>all.map(m=>{const cached=m.role==='assistant'?variants.current.get(m.id)?.get(language):undefined;
return cached?{...m,text:cached.answer,response:cached}:m}));
if(!missing.length){setUpdating(false);
return()=>c.abort()}setUpdating(true);
void Promise.all(missing.map(async m=>{try{const r=await askQuestion(m.request.question,m.request.audience,m.request.assistantContext,c.signal,language);
if(c.signal.aborted||localeVersion.current!==version)return;
const v=variants.current.get(m.id)??new Map<Language,ChatResponse>();
v.set(language,r);
variants.current.set(m.id,v);
setMessages(all=>all.map(x=>x.id===m.id&&x.role==='assistant'?{...x,text:r.answer,response:r}:x))}catch{}})).finally(()=>!c.signal.aborted&&localeVersion.current===version&&setUpdating(false));
return()=>c.abort()},[language]);
const send=async(q:string,supplied?:AssistantContext,display=q,forced?:Audience)=>{if(busy||pendingRequest.current)return;
setFindingStandard(false);
setView('assistant');
pendingRequest.current=true;
const continuing=!!pending&&!independent(q),context=supplied??(continuing?pending??undefined:session&&followup(q)?session:undefined),active=forced??audience;
if(forced)setAudience(forced);
if(!continuing&&!supplied&&!followup(q))setPending(null);
setBusy(true);
setError('');
setLast(q);
setLastDisplay(display);
setLastContext(context);
setMessages(x=>[...x,{id:++id.current,role:'user',text:display}]);
const c=new AbortController();
chatAbort.current=c;
try{const r=await askQuestion(q,active,context,c.signal,language),messageId=++id.current;
variants.current.set(messageId,new Map([[language,r]]));
setMessages(x=>[...x,{id:messageId,role:'assistant',text:r.answer,response:r,suggestedActions:normalizeSuggestedActions(r),request:{question:q,audience:active,assistantContext:context}}]);
setSession(r.assistant_context??undefined);
setPending(r.needs_clarification?(r.assistant_context??{original_question:context?.original_question??q,expected_slots:[]}):null)}catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:'Unable to complete that request.')}finally{if(chatAbort.current===c)chatAbort.current=null;
pendingRequest.current=false;
setBusy(false)}};
const reset=()=>{chatAbort.current?.abort();
localeAbort.current?.abort();
localeVersion.current++;
variants.current.clear();
pendingRequest.current=false;
setMessages([]);
setPending(null);
setSession(undefined);
setLastContext(undefined);
setLast('');
setLastDisplay('');
setError('');
setBusy(false);
setUpdating(false)};
const doAction=(a:SuggestedAction,c?:AssistantContext)=>{if(a.kind==='open_compliance_wizard'){go('wizard');
return}const q=questionForSuggestedAction(a);
if(q)void send(q,c,a.label)};
const go=(v:View)=>{if(view==='assistant'&&v!=='assistant'){setPending(null);
setSession(undefined)}setView(v);
setMenu(false)};
const startAudience=(selectedAudience:Audience)=>{
if(selectedAudience!==audience){
setPending(null);
setSession(undefined);
}
setAudience(selectedAudience);
setFindingStandard(true);
go('assistant');
};
const chooseTheme=(nextTheme:'light'|'dark')=>setTheme(nextTheme);
const local=(items:SuggestedAction[]|undefined)=>items?.map(a=>actionKeys[a.label]?{...a,label:t(actionKeys[a.label])}:a);
const themeAction=t(theme==='dark'?'themeLightMode':'themeDarkMode');
return <div className="app-shell">
<a className="skip-link" href="#main-content">{t('shellSkip')}
</a>
<header className="site-header">
<button className="brand" onClick={()=>go('home')}>
<img className="brand-logo" src="/bis-logo.jpeg" alt="" />
<span className="brand-copy"><strong>BIS Bandhu</strong><small>{t('shellTagline')}</small></span>
</button>
<nav className={menu?'open':''} aria-label={t('shellNavigation')}>
<button aria-current={view==='home'?'page':undefined} onClick={()=>go('home')}>{t('shellNavHome')}
</button>
<button aria-current={view==='assistant'&&audience==='general'?'page':undefined} onClick={()=>startAudience('general')}>{t('shellNavAssistant')}
</button>
<button aria-current={view==='assistant'&&audience==='manufacturer'?'page':undefined} onClick={()=>startAudience('manufacturer')}>{t('shellNavIndustry')}
</button>
<button aria-current={view==='assistant'&&audience==='consumer'?'page':undefined} onClick={()=>startAudience('consumer')}>{t('shellNavConsumers')}
</button>
<button aria-current={view==='wizard'?'page':undefined} onClick={()=>go('wizard')}>{t('shellNavWizard')}
</button>
</nav>
<div className="header-tools">
<ChatHeader status={status}/>
<button className="theme-toggle" type="button" aria-pressed={theme==='dark'} onClick={()=>chooseTheme(theme==='dark'?'light':'dark')}><span aria-hidden="true">{theme==='dark'?'☀':'◐'}</span><span>{themeAction}</span></button>
<button className="menu-toggle" aria-label={t('shellToggleNavigation')} aria-expanded={menu} onClick={()=>setMenu(!menu)}>☰</button>
</div>
</header>
<main id="main-content">{view==='home'&&<Home ask={(q,a)=>void send(q,undefined,q,a)} go={go} findStandard={()=>{setAudience('manufacturer');
setFindingStandard(true);
go('assistant')}} startAudienceJourney={startAudience}/>} {view==='assistant'&&<section className="assistant-view">
<div className="view-intro">
<p className="eyebrow">{audience==='manufacturer'?t('roleManufacturer'):audience==='consumer'?t('roleConsumer'):t('shellAssistantKicker')}
</p>
<h1>{audience==='manufacturer'?t('shellIndustryTitle'):audience==='consumer'?t('shellConsumerTitle'):t('shellAssistantTitle')}
</h1>
<p>{audience==='manufacturer'?t('manufacturerCard'):audience==='consumer'?t('consumerCard'):t('shellAssistantLead')}
</p>
{audience==='consumer'&&<a className="official-service-link" href="https://www.bis.gov.in/consumer-overview/" target="_blank" rel="noopener noreferrer">{consumerServiceLabel[language]}</a>}
</div>{messages.length===0&&<SuggestedQuestions actions={builtInSuggestedActions.map((a,i)=>({...a,label:t(suggestionKeys[i])}))} busy={busy} onSelect={a=>doAction(a)}/>}
{(messages.length>0||busy||updating||error)&&<section className="chat" aria-live="polite">{messages.map(m=>
<ChatMessage key={m.id} {...m} suggestedActions={local(m.suggestedActions)} busy={busy} onSuggestedAction={m.role==='assistant'&&(m.suggestedActions?.length??0)>0 ? (a=>doAction(a,pending??session??m.response?.assistant_context??undefined)) : undefined}/>)}{busy&&<LoadingMessage/>}{updating&&<p className="answer-update">{t('updatingAnswers')}
</p>}{error&&<ErrorMessage message={error} onRetry={()=>void send(last,lastContext,lastDisplay)}/>}
<div ref={end}/>
</section>}
<ChatInput onSend={send} busy={busy} audience={audience} onAudienceChange={startAudience} autoFocus={findingStandard} inputRef={questionInput}/>{messages.length>0&&<button className="secondary reset-conversation" onClick={reset} disabled={busy}>{t('startOver')}
</button>}
</section>}
<section className="wizard-view" hidden={view!=='wizard'}>
<div className="view-intro">
<p className="eyebrow">{t('shellWizardKicker')}
</p>
<h1>{t('shellWizardTitle')}
</h1>
<p>{t('shellWizardLead')}
</p>
</div>
<ComplianceWizard/>
</section>
</main>
<footer>
<b>BIS Bandhu</b>
<span>{t('footer')}
</span>
</footer>
</div>}
export default function App(){return <LanguageProvider>
<AppContent/>
</LanguageProvider>}
