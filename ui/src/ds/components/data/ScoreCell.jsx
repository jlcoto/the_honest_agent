import React from 'react';
import {bucketOf,BUCKET_COLOR,pct} from './scale.js';
export function ScoreCell({score,threshold,width=64}){
  const b=bucketOf(score);const below=threshold!=null&&score!=null&&score<threshold;
  return <span style={{display:'inline-flex',alignItems:'center',gap:8}}>
    <span style={{position:'relative',width,height:6,borderRadius:3,background:'var(--chart-empty)',overflow:'visible'}}>
      <span style={{position:'absolute',left:0,top:0,bottom:0,width:Math.max(0,Math.min(1,score||0))*100+'%',borderRadius:3,background:b?BUCKET_COLOR[b]:'transparent'}}/>
      {threshold!=null?<span style={{position:'absolute',left:threshold*100+'%',top:-3,bottom:-3,width:1.5,background:'var(--fg-1)',opacity:.55}}/>:null}
    </span>
    <span style={{font:'500 13px/1 var(--font-mono)',color:below?'var(--acc-wrong-ink)':'var(--fg-1)',fontVariantNumeric:'tabular-nums',minWidth:44,textAlign:'right'}}>{pct(score)}</span>
  </span>;
}
