import React from 'react';
const CDN='https://unpkg.com/lucide-static@0.469.0/icons/';
export function Icon({name,size=16,color='currentColor',style,title}){
  const url='url('+CDN+name+'.svg)';
  return <span role={title?'img':undefined} aria-label={title} aria-hidden={title?undefined:true} style={{display:'inline-block',flex:'none',width:size,height:size,background:color,WebkitMaskImage:url,maskImage:url,WebkitMaskSize:'contain',maskSize:'contain',WebkitMaskRepeat:'no-repeat',maskRepeat:'no-repeat',WebkitMaskPosition:'center',maskPosition:'center',...style}}/>;
}
