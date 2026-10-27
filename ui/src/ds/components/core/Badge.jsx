import React from 'react';
const T={
  neutral:{bg:'var(--bg-sunken)',fg:'var(--fg-2)',dot:'var(--fg-3)',ring:'var(--border-1)'},
  accent:{bg:'var(--accent-soft)',fg:'var(--accent)',dot:'var(--accent)'},
  correct:{bg:'var(--acc-correct-tint)',fg:'var(--acc-correct-ink)',dot:'var(--acc-correct)'},
  mostly:{bg:'var(--acc-mostly-tint)',fg:'var(--acc-mostly-ink)',dot:'var(--acc-mostly)'},
  partly:{bg:'var(--acc-partly-tint)',fg:'var(--acc-partly-ink)',dot:'var(--acc-partly)'},
  wrong:{bg:'var(--acc-wrong-tint)',fg:'var(--acc-wrong-ink)',dot:'var(--acc-wrong)'},
};
export function Badge({tone='neutral',dot,children,mono,size='md'}){
  const t=T[tone]||T.neutral;const sm=size==='sm';
  // Never wider than its container: a long label ends in "…" and shows in full on hover.
  const fullOnHover=e=>{const s=e.currentTarget.lastChild;e.currentTarget.title=s.scrollWidth>s.clientWidth?s.textContent:'';};
  return <span onMouseEnter={fullOnHover} style={{display:'inline-flex',alignItems:'center',gap:sm?4:6,height:sm?18:22,maxWidth:'100%',minWidth:0,padding:sm?'0 6px':'0 8px',borderRadius:'var(--radius-pill)',background:t.bg,boxShadow:t.ring?'inset 0 0 0 1px '+t.ring:undefined,color:t.fg,font:'500 '+(sm?11:12)+'px/1 '+(mono?'var(--font-mono)':'var(--font-sans)'),whiteSpace:'nowrap'}}>
    {dot?<span style={{width:sm?5:6,height:sm?5:6,borderRadius:3,background:t.dot,flex:'none'}}/>:null}<span style={{minWidth:0,overflow:'hidden',textOverflow:'ellipsis'}}>{children}</span>
  </span>;
}
