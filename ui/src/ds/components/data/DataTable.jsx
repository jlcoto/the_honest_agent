import React from 'react';
export function DataTable({columns,rows,dense,onRowClick,rowKey}){
  const [h,setH]=React.useState(-1);const pad=dense?'8px 12px':'12px 12px';
  return <div style={{overflowX:'auto',minWidth:0}}>
    <table style={{width:'100%',borderCollapse:'collapse',font:'var(--type-body)'}}>
      <thead><tr>{columns.map(c=><th key={c.key} style={{textAlign:c.align||'left',padding:'0 12px 8px',font:'500 12px/1.3 var(--font-sans)',color:'var(--fg-3)',borderBottom:'1px solid var(--border-1)',whiteSpace:'nowrap',width:c.width}}>{c.label}</th>)}</tr></thead>
      <tbody>{rows.map((r,i)=><tr key={rowKey?r[rowKey]:i} onMouseEnter={()=>setH(i)} onMouseLeave={()=>setH(-1)} onClick={()=>onRowClick&&onRowClick(r)} style={{background:h===i?'var(--bg-sunken)':'transparent',cursor:onRowClick?'pointer':'default'}}>
        {columns.map(c=><td key={c.key} style={{padding:pad,textAlign:c.align||'left',borderBottom:'1px solid var(--border-1)',color:'var(--fg-1)',verticalAlign:'middle',fontFamily:c.mono?'var(--font-mono)':undefined,fontSize:c.mono?13:undefined,fontVariantNumeric:'tabular-nums'}}>{c.render?c.render(r):r[c.key]}</td>)}
      </tr>)}</tbody>
    </table>
  </div>;
}
