'use strict';
(function(){
const listView=document.getElementById('listView');
if(!listView)return;
let listTab='upcoming';
const todayParis=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Paris'}).format(new Date());
const originalRenderList=renderList;
renderList=function(list){
const today=todayParis();
const filtered=list.filter(e=>listTab==='upcoming'?e.date>=today:e.date<today);
if(!filtered.length){
$('#eventList').innerHTML=listTab==='upcoming'
?'<div class="empty"><h3>Aucune soirée à venir dans cette sélection.</h3><p class="small">Les soirées passées restent accessibles dans l’onglet Historique.</p></div>'
:'<div class="empty"><h3>Aucune soirée passée dans cette sélection.</h3><p class="small">Les soirées à venir sont affichées dans l’onglet À venir.</p></div>';
return;
}
originalRenderList(filtered);
};
const setUpcoming=()=>{listTab='upcoming';document.getElementById('upcomingTab').setAttribute('aria-pressed','true');document.getElementById('historyTab').setAttribute('aria-pressed','false');render();};
const setHistory=()=>{listTab='history';document.getElementById('upcomingTab').setAttribute('aria-pressed','false');document.getElementById('historyTab').setAttribute('aria-pressed','true');render();};
document.getElementById('upcomingTab').addEventListener('click',setUpcoming);
document.getElementById('historyTab').addEventListener('click',setHistory);
render();
})();
