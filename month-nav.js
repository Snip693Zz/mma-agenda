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

  /* Étape 3 — présentation du calendrier */
  const calendar=document.getElementById('calendar');
  const presentationStyle=document.createElement('style');
  presentationStyle.textContent=`
.calendarEvent{display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:2px}
.cal-name{display:block;font-weight:650;line-height:1.35}
.cal-sub{display:block;opacity:.82;line-height:1.35}
.calendarEvent[data-org]{--cal-color:var(--line);--cal-text:var(--ink)}
.calendarEvent[data-org="UFC"]{--cal-color:#1f6feb;--cal-text:#9bc5ff}
.calendarEvent[data-org="PFL"]{--cal-color:#d1242f;--cal-text:#ffabb2}
.calendarEvent[data-org="ARES"]{--cal-color:#0a7d33;--cal-text:#93e3b0}
.calendarEvent[data-org="HEXAGONE"]{--cal-color:#b7791f;--cal-text:#f2d09a}
.calendarEvent[data-org]:not([data-org=""]){border-left-color:var(--cal-color);background:color-mix(in srgb,var(--cal-color) 14%,var(--panel));color:var(--cal-text)}
:root[data-theme=light] .calendarEvent[data-org="UFC"]{--cal-text:#174fa8}
:root[data-theme=light] .calendarEvent[data-org="PFL"]{--cal-text:#a21c25}
:root[data-theme=light] .calendarEvent[data-org="ARES"]{--cal-text:#086329}
:root[data-theme=light] .calendarEvent[data-org="HEXAGONE"]{--cal-text:#785013}
.day.is-today{box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 45%,transparent)}
@media(max-width:640px){.cal-name{font-size:10px}.cal-sub{font-size:9px}}
@media(max-width:360px){.cal-name{font-size:9px}.cal-sub{font-size:8.5px}}`;
  document.head.append(presentationStyle);

  /* Étape 4 — fiches détaillées */
  const detailStyle=document.createElement('style');
  detailStyle.textContent=`
dialog{max-width:820px}
.modal-body{padding:30px 26px 34px}
.event-meta{background:var(--raised);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:14px 0 0;font-size:13px;line-height:1.7}
.detail-note{margin:18px 0 6px;padding:14px 16px;border-left:3px solid var(--accent);border-radius:10px;background:var(--raised)}
.card{margin-top:18px;border:1px solid var(--line);border-radius:16px;padding:18px;background:var(--raised)}
.card:first-of-type{margin-top:22px}
.card-title{gap:14px;align-items:center}
.card-title h3{font-size:16px}
.card-time b{font-size:24px}
.card-actions{margin:16px 0 4px}
.bouts{margin-top:6px}
.bout{padding:16px 0;gap:14px}
.fighter-name{font-size:15px}
.sources{margin-top:26px;background:var(--raised);border:1px solid var(--line);border-radius:16px;padding:16px}
.sources summary{font-weight:600}
.source-links{margin-top:10px;gap:16px}
@media(max-width:640px){.modal-body{padding:22px 16px 26px}.card{padding:14px;border-radius:14px}.bout{gap:8px}.fighter-name{font-size:13px}}`;
  document.head.append(detailStyle);

  function enhanceCalendar(){
    if(!calendar)return;
    calendar.querySelectorAll('.calendarEvent').forEach(button=>{
      if(button.dataset.step3==='1')return;
      const event=(typeof data!=='undefined'?data:[]).find(item=>item.id===button.dataset.open);
      if(!event)return;
      const parts=String(event.title||'').split(' — ');
      const name=parts[0].trim();
      const subtitle=parts.slice(1).join(' — ').trim();
      button.dataset.org=event.org||'';
      button.dataset.step3='1';
      button.setAttribute('aria-label',event.title||name);
      button.innerHTML=`<span class="cal-name">${esc(name)}</span>${subtitle?`<span class="cal-sub">${esc(subtitle)}</span>`:''}`;
    });
  }

  if(calendar){
    enhanceCalendar();
    const calendarObserver=new MutationObserver(enhanceCalendar);
    calendarObserver.observe(calendar,{childList:true,subtree:true});
  }
})();