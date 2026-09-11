import { StatusBadge } from './StatusBadge';
export function ChatHeader({status}:{status:'ready'|'degraded'|'unavailable'}){return <header><div><h1>BIS AI Assistant</h1><p>Standards and certification guidance from indexed BIS documents</p></div><StatusBadge status={status}/></header>}
