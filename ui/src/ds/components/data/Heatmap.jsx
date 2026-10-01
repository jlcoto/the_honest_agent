import React from 'react';
import {bucketOf,BUCKET_COLOR,BUCKET_LABEL,BUCKETS,pct} from './scale.js';
import {Tabs} from '../core/Tabs.jsx';
import {Icon} from '../core/Icon.jsx';

const mean=a=>{const v=a.filter(x=>x!=null&&!isNaN(x));return v.length?v.reduce((s,x)=>s+x,0)/v.length:null;};
const overallOf=(a,p)=>(a==null||p==null)?(a??p??null):(a+p)/2;
const DATE_TIME=/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/;
const headLabel=c=>{const m=String(c).match(DATE_TIME);return m?m[1]:String(c);};
const METRICS=[{id:'overall',label:'Combined'},{id:'accuracy',label:'Accuracy'},{id:'provenance',label:'Provenance'}];
const MLABEL={overall:'Combined',accuracy:'Accuracy',provenance:'Provenance',values:'Score'};
const colMean=(kids,key,n)=>Array.from({length:n},(_,i)=>mean(kids.map(k=>k[key]?k[key][i]:null)));

export function Heatmap({rows,columns,metric,defaultMetric='overall',onMetricChange,showToggle,showSummary=true,summaryLabel='Overall',rowHeader='Quiz',groupBy,groupLabel,defaultExpanded=[],threshold=0.8,showTotals=true,totalsLabel='Overall',cellWidth=40,cellHeight=36,rowLabelWidth=220,showLegend=false,onCellClick}){
  const dual=rows.length>0&&rows[0].accuracy!=null;
  const [mLocal,setMLocal]=React.useState(defaultMetric);
  const m=dual?(metric||mLocal):'values';
  const setM=id=>{setMLocal(id);onMetricChange&&onMetricChange(id);};
  const [tip,setTip]=React.useState(null);
  const [open,setOpen]=React.useState(()=>new Set(defaultExpanded));
  const toggle=g=>setOpen(s=>{const n=new Set(s);n.has(g)?n.delete(g):n.add(g);return n;});
  const n=columns.length;

  const valueAt=(r,i)=>{
    if(!dual)return r.values[i];
    if(m==='accuracy')return r.accuracy[i];
    if(m==='provenance')return r.provenance[i];
    return overallOf(r.accuracy[i],r.provenance[i]);
  };
  const summaryOf=r=>{
    if(!dual)return mean(r.values);
    const a=mean(r.accuracy),p=mean(r.provenance);
    return m==='accuracy'?a:m==='provenance'?p:overallOf(a,p);
  };

  // Build display list: plain rows, or group rows (aggregated) + expanded children
  const display=React.useMemo(()=>{
    if(!groupBy)return rows.map(r=>({kind:'row',r}));
    const order=[];const map={};
    rows.forEach(r=>{const g=r[groupBy]??'Other';if(!map[g]){map[g]=[];order.push(g);}map[g].push(r);});
    const out=[];
    order.forEach(g=>{const kids=map[g];
      const agg=dual?{label:g,accuracy:colMean(kids,'accuracy',n),provenance:colMean(kids,'provenance',n)}:{label:g,values:colMean(kids,'values',n)};
      out.push({kind:'group',r:agg,g,kids});
      if(open.has(g))kids.forEach(k=>out.push({kind:'child',r:k,g}));
    });
    return out;
  },[rows,groupBy,open,dual,n]);

  const totals=React.useMemo(()=>{const agg=dual?{label:totalsLabel,accuracy:colMean(rows,'accuracy',n),provenance:colMean(rows,'provenance',n)}:{label:totalsLabel,values:colMean(rows,'values',n)};return {kind:'group',r:agg,kids:rows,g:null};},[rows,dual,n,totalsLabel]);

  const show=(e,item,col,i)=>{
    const r=item.r;const rc=e.currentTarget.getBoundingClientRect();
    const v=i==null?summaryOf(r):valueAt(r,i);
    const lines=[];
    if(dual&&m==='overall'){
      const a=i==null?mean(r.accuracy):r.accuracy[i];const p=i==null?mean(r.provenance):r.provenance[i];
      lines.push(['Accuracy',pct(a)],['Provenance',pct(p)]);
    }
    let note=null;
    if(item.kind==='group'){
      const vals=item.kids.map(k=>i==null?summaryOf(k):valueAt(k,i)).filter(x=>x!=null);
      const below=vals.filter(x=>x<threshold).length;
      note=below+' of '+vals.length+' quizzes below '+Math.round(threshold*100)+'%';
    }
    setTip({x:rc.left+rc.width/2,y:rc.top,row:r.label,col,v,b:bucketOf(v),lines,note});
  };

  const maxLen=Math.max(summaryLabel.length,...columns.map(c=>headLabel(c).length));
  const rise=Math.ceil(maxLen*7.6*0.71);
  const headerH=Math.max(48,rise+16);
  const GAP=1;const AX='color-mix(in oklch,var(--fg-3) 60%,var(--fg-2))';const axG='linear-gradient('+AX+','+AX+')';
  const thBase={padding:0,borderBottom:'2px solid '+AX,backgroundColor:'transparent',verticalAlign:'bottom'};

  const rotated=(t,sans)=><div style={{position:'relative',height:headerH,width:cellWidth}}>
    <span style={{position:'absolute',left:'50%',bottom:8,transformOrigin:'0 100%',transform:'rotate(-45deg)',whiteSpace:'nowrap',font:sans?'500 12px/1 var(--font-sans)':'400 11px/1 var(--font-sans)',fontVariantNumeric:'tabular-nums',color:sans?'var(--fg-1)':'var(--fg-2)'}}>{t}</span>
  </div>;
  const hoverOn=e=>{e.currentTarget.style.boxShadow='inset 0 0 0 2px var(--fg-1)';};
  const hoverOff=e=>{e.currentTarget.style.boxShadow='none';};
  const box=(v,onEnter,onClick)=>{const b=bucketOf(v);
    return <div onMouseEnter={onEnter} onMouseLeave={()=>setTip(null)} onClick={onClick} onMouseOver={hoverOn} onMouseOut={hoverOff}
      style={{width:cellWidth-1,height:cellHeight-1,marginRight:1,background:b?BUCKET_COLOR[b]:'var(--chart-empty)',cursor:onClick?'pointer':'default',transition:'box-shadow var(--dur-fast) var(--ease-out)'}}/>;};

  const labelCell=item=>{
    const r=item.r;const isG=item.kind==='group';const isC=item.kind==='child';const on=isG&&open.has(item.g);
    const sub=isG?(item.kids.length+(item.kids.length===1?' quiz':' quizzes')):(isC&&groupBy==='sublabel'?null:r.sublabel);
    return <td onClick={isG?()=>toggle(item.g):undefined} aria-expanded={isG?on:undefined}
      style={{position:'sticky',left:0,zIndex:1,background:'var(--bg-surface)',minWidth:rowLabelWidth,maxWidth:rowLabelWidth,height:cellHeight,padding:isC?'0 12px 0 36px':'0 12px',borderBottom:'1px solid var(--border-1)',cursor:isG?'pointer':'default',userSelect:isG?'none':undefined}}>
      <div style={{display:'flex',alignItems:'center',gap:6,minWidth:0}}>
        {isG?<span style={{display:'inline-flex',color:'var(--fg-2)',transform:on?'rotate(90deg)':'none',transition:'transform var(--dur-base) var(--ease-out)'}}><Icon name="chevron-right" size={14}/></span>:null}
        <div style={{minWidth:0}}>
          <div title={r.label} style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',font:(isG?'500':'400')+' '+(isC?13:14)+'px/1.25 '+(isC?'var(--font-mono)':'var(--font-sans)'),color:isC?'var(--fg-2)':'var(--fg-1)'}}>{r.label}</div>
          {sub?<div style={{font:'400 11px/1.3 var(--font-mono)',color:'var(--fg-3)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{sub}</div>:null}
        </div>
      </div>
    </td>;
  };

  return <div style={{display:'flex',flexDirection:'column',gap:4,minWidth:0}}>
    {(showToggle??dual)?<div style={{display:'flex',justifyContent:'flex-end'}}><Tabs items={METRICS} value={m} onChange={setM}/></div>:null}
    <div style={{overflowX:'auto',minWidth:0}}>
      <table style={{borderCollapse:'separate',borderSpacing:0,margin:'0 auto',paddingRight:rise+12,paddingLeft:rise+12}}>
        <thead><tr>
          <th style={{...thBase,backgroundColor:'var(--bg-surface)',position:'sticky',left:0,zIndex:2,textAlign:'left',minWidth:rowLabelWidth,maxWidth:rowLabelWidth,padding:'0 12px 8px 12px',font:'700 11px/1 var(--font-sans)',letterSpacing:'var(--ls-caps)',textTransform:'uppercase',color:'var(--fg-1)'}}>{groupBy?(groupLabel||'Category')+' / '+rowHeader:rowHeader}</th>
          {columns.map((c,i)=><th key={i} style={showSummary&&i===columns.length-1?{...thBase,borderBottom:'none',backgroundImage:axG,backgroundRepeat:'no-repeat',backgroundSize:'calc(100% - 1px) 2px',backgroundPosition:'left bottom'}:thBase}>{rotated(headLabel(c))}</th>)}
          {showSummary?<th style={{...thBase,paddingLeft:GAP,borderBottom:'none',backgroundImage:axG,backgroundRepeat:'no-repeat',backgroundSize:(cellWidth-1)+'px 2px',backgroundPosition:GAP+'px bottom'}}>{rotated(summaryLabel,true)}</th>:null}
        </tr></thead>
        <tbody>{display.map((item,ri)=>{const r=item.r;
          const click=onCellClick&&item.kind!=='group'?(ci,v)=>()=>onCellClick(r,columns[ci],v,m):null;
          return <tr key={item.kind+':'+r.label+':'+ri}>
            {labelCell(item)}
            {columns.map((_,ci)=>{const v=valueAt(r,ci);return <td key={ci} style={{padding:ci===0?'0 0 1px 2px':'0 0 1px',...(ci===0?{backgroundImage:axG,backgroundRepeat:'no-repeat',backgroundSize:showTotals&&ri===display.length-1?'2px calc(100% - 1px)':'2px 100%',backgroundPosition:'left top'}:{})}}>{box(v,e=>show(e,item,columns[ci],ci),click?click(ci,v):undefined)}</td>;})}
            {showSummary?<td style={{padding:'0 0 1px '+GAP+'px'}}>{box(summaryOf(r),e=>show(e,item,summaryLabel,null))}</td>:null}
          </tr>;})}</tbody>
        {showTotals?<tfoot><tr>
          <td style={{position:'sticky',left:0,zIndex:1,background:'var(--bg-surface)',minWidth:rowLabelWidth,maxWidth:rowLabelWidth,height:cellHeight+GAP,padding:GAP+'px 12px 0',verticalAlign:'middle'}}>
            <div style={{font:'700 14px/1.25 var(--font-sans)',color:'var(--fg-1)'}}>{totalsLabel}</div>
          </td>
          {columns.map((_,ci)=><td key={ci} style={{padding:GAP+'px 0 0 '+(ci===0?2:0)+'px',...(ci===0?{backgroundImage:axG,backgroundRepeat:'no-repeat',backgroundSize:'2px calc(100% - '+GAP+'px)',backgroundPosition:'left bottom'}:{})}}>{box(valueAt(totals.r,ci),e=>show(e,totals,columns[ci],ci))}</td>)}
          {showSummary?<td style={{padding:GAP+'px 0 0 '+GAP+'px'}}>{box(summaryOf(totals.r),e=>show(e,totals,summaryLabel,null))}</td>:null}
        </tr></tfoot>:null}
      </table>
    </div>
    {showLegend?<div style={{display:'flex',flexWrap:'wrap',gap:'4px 16px',font:'400 12px/1.4 var(--font-sans)',color:'var(--fg-2)'}}>
      {BUCKETS.map(k=><span key={k} style={{display:'inline-flex',alignItems:'center',gap:6}}><span style={{width:10,height:10,background:BUCKET_COLOR[k]}}/>{BUCKET_LABEL[k]}</span>)}
      <span style={{display:'inline-flex',alignItems:'center',gap:6}}><span style={{width:10,height:10,background:'var(--chart-empty)'}}/>No run</span>
    </div>:null}
    {tip?<div style={{position:'fixed',left:tip.x,top:tip.y-8,transform:'translate(-50%,-100%)',zIndex:50,padding:'8px 10px',borderRadius:8,background:'var(--bg-inverse)',color:'var(--fg-inverse)',font:'400 12px/1.5 var(--font-sans)',boxShadow:'var(--shadow-2)',pointerEvents:'none',minWidth:150,whiteSpace:'nowrap'}}>
      <div style={{fontWeight:500}}>{tip.row}</div>
      <div style={{fontFamily:'var(--font-mono)',opacity:.7,fontSize:11}}>{tip.col}</div>
      <div style={{display:'flex',justifyContent:'space-between',gap:16,marginTop:4}}><span>{MLABEL[m]}</span><span style={{fontFamily:'var(--font-mono)',fontWeight:500}}>{pct(tip.v)}</span></div>
      {tip.lines.map(([k,v])=><div key={k} style={{display:'flex',justifyContent:'space-between',gap:16,opacity:.8}}><span>{k}</span><span style={{fontFamily:'var(--font-mono)'}}>{v}</span></div>)}
      <div style={{opacity:.7,marginTop:2}}>{tip.b?BUCKET_LABEL[tip.b]:'No run'}</div>
      {tip.note?<div style={{marginTop:4,paddingTop:4,borderTop:'1px solid color-mix(in oklch,var(--fg-inverse) 20%,transparent)'}}>{tip.note}</div>:null}
    </div>:null}
  </div>;
}
