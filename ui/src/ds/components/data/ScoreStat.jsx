import React from 'react';
import {bucketOf,BUCKET_COLOR,pct} from './scale.js';
import {Sparkline} from './Sparkline.jsx';
export function ScoreStat({label,value,format='percent',delta,deltaLabel='vs previous run',caption,alert,spark,size='md'}){
  const isPct=format==='percent';const isCount=format==='count';const b=isPct?bucketOf(value):null;
  const up=delta!=null&&delta>0;const flat=delta!=null&&Math.abs(delta)<(isCount?0.5:0.0005);
  const dColor=flat?'var(--fg-3)':up?'var(--acc-correct-ink)':'var(--acc-wrong-ink)';
  const shown=isPct?pct(value):typeof value==='string'?value.replace(/\s*\/\s*/g,' / '):value;
  // A count changes by whole evals (+1, −2); a percentage by points (+2.1 pp).
  const dText=isCount?(flat?'±0':(up?'+':'−')+Math.abs(Math.round(delta))):(flat?'±0.0':(up?'+':'−')+Math.abs(delta*100).toFixed(1))+(isPct?' pp':'');
  // A count's caption (its percentage) stays next to the change; other formats show one or the other.
  const showCaption=caption&&(delta==null||isCount);
  return <div style={{display:'flex',flexDirection:'column',gap:8,minWidth:0}}>
    <div style={{display:'flex',alignItems:'center',gap:6,font:'var(--type-label)',color:'var(--fg-2)'}}>
      {b?<span style={{width:8,height:8,borderRadius:2,background:BUCKET_COLOR[b]}}/>:null}{label}
    </div>
    <div style={{display:'flex',alignItems:'flex-end',justifyContent:'space-between',gap:'8px 10px',flexWrap:'wrap',minWidth:0}}>
      <span style={{font:'500 '+(size==='lg'?48:28)+'px/1 var(--font-display)',letterSpacing:'-0.02em',color:'var(--fg-1)',fontVariantNumeric:'tabular-nums',whiteSpace:'nowrap'}}>{shown}</span>
      {spark?<Sparkline values={spark} width={56} height={24}/>:null}
    </div>
    {(delta!=null||showCaption)?<div style={{display:'flex',flexWrap:'wrap',gap:6,alignItems:'baseline',font:'var(--type-small)',color:'var(--fg-3)'}}>
      {delta!=null?<span style={{font:'500 12px/1 var(--font-mono)',color:dColor,whiteSpace:'nowrap'}}>{dText}</span>:null}
      {delta!=null?<span style={{whiteSpace:'nowrap'}}>{deltaLabel}</span>:null}
      {delta!=null&&showCaption?<span>·</span>:null}{showCaption?<span>{caption}</span>:null}
    </div>:null}
    {alert?<div style={{font:'var(--type-small)',color:'var(--acc-wrong-ink)'}}>{alert}</div>:null}
  </div>;
}
