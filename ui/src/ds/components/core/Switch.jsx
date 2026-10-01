import React from 'react';
export function Switch({checked,onChange,label,disabled}){
  return <label style={{display:'inline-flex',alignItems:'center',gap:8,cursor:disabled?'not-allowed':'pointer',opacity:disabled?.45:1,font:'400 14px/1.3 var(--font-sans)',color:'var(--fg-1)'}}>
    <span style={{position:'relative',width:30,height:18,borderRadius:9,background:checked?'var(--accent)':'var(--border-2)',transition:'background var(--dur-base) var(--ease-out)',flex:'none'}}>
      <span style={{position:'absolute',top:2,left:checked?14:2,width:14,height:14,borderRadius:7,background:'var(--white)',boxShadow:'var(--shadow-1)',transition:'left var(--dur-base) var(--ease-out)'}}/>
    </span>
    <input type="checkbox" role="switch" checked={!!checked} disabled={disabled} onChange={e=>onChange&&onChange(e.target.checked)} style={{position:'absolute',opacity:0,width:0,height:0}}/>
    {label}
  </label>;
}
