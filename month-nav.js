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
  style.textContent=`.monthbar{gap:8px}.monthnav{background:transparent;border:0;color:var(--accent);font-size:14px;font-weight:600;padding:10px 8px;white-space:nowrap}.monthnav:hover{text-decoration:underline}.month-center{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1}.month-center .today{font-size:12px;min-height:32px;padding:4px 10px}@media(max-width:640px){.monthnav{font-size:12px;padding:8px 4px}}`;
  document.head.append(style);
})();