import React from 'react';
import {Icon} from './Icon.jsx';
export function Input({label,icon,placeholder,value,onChange,type='text',hint,invalid,disabled}){
  const [f,setF]=React.useState(false);
  return <label style={{display:'flex',flexDirection:'column',gap:6,minWidth:0}}>
    {label?<span style={{font:'var(--type-label)',color:'var(--fg-2)'}}>{label}</span>:null}
    <span style={{display:'flex',alignItems:'center',gap:8,height:36,padding:'0 12px',borderRadius:'var(--radius-sm)',background:disabled?'var(--bg-sunken)':'var(--bg-surface)',border:'1px solid '+(invalid?'var(--acc-wrong)':f?'var(--border-focus)':'var(--border-2)'),boxShadow:f?'var(--shadow-focus)':'none',color:'var(--fg-3)'}}>
      {icon?<Icon name={icon} size={16}/>:null}
      <input type={type} placeholder={placeholder} value={value} onChange={onChange} disabled={disabled} onFocus={()=>setF(true)} onBlur={()=>setF(false)} style={{flex:1,minWidth:0,border:0,outline:0,background:'transparent',color:'var(--fg-1)',font:'400 14px/1 var(--font-sans)'}}/>
    </span>
    {hint?<span style={{font:'var(--type-small)',color:invalid?'var(--acc-wrong-ink)':'var(--fg-3)'}}>{hint}</span>:null}
  </label>;
}
