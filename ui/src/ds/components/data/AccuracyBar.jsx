import React from 'react';
import {BUCKETS,BUCKET_COLOR,BUCKET_LABEL} from './scale.js';
export function AccuracyBar({counts,height=10,showLegend=false,showTotal=false}){
  const total=BUCKETS.reduce((s,k)=>s+(counts[k]||0),0)||1;
  return <div style={{display:'flex',flexDirection:'column',gap:10,minWidth:0}}>
    <div style={{display:'flex',gap:2,height,borderRadius:height/2,overflow:'hidden',background:'var(--chart-empty)'}}>
      {BUCKETS.map(k=>counts[k]?<div key={k} title={BUCKET_LABEL[k]+': '+counts[k]} style={{flex:counts[k]+' 0 0',background:BUCKET_COLOR[k]}}/>:null)}
    </div>
    {showLegend?<div style={{display:'flex',flexWrap:'wrap',gap:'6px 16px',font:'var(--type-small)',color:'var(--fg-2)'}}>
      {BUCKETS.map(k=><span key={k} style={{display:'inline-flex',alignItems:'center',gap:6}}><span style={{width:8,height:8,borderRadius:2,background:BUCKET_COLOR[k]}}/>{BUCKET_LABEL[k]}<span style={{font:'500 12px/1 var(--font-mono)',color:'var(--fg-1)'}}>{counts[k]||0}</span></span>)}
      {showTotal?<span style={{marginLeft:'auto',font:'500 12px/1.45 var(--font-mono)',color:'var(--fg-3)'}}>{total} total</span>:null}
    </div>:null}
  </div>;
}
