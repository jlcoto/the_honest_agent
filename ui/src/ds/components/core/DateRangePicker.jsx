import React from 'react';
import {Icon} from './Icon.jsx';
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONL=['January','February','March','April','May','June','July','August','September','October','November','December'];
const iso=(y,m,d)=>{const t=new Date(Date.UTC(y,m,d));return t.toISOString().slice(0,10);};
const parse=s=>{const [y,m,d]=s.split('-').map(Number);return {y,m:m-1,d};};
const addDays=(s,n)=>{const x=parse(s);return iso(x.y,x.m,x.d+n);};
const short=s=>{const x=parse(s);return x.d+' '+MON[x.m];};
const todayIso=()=>{const t=new Date();return iso(t.getFullYear(),t.getMonth(),t.getDate());};
const DEFAULT_PRESETS=[{label:'Last 7 days',days:7},{label:'Last 30 days',days:30},{label:'Last 90 days',days:90}];
export function DateRangePicker({value,onChange,dates=[],presets=DEFAULT_PRESETS,today,align='right'}){
  const now=today||todayIso();
  const [open,setOpen]=React.useState(false);
  const [pending,setPending]=React.useState(null);
  const [hover,setHover]=React.useState(null);
  const from=value&&value.from||dates[0]||addDays(now,-29),to=value&&value.to||now;
  const init=()=>{const x=parse(to);return x.m===0?{y:x.y-1,m:11}:{y:x.y,m:x.m-1};};
  const [view,setView]=React.useState(init);
  const ref=React.useRef(null);
  React.useEffect(()=>{if(!open)return;const h=e=>{if(ref.current&&!ref.current.contains(e.target)){setOpen(false);setPending(null);}};document.addEventListener('mousedown',h);return()=>document.removeEventListener('mousedown',h);},[open]);
  const has=new Set(dates);
  const label=from===to?short(from)+' '+parse(to).y:short(from)+(parse(from).y!==parse(to).y?' '+parse(from).y:'')+' – '+short(to)+' '+parse(to).y;
  const commit=(a,b)=>{const [f,t]=a<=b?[a,b]:[b,a];onChange&&onChange({from:f,to:t});setPending(null);setHover(null);setOpen(false);};
  const pick=d=>{if(pending==null)setPending(d);else commit(pending,d);};
  const lo=pending!=null?(hover&&hover<pending?hover:pending):from;
  const hi=pending!=null?(hover&&hover>pending?hover:pending):to;
  const shift=n=>setView(v=>{const t=v.m+n;return {y:v.y+Math.floor(t/12),m:((t%12)+12)%12};});
  const month=(y,m)=>{const first=new Date(Date.UTC(y,m,1)).getUTCDay();const lead=(first+6)%7;const n=new Date(Date.UTC(y,m+1,0)).getUTCDate();
    const cells=[];for(let i=0;i<lead;i++)cells.push(null);for(let d=1;d<=n;d++)cells.push(iso(y,m,d));
    return <div style={{display:'flex',flexDirection:'column',gap:6}}>
      <span style={{font:'500 13px/1 var(--font-sans)',color:'var(--fg-1)',textAlign:'center',height:28,display:'flex',alignItems:'center',justifyContent:'center'}}>{MONL[m]} {y}</span>
      <div style={{display:'grid',gridTemplateColumns:'repeat(7,32px)',rowGap:2}}>
        {['M','T','W','T','F','S','S'].map((w,i)=><span key={i} style={{height:24,display:'flex',alignItems:'center',justifyContent:'center',font:'500 11px/1 var(--font-sans)',color:'var(--fg-3)'}}>{w}</span>)}
        {cells.map((d,i)=>{if(!d)return <span key={i}/>;const future=d>now;const end=d===lo||d===hi;const inR=d>lo&&d<hi;const run=has.has(d);
          return <button key={i} type="button" disabled={future} onClick={()=>pick(d)} onMouseEnter={()=>setHover(d)} title={run?d+' · eval run':d}
            style={{position:'relative',height:32,border:0,padding:0,cursor:future?'default':'pointer',font:(d===now?'700':'400')+' 13px/1 var(--font-sans)',fontVariantNumeric:'tabular-nums',
              background:end?'var(--accent)':inR?'var(--accent-soft)':'transparent',color:future?'var(--fg-3)':end?'var(--accent-fg)':'var(--fg-1)',opacity:future?.45:1,
              borderRadius:end?(lo===hi?'var(--radius-xs)':d===lo?'var(--radius-xs) 0 0 var(--radius-xs)':'0 var(--radius-xs) var(--radius-xs) 0'):0}}>
            {parse(d).d}
            {run?<span style={{position:'absolute',left:'50%',bottom:4,width:4,height:4,marginLeft:-2,borderRadius:2,background:end?'var(--accent-fg)':'var(--accent)'}}/>:null}
          </button>;})}
      </div>
    </div>;};
  const nx=view.m===11?{y:view.y+1,m:0}:{y:view.y,m:view.m+1};
  const navBtn=(icon,n,lbl,side)=><button type="button" aria-label={lbl} onClick={()=>shift(n)} style={{position:'absolute',top:0,[side]:0,width:28,height:28,border:0,borderRadius:'var(--radius-xs)',background:'transparent',color:'var(--fg-2)',cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center'}}><Icon name={icon} size={16}/></button>;
  const presetBtn=(lbl,a,b,key)=>{const on=pending==null&&from===a&&to===b;return <button key={key} type="button" onClick={()=>commit(a,b)} style={{textAlign:'left',height:30,padding:'0 8px',border:0,borderRadius:'var(--radius-xs)',cursor:'pointer',font:'400 13px/1 var(--font-sans)',background:on?'var(--accent-soft)':'transparent',color:'var(--fg-1)',whiteSpace:'nowrap'}}>{lbl}</button>;};
  return <span ref={ref} style={{position:'relative',display:'inline-flex'}}>
    <button type="button" onClick={()=>{if(!open)setView(init());setOpen(!open);}} aria-expanded={open} style={{display:'inline-flex',alignItems:'center',gap:8,height:28,padding:'0 10px',borderRadius:'var(--radius-sm)',border:'1px solid '+(open?'var(--border-focus)':'var(--border-2)'),background:'var(--bg-surface)',color:'var(--fg-1)',font:'500 13px/1 var(--font-sans)',cursor:'pointer',whiteSpace:'nowrap'}}>
      <span style={{display:'flex',color:'var(--fg-3)'}}><Icon name="calendar" size={14}/></span>{label}<span style={{display:'flex',color:'var(--fg-3)'}}><Icon name="chevron-down" size={14}/></span>
    </button>
    {open?<div role="dialog" onMouseLeave={()=>setHover(null)} style={{position:'absolute',top:'calc(100% + 6px)',[align]:0,zIndex:20,display:'flex',gap:16,padding:12,background:'var(--bg-surface)',border:'1px solid var(--border-1)',borderRadius:'var(--radius-md)',boxShadow:'var(--shadow-2)'}}>
      <div style={{display:'flex',flexDirection:'column',gap:2,minWidth:120,paddingRight:12,borderRight:'1px solid var(--border-1)'}}>
        {presets.map((p,i)=>presetBtn(p.label,addDays(now,-(p.days-1)),now,i))}
        {dates.length?presetBtn('All eval runs',dates[0],dates[dates.length-1],'all'):null}
      </div>
      <div style={{position:'relative',display:'flex',flexDirection:'column',gap:10}}>
        {navBtn('chevron-left',-1,'Previous month','left')}{navBtn('chevron-right',1,'Next month','right')}
        <div style={{display:'flex',gap:20,padding:'0 4px'}}>{month(view.y,view.m)}{month(nx.y,nx.m)}</div>
        <div style={{display:'flex',alignItems:'center',gap:6,font:'400 12px/1.3 var(--font-sans)',color:'var(--fg-3)',padding:'0 4px'}}>
          {dates.length?<span style={{display:'inline-flex',alignItems:'center',gap:6}}><span style={{width:4,height:4,borderRadius:2,background:'var(--accent)'}}/>Eval run</span>:null}
          <span style={{marginLeft:'auto',whiteSpace:'nowrap'}}>{pending==null?'Pick a start date':'Now pick an end date'}</span>
        </div>
      </div>
    </div>:null}
  </span>;
}
