import React from 'react';
export function Tabs({items,value,onChange,variant='segmented'}){
  if(variant==='underline'){
    return <div role="tablist" style={{display:'flex',gap:20,borderBottom:'1px solid var(--border-1)'}}>
      {items.map(it=>{const on=it.id===value;return <button key={it.id} role="tab" aria-selected={on} onClick={()=>onChange&&onChange(it.id)} style={{background:'none',border:0,padding:'10px 0',marginBottom:-1,borderBottom:'2px solid '+(on?'var(--accent)':'transparent'),color:on?'var(--fg-1)':'var(--fg-3)',font:'500 14px/1 var(--font-sans)',cursor:'pointer'}}>{it.label}</button>;})}
    </div>;
  }
  return <div role="tablist" style={{display:'inline-flex',gap:2,padding:3,background:'var(--bg-sunken)',borderRadius:'var(--radius-sm)',border:'1px solid var(--border-1)'}}>
    {items.map(it=>{const on=it.id===value;return <button key={it.id} role="tab" aria-selected={on} onClick={()=>onChange&&onChange(it.id)} style={{height:26,padding:'0 10px',border:0,borderRadius:6,background:on?'var(--bg-surface)':'transparent',boxShadow:on?'var(--shadow-1)':'none',color:on?'var(--fg-1)':'var(--fg-2)',font:'500 13px/1 var(--font-sans)',cursor:'pointer'}}>{it.label}</button>;})}
  </div>;
}
