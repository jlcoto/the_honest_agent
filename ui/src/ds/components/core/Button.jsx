import React from 'react';
import {Icon} from './Icon.jsx';
const SZ={sm:{h:28,px:10,fs:13,ic:14},md:{h:36,px:14,fs:14,ic:16}};
export function Button({variant='primary',size='md',icon,iconRight,disabled,children,onClick,type='button',style}){
  const [h,setH]=React.useState(false);const [p,setP]=React.useState(false);const s=SZ[size]||SZ.md;
  const V={
    primary:{bg:h?'var(--accent-hover)':'var(--accent)',fg:'var(--accent-fg)',bd:'transparent'},
    secondary:{bg:h?'var(--bg-sunken)':'var(--bg-surface)',fg:'var(--fg-1)',bd:'var(--border-2)'},
    ghost:{bg:h?'var(--bg-sunken)':'transparent',fg:'var(--fg-2)',bd:'transparent'},
  }[variant]||{};
  return <button type={type} disabled={disabled} onClick={onClick}
    onMouseEnter={()=>setH(true)} onMouseLeave={()=>{setH(false);setP(false)}} onMouseDown={()=>setP(true)} onMouseUp={()=>setP(false)}
    style={{display:'inline-flex',alignItems:'center',justifyContent:'center',gap:6,height:s.h,padding:'0 '+s.px+'px',borderRadius:'var(--radius-sm)',border:'1px solid '+V.bd,background:V.bg,color:V.fg,font:'500 '+s.fs+'px/1 var(--font-sans)',cursor:disabled?'not-allowed':'pointer',opacity:disabled?.45:1,transform:p&&!disabled?'translateY(1px)':'none',transition:'background var(--dur-fast) var(--ease-out)',whiteSpace:'nowrap',...style}}>
    {icon?<Icon name={icon} size={s.ic}/>:null}{children}{iconRight?<Icon name={iconRight} size={s.ic}/>:null}
  </button>;
}
