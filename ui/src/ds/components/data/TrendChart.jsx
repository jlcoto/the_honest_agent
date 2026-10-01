import React from 'react';
import {bucketOf,BUCKET_COLOR} from './scale.js';
const SERIES=['var(--chart-neutral)','var(--green-500)','var(--green-300)','var(--fg-3)'];
export function TrendChart({series,labels,threshold,height=220,min=0,max=1,colorDots=true}){
  const ref=React.useRef(null);const [w,setW]=React.useState(600);const [hi,setHi]=React.useState(null);
  React.useEffect(()=>{if(!ref.current)return;const ro=new ResizeObserver(e=>setW(Math.max(200,e[0].contentRect.width)));ro.observe(ref.current);return()=>ro.disconnect();},[]);
  const L=40,R=12,T=10,B=26,W=w-L-R,H=height-T-B,n=labels.length;
  const x=i=>L+(n<2?W/2:i*W/(n-1));const y=v=>T+H-(v-min)/(max-min)*H;
  const ticks=[0,.25,.5,.75,1].map(t=>min+t*(max-min));
  const every=Math.ceil(n/Math.max(1,Math.floor(W/64)));
  return <div ref={ref} style={{width:'100%',position:'relative'}}>
    <svg width={w} height={height} style={{display:'block'}} onMouseLeave={()=>setHi(null)}
      onMouseMove={e=>{const r=e.currentTarget.getBoundingClientRect();const i=Math.round((e.clientX-r.left-L)/(W/Math.max(1,n-1)));setHi(Math.max(0,Math.min(n-1,i)));}}>
      {ticks.map(t=><g key={t}><line x1={L} x2={L+W} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)"/><text x={L-8} y={y(t)+4} textAnchor="end" style={{font:'400 11px var(--font-mono)',fill:'var(--chart-axis)'}}>{Math.round(t*100)+'%'}</text></g>)}
      {labels.map((l,i)=>i%every===0?<text key={i} x={x(i)} y={height-6} textAnchor="middle" style={{font:'400 11px var(--font-mono)',fill:'var(--chart-axis)'}}>{l}</text>:null)}
      {threshold!=null?<g><line x1={L} x2={L+W} y1={y(threshold)} y2={y(threshold)} stroke="var(--acc-wrong)" strokeDasharray="4 4" strokeWidth="1.25"/><text x={L+W} y={y(threshold)-6} textAnchor="end" style={{font:'500 11px var(--font-sans)',fill:'var(--acc-wrong-ink)'}}>{'min score '+Math.round(threshold*100)+'%'}</text></g>:null}
      {hi!=null?<line x1={x(hi)} x2={x(hi)} y1={T} y2={T+H} stroke="var(--border-2)"/>:null}
      {series.map((s,si)=>{const c=s.color||SERIES[si%SERIES.length];const d=s.values.map((v,i)=>v==null?'':((i&&s.values[i-1]!=null?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1))).join(' ');
        return <g key={s.id||si}><path d={d} fill="none" stroke={c} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>
          {s.values.map((v,i)=>v==null?null:<circle key={i} cx={x(i)} cy={y(v)} r={hi===i?4.5:3} fill={colorDots&&series.length===1?BUCKET_COLOR[bucketOf(v)]:c} stroke="var(--bg-surface)" strokeWidth="1.5"/>)}</g>;})}
    </svg>
    {hi!=null?<div style={{position:'absolute',top:0,left:Math.min(x(hi)+10,w-170),padding:'8px 10px',borderRadius:8,background:'var(--bg-inverse)',color:'var(--fg-inverse)',font:'400 12px/1.5 var(--font-sans)',boxShadow:'var(--shadow-2)',pointerEvents:'none',minWidth:130}}>
      <div style={{fontFamily:'var(--font-mono)',opacity:.7,marginBottom:2}}>{labels[hi]}</div>
      {series.map((s,si)=><div key={si} style={{display:'flex',justifyContent:'space-between',gap:12}}><span>{s.label}</span><span style={{fontFamily:'var(--font-mono)'}}>{s.values[hi]==null?'—':(s.values[hi]*100).toFixed(1)+'%'}</span></div>)}
    </div>:null}
  </div>;
}
