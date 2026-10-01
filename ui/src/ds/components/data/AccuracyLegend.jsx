import React from 'react';
import {BUCKETS,BUCKET_COLOR,BUCKET_LABEL} from './scale.js';
const RANGE={correct:'≥ 95%',mostly:'75–95%',partly:'40–75%',wrong:'< 40%'};
export function AccuracyLegend({showRanges=true,compact}){
  return <div style={{display:'flex',flexWrap:'wrap',gap:compact?'4px 12px':'6px 18px',font:(compact?'400 12px':'400 13px')+'/1.4 var(--font-sans)',color:'var(--fg-2)'}}>
    {BUCKETS.map(k=><span key={k} style={{display:'inline-flex',alignItems:'center',gap:6}}>
      <span style={{width:10,height:10,borderRadius:3,background:BUCKET_COLOR[k]}}/>{BUCKET_LABEL[k]}
      {showRanges?<span style={{font:'400 12px/1 var(--font-mono)',color:'var(--fg-3)'}}>{RANGE[k]}</span>:null}
    </span>)}
  </div>;
}
