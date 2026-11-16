// Historical mapping records are never promoted by stale candidate flags.
(() => {
const el=id=>document.getElementById(id), fields=['scope','category','grade','search'], size=30;
let page=0;
const escape=s=>String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
for(const [id,key] of [['category','category'],['grade','representation']])for(const t of [...new Set(CATALOG.map(r=>r[key]))].sort())el(id).add(new Option(t,t));
function picture(r,source){
    const detail=source&&el('sourceView').value==='detail';
    const hash=source?(detail?r.detail_image||r.source_image:r.source_image):r.target_image;
    const url=(source?(detail?r.detail_url||r.source_url:r.source_url):r.target_url)||(hash?'images/'+hash+'.png':'');
    const label=source?'U7 '+r.shape+'/'+r.frame:r.representation==='Approved representation'?'Approved ground artwork':r.uo_id||'No mapping';
    return '<figure><div class="stage">'+(url?'<a href="'+escape(url)+'" target="_blank" rel="noopener" aria-label="Enlarge '+escape(label)+'"><img alt="'+escape(label)+'" src="'+escape(url)+'"></a>':'<i>No visible artwork</i>')+'</div><figcaption>'+escape(label)+'</figcaption></figure>';
}
function render(){
    const q=el('search').value.trim().toLowerCase(), scope=el('scope').value;
    const rows=CATALOG.filter(r=>(!scope||(scope==='town'?r.evidence!=='Other frame':scope===r.evidence))&&(!el('category').value||el('category').value===r.category)&&(!el('grade').value||el('grade').value===r.representation)&&(!q||[r.name,r.source_name,r.uo_name,r.uo_id,r.owner,r.method,r.layers,r.shape+'/'+r.frame].join(' ').toLowerCase().includes(q)));
    const max=Math.max(0,Math.ceil(rows.length/size)-1);page=Math.max(0,Math.min(page,max));
    el('prev').disabled=el('back').disabled=page===0;el('next').disabled=el('forward').disabled=page>=max;
    el('count').textContent=rows.length?rows.length.toLocaleString()+' records · page '+(page+1)+' of '+(max+1):'No matching records';
    el('cards').innerHTML=rows.slice(page*size,(page+1)*size).map(r=>'<article><div class="line"><small>'+escape(r.category)+'</small><span class="tag">'+escape(r.representation)+'</span></div><h3>'+escape(r.name||r.source_name)+'</h3><div class="pair">'+picture(r,true)+picture(r,false)+'</div><small>'+escape(r.uo_name)+'</small><p>'+escape(r.note)+'</p>'+(r.documentation_url?'<a href="'+escape(r.documentation_url)+'">View approved representation</a>':'<details><summary>Historical mapping details</summary><small>'+escape(r.status)+' · '+escape(r.uo_id)+'</small></details>')+'<footer>'+escape(r.evidence)+(r.refs?' · '+r.refs+' source references<div>'+escape(r.layers)+' · ('+escape(r.witness)+')</div>':'')+(r.footprint?'<div>Footprint '+escape(r.footprint)+' · '+escape(r.method)+'</div>':'')+(r.swing?'<a href="#'+escape(r.swing)+'">Swing partner '+escape(r.swing)+'</a>':'')+'</footer></article>').join('')||'<p>No records match these filters.</p>';
}
function jump(){const pair=decodeURIComponent(location.hash.slice(1));if(!/^\d+\/\d+$/.test(pair))return;el('category').value=el('grade').value=el('scope').value='';el('search').value=pair;page=0;render();}
fields.forEach(id=>el(id).addEventListener('input',()=>{page=0;render();}));el('sourceView').onchange=render;
for(const [id,d] of [['prev',-1],['back',-1],['next',1],['forward',1]])el(id).onclick=()=>{page+=d;render();el('prev').scrollIntoView({block:'nearest'});};
addEventListener('hashchange',jump);render();jump();
})();
