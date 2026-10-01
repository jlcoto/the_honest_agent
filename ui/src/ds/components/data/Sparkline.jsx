import React from 'react';
import {bucketOf,BUCKET_COLOR} from './scale.js';
export function Sparkline({values,width=96,height=28,color='var(--chart-neutral)',min=0,max=1,showEnd=true}){
  const v=(values||[]).filter(x=>x!=null);if(v.length<2)return <svg width={width} height={height}/>;
  const pad=3,W=width-pad*2,H=height-pad*2;
  const pts=v.map((y,i)=>[pad+i*W/(v.length-1),pad+H-(Math.max(min,Math.min(max,y))-min)/(max-min)*H]);
  const d=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const last=pts[pts.length-1];const b=bucketOf(v[v.length-1]);
  return <svg width={width} height={height} viewBox={'0 0 '+width+' '+height} style={{display:'block',overflow:'visible'}}>
    <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round"/>
    {showEnd?<circle cx={last[0]} cy={last[1]} r="2.5" fill={b?BUCKET_COLOR[b]:color}/>:null}
  </svg>;
}
