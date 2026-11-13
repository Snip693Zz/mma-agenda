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
    prevLabel.textContent='← '+monthName(current.year,current.month-1);
    nextLabel.textContent=monthName(current.year,current.month+1)+' →';
  }
  const prevLabel=document.createElement('button');
  prevLabel.type='button';
  prevLabel.className='monthnav';
  prevLabel.setAttribute('aria-label','Aller au mois précédent');
  const nextLabel=document.createElement('button');
  nextLabel.type='button';
  nextLabel.className='monthnav';
  nextLabel.setAttribute('aria-label','Aller au mois suivant');
  const center=document.createElement('div');
  center.className='month-center';
  center.append(title,count,today);
  bar.innerHTML='';
  bar.append(prevLabel,center,nextLabel);
  prevLabel.addEventListener('click',()=>prev.click());
  nextLabel.addEventListener('click',()=>next.click());
  const observer=new MutationObserver(updateLabels);
  observer.observe(title,{childList:true,characterData:true,subtree:true});
  updateLabels();
  const style=document.createElement('style');
  style.textContent=`.monthbar{display:flex;align-items:center;justify-content:space-between;gap:10px}.monthnav{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;gap:6px;background:var(--raised);border:1px solid var(--line);color:var(--ink);font-size:13px;font-weight:600;padding:10px 14px;border-radius:14px;white-space:nowrap;transition:border-color .18s,background .18s,transform .18s}.monthnav:hover{border-color:var(--accent);background:var(--panel)}.monthnav:active{transform:scale(.98)}.month-center{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;text-align:center}.month-center h2{margin:0;font-size:clamp(18px,4.5vw,23px);font-weight:650;letter-spacing:-.03em;line-height:1.2;text-align:center;white-space:nowrap}.month-center small{color:var(--muted);font-size:11px;line-height:1.3}.month-center .today{font-size:12px;min-height:30px;padding:3px 10px;margin-top:2px}@media(max-width:520px){.monthnav{width:44px;height:44px;padding:0;font-size:0;border-radius:14px}.monthnav::before{font-size:20px;font-weight:600;line-height:1}.monthnav[aria-label="Aller au mois précédent"]::before{content:'←'}.monthnav[aria-label="Aller au mois suivant"]::before{content:'→'}}`;
  document.head.append(style);
})();