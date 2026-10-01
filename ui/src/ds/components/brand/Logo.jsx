import React from 'react';
export function Logo({markSrc='assets/logo-mark.png',size=32,wordmark=true,stacked,inverse,textSize}){
  return <span style={{display:'inline-flex',alignItems:'center',flexDirection:stacked?'column':'row',gap:stacked?8:10,color:inverse?'#F3F2EC':'var(--fg-1)'}}>
    <img src={markSrc} alt={wordmark?'':'The Honest Agent'} height={size} style={{display:'block',height:size,width:'auto'}}/>
    {wordmark?<span style={{font:'600 '+(textSize||Math.round(size*0.5))+'px/1 var(--font-display)',letterSpacing:'-0.02em',whiteSpace:'nowrap'}}>The Honest Agent</span>:null}
  </span>;
}
