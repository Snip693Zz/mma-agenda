(function(){
  'use strict';
  const bar=document.querySelector('.monthbar');
  if(!bar)return;
  const prev=document.getElementById('prev');
  const next=document.getElementById('next');
  const today=document.getElementById('today');
  const title=document.getElementById('monthTitle');
  const count=document.getElementById('monthCount');
  if(!prev||!next||!today||!title||!count)return;
  const fmt=new Intl.DateTimeFormat('fr-FR',{month:'long',year:'numeric',timeZone:'UTC'});
  const months=['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'];
  function monthName(y,m){
    return fmt.format(new Date(Date.UTC(y,m,1))).replace(/^./,c=>c.toUpperCase());
  }
  function parseTitle(text){
    const match=String(text||'').trim().match(/^([a-zéûô]+)\s+(\d{4})$/i);
    if(!match)return null;
    const index=months.indexOf(match[1].toLowerCase());
    return index<0?null:{year:Number(match[2]),month:index};
  }
  function updateLabels(){
    const current=parseTitle(title.textContent);
    if(!current)return;
    prev.setAttribute('aria-label','Aller à '+monthName(current.year,current.month-1));
    next.setAttribute('aria-label','Aller à '+monthName(current.year,current.month+1));
  }
  const arrowLeft=document.createElementNS('http://www.w3.org/2000/svg','svg');
  arrowLeft.setAttribute('viewBox','0 0 24 24');
  arrowLeft.setAttribute('aria-hidden','true');
  arrowLeft.innerHTML='<path d="M15 5l-7 7 7 7"/>';
  const arrowRight=document.createElementNS('http://www.w3.org/2000/svg','svg');
  arrowRight.setAttribute('viewBox','0 0 24 24');
  arrowRight.setAttribute('aria-hidden','true');
  arrowRight.innerHTML='<path d="M9 5l7 7-7 7"/>';
  prev.innerHTML='';
  next.innerHTML='';
  prev.append(arrowLeft);
  next.append(arrowRight);
  const center=document.createElement('div');
  center.className='month-center';
  center.append(title,count,today);
  bar.innerHTML='';
  bar.append(prev,center,next);
  const observer=new MutationObserver(updateLabels);
  observer.observe(title,{childList:true,characterData:true,subtree:true});
  updateLabels();
  const style=document.createElement('style');
  style.textContent=`.monthbar{display:flex;align-items:center;justify-content:space-between;gap:10px}.monthbar .iconbtn{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;background:var(--raised);border:1px solid var(--line);color:var(--ink);width:44px;height:44px;padding:0;border-radius:14px;transition:border-color .18s,background .18s,transform .18s}.monthbar .iconbtn:hover{border-color:var(--accent);background:var(--panel)}.monthbar .iconbtn:active{transform:scale(.98)}.monthbar .iconbtn svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.month-center{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;text-align:center}.month-center h2{margin:0;font-size:clamp(18px,4.5vw,23px);font-weight:650;letter-spacing:-.03em;line-height:1.2;text-align:center;white-space:nowrap}.month-center small{color:var(--muted);font-size:11px;line-height:1.3}.month-center .today{font-size:12px;min-height:30px;padding:3px 10px;margin-top:2px}`;
  document.head.append(style);
})();