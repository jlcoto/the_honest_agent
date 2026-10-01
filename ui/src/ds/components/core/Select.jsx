import React from 'react';
import {Icon} from './Icon.jsx';
export function Select({label,options,value,onChange,size='md',icon}){
  const h=size==='sm'?28:36;
  return <label style={{display:'inline-flex',flexDirection:'column',gap:6,minWidth:0}}>
    {label?<span style={{font:'var(--type-label)',color:'var(--fg-2)'}}>{label}</span>:null}
    <span style={{position:'relative',display:'inline-flex',alignItems:'center'}}>
      {icon?<span style={{position:'absolute',left:10,display:'flex',color:'var(--fg-3)',pointerEvents:'none'}}><Icon name={icon} size={14}/></span>:null}
      <select value={value} onChange={e=>onChange&&onChange(e.target.value)} style={{appearance:'none',WebkitAppearance:'none',height:h,padding:'0 32px 0 '+(icon?30:12)+'px',borderRadius:'var(--radius-sm)',border:'1px solid var(--border-2)',background:'var(--bg-surface)',color:'var(--fg-1)',font:'500 '+(size==='sm'?13:14)+'px/1 var(--font-sans)',cursor:'pointer',minWidth:0}}>
        {options.map(o=>typeof o==='string'?<option key={o} value={o}>{o}</option>:<option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <span style={{position:'absolute',right:10,display:'flex',color:'var(--fg-3)',pointerEvents:'none'}}><Icon name="chevron-down" size={14}/></span>
    </span>
  </label>;
}
