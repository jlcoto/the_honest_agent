import React from 'react';
import {Icon} from './Icon.jsx';
export function Checkbox({checked,onChange,label,disabled}){
  return <label style={{display:'inline-flex',alignItems:'center',gap:8,cursor:disabled?'not-allowed':'pointer',opacity:disabled?.45:1,font:'400 14px/1.3 var(--font-sans)',color:'var(--fg-1)'}}>
    <span style={{width:16,height:16,borderRadius:4,border:'1px solid '+(checked?'var(--accent)':'var(--border-2)'),background:checked?'var(--accent)':'var(--bg-surface)',display:'inline-flex',alignItems:'center',justifyContent:'center',color:'var(--accent-fg)',flex:'none'}}>{checked?<Icon name="check" size={12}/>:null}</span>
    <input type="checkbox" checked={!!checked} disabled={disabled} onChange={e=>onChange&&onChange(e.target.checked)} style={{position:'absolute',opacity:0,width:0,height:0}}/>
    {label}
  </label>;
}
