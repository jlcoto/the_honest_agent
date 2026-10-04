import React from 'react';
const T={
  neutral:{bg:'var(--bg-sunken)',fg:'var(--fg-2)',dot:'var(--fg-3)',ring:'var(--border-1)'},
  accent:{bg:'var(--accent-soft)',fg:'var(--accent)',dot:'var(--accent)'},
  correct:{bg:'var(--acc-correct-tint)',fg:'var(--acc-correct-ink)',dot:'var(--acc-correct)'},
  mostly:{bg:'var(--acc-mostly-tint)',fg:'var(--acc-mostly-ink)',dot:'var(--acc-mostly)'},
  partly:{bg:'var(--acc-partly-tint)',fg:'var(--acc-partly-ink)',dot:'var(--acc-partly)'},
  wrong:{bg:'var(--acc-wrong-tint)',fg:'var(--acc-wrong-ink)',dot:'var(--acc-wrong)'},
};
export function Badge({tone='neutral',dot,children,mono}){
  const t=T[tone]||T.neutral;
  return <span style={{display:'inline-flex',alignItems:'center',gap:6,height:22,padding:'0 8px',borderRadius:'var(--radius-pill)',background:t.bg,boxShadow:t.ring?'inset 0 0 0 1px '+t.ring:undefined,color:t.fg,font:'500 12px/1 '+(mono?'var(--font-mono)':'var(--font-sans)'),whiteSpace:'nowrap'}}>
    {dot?<span style={{width:6,height:6,borderRadius:3,background:t.dot}}/>:null}{children}
  </span>;
}
