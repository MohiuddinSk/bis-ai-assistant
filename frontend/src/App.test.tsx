import {act,cleanup,render,screen,waitFor} from '@testing-library/react';import userEvent from '@testing-library/user-event';import {vi,it,expect,beforeEach,afterEach} from 'vitest';import App from './App';
const a={answer:'IS 15644 is the primary standard.',grounded:true,insufficient_evidence:false,evidence_count:2,citations:[{citation_id:'S1',source_filename:'manual.pdf',page_start:4,page_end:4,chunk_id:'secret',excerpt:'IS 15644 applies.'}],model:'test',generation_mode:'llm' as const,disclaimer:'Verify'};const rep=(x:unknown)=>({ok:true,json:async()=>x});const mock=(chat:unknown=a,health:unknown={status:'ready'})=>vi.stubGlobal('fetch',vi.fn((u:string)=>Promise.resolve(rep(u.includes('health')?health:chat))));beforeEach(()=>{vi.restoreAllMocks();mock()});afterEach(()=>{cleanup();vi.restoreAllMocks()});const renderReady=async()=>{render(<App/>);await screen.findByRole('status')};
it('renders welcome',async()=>{await renderReady();expect(screen.getByText('Suggested questions')).toBeInTheDocument()});
it('switches between chat and compliance wizard',async()=>{await renderReady();const u=userEvent.setup();await u.click(screen.getByRole('button',{name:'Compliance Wizard'}));expect(screen.getByRole('heading',{name:'Compliance Wizard'})).toBeInTheDocument();await u.click(screen.getByRole('button',{name:'Ask a question'}));expect(screen.getByText('Suggested questions')).toBeInTheDocument()});
it('suggestion submits grounded answer',async()=>{render(<App/>);await userEvent.setup().click(screen.getByText(/battery-operated/i));expect(await screen.findByText(a.answer)).toBeInTheDocument()});
it('empty input rejected',async()=>{await renderReady();expect(screen.getByRole('button',{name:'Send'})).toBeDisabled()});
it('allows a user to choose a guidance audience',async()=>{await renderReady();const selector=screen.getByLabelText('I am a:');await userEvent.setup().selectOptions(selector,'manufacturer');expect(selector).toHaveValue('manufacturer')});
it('citation source page and excerpt expand',async()=>{render(<App/>);const u=userEvent.setup();await u.click(screen.getByText(/battery-operated/i));const b=await screen.findByRole('button',{name:/view evidence/i});expect(screen.getByRole('heading',{name:/sources 1/i})).toBeInTheDocument();expect(screen.getByText(/manual.pdf/).parentElement).toHaveTextContent('Page 4');await u.click(b);expect(screen.getByText(a.citations[0].excerpt)).toBeInTheDocument()});
it('keeps spaces between adjacent answer sentences',async()=>{mock({...a,answer:'IS 15644. IS 9873 are secondary standards.'});render(<App/>);await userEvent.setup().click(screen.getByText(/battery-operated/i));expect(await screen.findByText('IS 15644. IS 9873 are secondary standards.')).toBeInTheDocument()});
it('insufficient response displayed',async()=>{mock({...a,grounded:false,insufficient_evidence:true,generation_mode:'abstention'});render(<App/>);await userEvent.setup().click(screen.getByText(/battery-operated/i));expect(await screen.findByText('Evidence insufficient')).toBeInTheDocument()});
it('extractive fallback grounded',async()=>{mock({...a,generation_mode:'extractive_fallback'});render(<App/>);await userEvent.setup().click(screen.getByText(/battery-operated/i));expect(await screen.findByText('Grounded answer')).toBeInTheDocument()});
it('loading appears',async()=>{let done!:Function;vi.stubGlobal('fetch',vi.fn((u:string)=>u.includes('health')?Promise.resolve(rep({status:'ready'})):new Promise(r=>done=r)));await renderReady();await userEvent.setup().click(screen.getByText(/battery-operated/i));expect(screen.getByText(/searching bis documents/i)).toBeInTheDocument();await act(async()=>{done(rep(a))});await screen.findByText(a.answer)});
it('duplicate prevented',async()=>{let done!:Function;const f=vi.fn((u:string)=>u.includes('health')?Promise.resolve(rep({status:'ready'})):new Promise(r=>done=r));vi.stubGlobal('fetch',f);await renderReady();const u=userEvent.setup();await u.click(screen.getByText(/battery-operated/i));await u.click(screen.getByText(/battery-operated/i));expect(f).toHaveBeenCalledTimes(2);await act(async()=>{done(rep(a))});await screen.findByText(a.answer)});
it('failure retry',async()=>{const f=vi.fn().mockResolvedValueOnce(rep({status:'ready'})).mockRejectedValueOnce(Error()).mockResolvedValueOnce(rep(a));vi.stubGlobal('fetch',f);render(<App/>);const u=userEvent.setup();await u.click(screen.getByText(/battery-operated/i));await u.click(await screen.findByText('Retry'));expect(await screen.findByText(a.answer)).toBeInTheDocument()});
it('Enter sends',async()=>{render(<App/>);await userEvent.setup().type(screen.getByLabelText(/ask a question/i),'test?{Enter}');expect(await screen.findByText(a.answer)).toBeInTheDocument()});
it('Shift Enter newline',async()=>{render(<App/>);const b=screen.getByLabelText(/ask a question/i);await userEvent.setup().type(b,'x{Shift>}{Enter}{/Shift}y');expect(b).toHaveValue('x\ny')});
it('health ready',async()=>{render(<App/>);expect(await screen.findByRole('status')).toHaveTextContent('ready')});
it('health degraded',async()=>{mock(a,{status:'degraded'});render(<App/>);expect(await screen.findByRole('status')).toHaveTextContent('degraded')});
it('health unavailable',async()=>{vi.stubGlobal('fetch',vi.fn().mockRejectedValue(Error()));render(<App/>);expect(await screen.findByRole('status')).toHaveTextContent('unavailable')});
it('malformed API response is safe',async()=>{mock({bad:true});render(<App/>);await userEvent.setup().click(screen.getByText(/battery-operated/i));expect(await screen.findByRole('alert')).toHaveTextContent(/unreadable/i)});
it('raw HTML remains text',async()=>{mock({...a,answer:'<b>unsafe</b>'});render(<App/>);await userEvent.setup().click(screen.getByText(/battery-operated/i));expect(await screen.findByText('<b>unsafe</b>')).toBeInTheDocument();expect(document.querySelector('b')).toBeNull()});

it('renders clarification as Need more details and sends bounded context with the follow-up',async()=>{
 const context={original_question:'What standards apply to toys?',expected_slots:['power_type' as const],current_goal:'identify_standards' as const};
 const clarification={...a,answer:'Is the toy battery-operated, mains-powered, or non-electric?',grounded:false,insufficient_evidence:false,needs_clarification:true,generation_mode:'clarification' as const,citations:[],suggested_replies:['Battery-operated','Mains-powered','Non-electric'],assistant_context:context,answer_sections:[{type:'clarification' as const,title:'Need more details',content:'Is the toy battery-operated, mains-powered, or non-electric?',items:[],citation_ids:[]}]};
 let chatCall=0;
 const f=vi.fn((url:string,init?:RequestInit)=>{
  if(url.includes('health'))return Promise.resolve(rep({status:'ready'}));
  chatCall+=1;
  return Promise.resolve(rep(chatCall===1?clarification:{...a,needs_clarification:false}));
 });
 vi.stubGlobal('fetch',f);render(<App/>);const u=userEvent.setup();
 await u.type(screen.getByLabelText(/ask a question/i),'What standards apply to toys?{Enter}');
 expect(await screen.findByText('Need more details',{selector:'.answer-status'})).toBeInTheDocument();
 await u.click(screen.getByRole('button',{name:'Non-electric'}));
 await screen.findByText(a.answer);
 const payload=JSON.parse(String((f.mock.calls[2]?.[1] as RequestInit).body));
 expect(payload.assistant_context).toEqual(context);
 expect(f).toHaveBeenCalledTimes(3);
});

it('does not attach stale clarification context to an unrelated full question',async()=>{
 const clarification={...a,answer:'Is the toy battery-operated, mains-powered, or non-electric?',grounded:false,insufficient_evidence:false,needs_clarification:true,generation_mode:'clarification' as const,citations:[],assistant_context:{original_question:'What standards apply to toys?',expected_slots:['power_type']}};
 let chatCall=0;const f=vi.fn((url:string,_init?:RequestInit)=>Promise.resolve(rep(url.includes('health')?{status:'ready'}:(chatCall++===0?clarification:a))));
 vi.stubGlobal('fetch',f);render(<App/>);const u=userEvent.setup();
 await u.type(screen.getByLabelText(/ask a question/i),'What standards apply to toys?{Enter}');await screen.findByText('Need more details',{selector:'.answer-status'});
 await u.type(screen.getByLabelText(/ask a question/i),'How many days will BIS take to approve my licence?{Enter}');await screen.findByText(a.answer);
 const payload=JSON.parse(String((f.mock.calls[2]?.[1] as RequestInit).body));
 expect(payload).not.toHaveProperty('assistant_context');
});

it('Start over clears messages and active assistant context',async()=>{
 const clarification={...a,answer:'Need power',grounded:false,insufficient_evidence:false,needs_clarification:true,generation_mode:'clarification' as const,citations:[],assistant_context:{original_question:'What standards apply?',expected_slots:['power_type']},suggested_replies:['Non-electric']};
 mock(clarification);render(<App/>);const u=userEvent.setup();await u.click(screen.getByText(/battery-operated/i));await screen.findByText('Need more details',{selector:'.answer-status'});
 await u.click(screen.getByRole('button',{name:'Start over'}));
 expect(screen.getByText('Suggested questions')).toBeInTheDocument(); expect(screen.queryByText('Need power')).not.toBeInTheDocument();
});

it('renders accessible suggested standard replies and sends the chosen standard once',async()=>{
 const context={original_question:'Explain the standard',expected_slots:['standard_reference' as const],current_goal:'explain_standard' as const,referenced_standards:['IS 15644','IS 9873 Part 1']};
 const clarification={...a,answer:'Which Indian Standard would you like me to explain?',grounded:false,insufficient_evidence:false,needs_clarification:true,generation_mode:'clarification' as const,citations:[],suggested_replies:['IS 15644','IS 9873 Part 1'],assistant_context:context,answer_sections:[{type:'clarification' as const,title:'Need more details',content:'Which Indian Standard would you like me to explain?',items:[],citation_ids:[]}]};
 let chatCall=0;
 const f=vi.fn((url:string,init?:RequestInit)=>{
  if(url.includes('health'))return Promise.resolve(rep({status:'ready'}));
  chatCall+=1;
  return Promise.resolve(rep(chatCall===1?clarification:{...a,needs_clarification:false,answer:'IS 15644 is identified as the primary standard for electric toys.'}));
 });
 vi.stubGlobal('fetch',f);render(<App/>);const u=userEvent.setup();
 await u.type(screen.getByLabelText(/ask a question/i),'Explain the standard{Enter}');
 expect(await screen.findByRole('group',{name:'Suggested replies'})).toBeInTheDocument();
 await u.click(screen.getByRole('button',{name:'IS 15644'}));
 await screen.findByText(/primary standard for electric toys/i);
 const payload=JSON.parse(String((f.mock.calls[2]?.[1] as RequestInit).body));
 expect(payload.question).toBe('IS 15644');
 expect(payload.assistant_context).toEqual(context);
 expect(f).toHaveBeenCalledTimes(3);
});

it('displays ambiguous standard-reference clarification',async()=>{
 const clarification={...a,answer:'Which of the previously mentioned Indian Standards would you like me to explain?',grounded:false,insufficient_evidence:false,needs_clarification:true,generation_mode:'clarification' as const,citations:[],suggested_replies:['IS 15644','IS 9873 Part 1'],assistant_context:{referenced_standards:['IS 15644','IS 9873 Part 1'],expected_slots:['standard_reference' as const]}};
 mock(clarification);render(<App/>);await userEvent.setup().type(screen.getByLabelText(/ask a question/i),'Explain that standard{Enter}');
 expect(await screen.findByText('Need more details',{selector:'.answer-status'})).toBeInTheDocument();
 expect(screen.getByText(/previously mentioned Indian Standards/i)).toBeInTheDocument();
});

it('mode switching clears retained standard context',async()=>{
 const clarification={...a,answer:'Which Indian Standard would you like me to explain?',grounded:false,insufficient_evidence:false,needs_clarification:true,generation_mode:'clarification' as const,citations:[],suggested_replies:['IS 15644'],assistant_context:{expected_slots:['standard_reference' as const],referenced_standards:['IS 15644']}};
 mock(clarification);render(<App/>);const u=userEvent.setup();
 await u.type(screen.getByLabelText(/ask a question/i),'Explain the standard{Enter}');
 await screen.findByText('Need more details',{selector:'.answer-status'});
 await u.click(screen.getByRole('button',{name:'Compliance Wizard'}));
 await u.click(screen.getByRole('button',{name:'Ask a question'}));
 expect(screen.getByText('Suggested questions')).toBeInTheDocument();
 expect(screen.queryByText(/Which Indian Standard/i)).not.toBeInTheDocument();
});

it('keeps citations, page metadata and hides internal identifiers after a standard explanation',async()=>{
 mock({...a,answer:'IS 15644 is identified as the primary standard for electric toys.'});
 render(<App/>);await userEvent.setup().click(screen.getByText(/battery-operated/i));
 expect(await screen.findByText(/manual.pdf/)).toBeInTheDocument();
 expect(screen.getByText(/Page 4/)).toBeInTheDocument();
 expect(document.body).not.toHaveTextContent('secret');
});
