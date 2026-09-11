export function ErrorMessage({message,onRetry}:{message:string;onRetry:()=>void}){return <div className="error" role="alert">{message} <button onClick={onRetry}>Retry</button></div>}
