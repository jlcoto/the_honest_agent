import React from 'react';
export function Tooltip({content,children,side='top'}){
  const [o,setO]=React.useState(false);
  const pos=side==='bottom'?{top:'calc(100% + 6px)'}:{bottom:'calc(100% + 6px)'};
  return <span style={{position:'relative',display:'inline-flex'}} onMouseEnter={()=>setO(true)} onMouseLeave={()=>setO(false)} onFocus={()=>setO(true)} onBlur={()=>setO(false)}>
    {children}
    {o?<span role="tooltip" style={{position:'absolute',left:'50%',transform:'translateX(-50%)',...pos,zIndex:20,padding:'6px 8px',borderRadius:'var(--radius-xs)',background:'var(--bg-inverse)',color:'var(--fg-inverse)',font:'400 12px/1.35 var(--font-sans)',whiteSpace:'nowrap',boxShadow:'var(--shadow-2)',pointerEvents:'none'}}>{content}</span>:null}
  </span>;
}
