import React from 'react';
export function Card({title,subtitle,actions,children,padding=20,style}){
  return <section style={{background:'var(--bg-surface)',border:'1px solid var(--border-1)',borderRadius:'var(--radius-lg)',boxShadow:'var(--shadow-1)',padding,display:'flex',flexDirection:'column',gap:16,minWidth:0,...style}}>
    {(title||actions)?<header style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',gap:12}}>
      <div style={{display:'flex',flexDirection:'column',gap:2,minWidth:0}}>
        {title?<h3 style={{margin:0,font:'var(--type-h2)',color:'var(--fg-1)',letterSpacing:'-0.01em'}}>{title}</h3>:null}
        {subtitle?<p style={{margin:0,font:'var(--type-small)',color:'var(--fg-3)'}}>{subtitle}</p>:null}
      </div>
      {actions?<div style={{display:'flex',gap:8,alignItems:'center',flex:'none'}}>{actions}</div>:null}
    </header>:null}
    {children}
  </section>;
}
