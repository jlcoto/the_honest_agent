import React from 'react';
import {Icon} from './Icon.jsx';
export function IconButton({icon,label,variant='ghost',size='md',onClick,active,disabled}){
  const [h,setH]=React.useState(false);const d=size==='sm'?28:36;
  const bg=active?'var(--accent-soft)':variant==='secondary'?(h?'var(--bg-sunken)':'var(--bg-surface)'):(h?'var(--bg-sunken)':'transparent');
  return <button type="button" aria-label={label} title={label} onClick={onClick} disabled={disabled}
    onMouseEnter={()=>setH(true)} onMouseLeave={()=>setH(false)}
    style={{width:d,height:d,display:'inline-flex',alignItems:'center',justifyContent:'center',borderRadius:'var(--radius-sm)',border:variant==='secondary'?'1px solid var(--border-2)':'1px solid transparent',background:bg,color:active?'var(--accent)':'var(--fg-2)',cursor:disabled?'not-allowed':'pointer',opacity:disabled?.45:1,padding:0,transition:'background var(--dur-fast) var(--ease-out)'}}>
    <Icon name={icon} size={size==='sm'?14:16}/>
  </button>;
}
