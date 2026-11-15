/* Visual effect chooser: screenshots 1–36 are from the licensed upstream preview montage.
   The remaining 15 show illustrative icons, not misleading rendered previews. */
(function(){
const PREVIEW='https://raw.githubusercontent.com/Vibha-Ramprakash/claude-video-effects/60840acc7e126a5e34068276a23e912ec4c8c34c/assets/preview.jpg';
const rows=[
['noise','Reels Rain','Peechhe multiple reel cards aa jayenge','face','🎞️'],
['lineup','Cards Above','Sir ke upar numbered cards dikhte hain','face','🗂️'],
['locked-on','Face Tracker','Camera tumhara face follow karega','zoom','🎯'],
['orbit','3D Orbit','Reel cards head ke around ghoomengi','face','🪐'],
['lean-in','Quick Zoom','Ekdam se dramatic zoom-in hoga','zoom','🔎'],
['backdrop-word','Big Backdrop Word','Peechhe bahut bada stylish word','text','🔠'],
['spotlight','Spotlight','Background dark, subject bright','face','🔦'],
['the-bill','Receipt Print','Text receipt ki tarah print hoga','text','🧾'],
['moody','Cinematic Color','Dark movie-style color grading','visual','🎬'],
['swipe','Before / After','Screen par before-after swipe','zoom','↔️'],
['todo','To-Do Checklist','Side mein checklist tick hoti rahegi','social','☑️'],
['comment-box','Typing Comment','Instagram comment type hota dikhega','social','💬'],
['tap','Follow Button','Follow se Following animation','social','👆'],
['pause-point','Freeze + Arrow','Video pause aur hand-drawn arrow','zoom','📍'],
['uninstall','Glitch Uninstall','Glitchy uninstall progress animation','visual','⚡'],
['reel-frame','Reel Card','Video Instagram reel-card banega','social','📱'],
['shortcut-rain','Falling Keys','Keyboard keys rain ki tarah girengi','visual','⌨️'],
['reject-stamp','NOPE Stamp','Screen par bada red stamp','text','🚫'],
['countdown-flip','3-2-1 Countdown','Upar flip-clock countdown','text','⏱️'],
['rabbit-hole','Tunnel Zoom','Frame andar tunnel ki tarah jayega','zoom','🌀'],
['cover-star','Magazine Cover','Celebrity magazine cover jaisa look','face','⭐'],
['scribble','Marker Doodles','Animated doodles face ke around','visual','🖊️'],
['glass-widgets','Glass Widgets','Floating frosted-glass information cards','social','🫧'],
['red-collage','Red Poster','Black-white video + bold red words','text','🟥'],
['split-headline','Split Headline','Upar badi headline, neeche video','text','📰'],
['pastel-word','Pastel Background','Lavender background aur giant text','text','🟣'],
['check-pills','Clicking Pills','Clickable blue labels tick honge','social','🔵'],
['timeline','Editing Timeline','Neeche editing timeline aur playhead','visual','🎚️'],
['headline-box','Bold Headline','Big headline box ke saath zoom','text','🗞️'],
['profile-wall','Profile Wall','Reel grid aur view counter dikhega','social','🧩'],
['tier-list','Ranking Tier List','S-A-B-C ranking board animation','social','🏆'],
['broll-split','Top / Bottom Split','Upar B-roll aur neeche main video','zoom','🪟'],
['phone-fan','Phone Fan','Phone screens taash jaise failenge','social','📲'],
['dot-reveal','Dot Reveal','Glowing dots se video reveal hoga','visual','✨'],
['headline-wall','Headline Wall','Peechhe kai headlines aur total','text','📰'],
['checklist','Green Checklist','Tasks ek-ek karke green tick','social','✅'],
['liquid-glass-graph','Glass Graph','Transparent graph aur growing number','social','📈'],
['carousel-spin','3D Carousel','Reel cards 3D mein rotate karenge','visual','🎠'],
['match-cut','News Match Cut','News pages ke fast matching cuts','visual','🎞️'],
['apple-toggles','iPhone Toggles','iPhone setting switches on honge','social','📳'],
['led-sign','Neon LED Sign','Dark scene mein neon text type hoga','text','💡'],
['slow-push','Slow Movie Zoom','Smooth cinematic camera zoom','zoom','🎥'],
['over-the-shoulder-zoom','Zoom + Two Graphs','Corner zoom ke saath glass charts','zoom','📊'],
['messages','Message Popups','Chat notifications ek-ek karke ayengi','social','💬'],
['place-in-grid','3×3 Reel Grid','Center mein video, around reel grid','social','▦'],
['tape-label','Yellow Tape Label','Chest par yellow tape-style title','text','🟨'],
['select-resize','Drag to Resize','Cursor number ko select karke bada karega','social','🖱️'],
['wave-trim','Audio Wave Trim','Voice-wave aur silent parts animation','visual','🎙️'],
['huge-strike','Big Word Strike','Giant text par red cross line','text','❌'],
['crayon-write','Crayon Writing','Red crayon text likhkar underline','text','🖍️'],
['fan-build','Reel Fan Build','Reel covers fan shape mein niklenge','social','🃏']
].map((r,i)=>({id:r[0],name:r[1],desc:r[2],type:r[3],icon:r[4],idx:i}));
const BY_ID=Object.fromEntries(rows.map(x=>[x.id,x]));
const FILTERS=[
['all','✨ All 51'],
['easy','⭐ Easy picks'],
['gaming','🎮 Gaming Shorts'],
['movie','🎬 Movie Explainer'],
['talking','🎙️ Talking Video'],
['zoom','📹 Zoom'],
['text','🔤 Text'],
['social','📱 UI effects'],
['visual','💫 Visuals']
];
const PICKS={
easy:['lean-in','moody','slow-push','spotlight','headline-box','pause-point','countdown-flip','reject-stamp','dot-reveal','locked-on'],
gaming:['lean-in','moody','pause-point','countdown-flip','timeline','headline-box','reject-stamp','slow-push','dot-reveal','huge-strike','scribble'],
movie:['headline-box','slow-push','moody','spotlight','split-headline','countdown-flip','red-collage','led-sign','huge-strike','match-cut'],
talking:['locked-on','orbit','spotlight','glass-widgets','lineup','backdrop-word','comment-box','checklist','cover-star','tap','slow-push']
};
const CLASS_LABEL={zoom:'Camera',face:'Face effects',text:'Text / title',social:'UI / cards',visual:'Visual style'};
let filter='all',searchValue='';
function match(x){let q=searchValue.trim().toLowerCase();return (filter==='all'||(PICKS[filter]||[]).includes(x.id)||x.type===filter)&&(!q||(x.name+' '+x.desc+' '+x.id).toLowerCase().includes(q))}
function makePoster(item){
 const p=document.createElement('div');
 p.className='effect-poster '+(item.idx<36?'has-sprite':'visual-cue');
 if(item.idx<36){
   const col=item.idx%9,row=Math.floor(item.idx/9);
   p.style.backgroundImage='url("'+PREVIEW+'")';
   p.style.setProperty('--x',(col/8*100).toFixed(4)+'%');
   p.style.setProperty('--y',(row/3*100).toFixed(4)+'%');
 }else{
   const icon=document.createElement('div');icon.className='effect-cue-icon';icon.textContent=item.icon;p.append(icon);
 }
 const label=document.createElement('span');
 label.className='effect-preview-label';label.textContent=item.idx<36?'Example photo':'Visual guide';
 p.append(label);return p;
}
function choose(id){
 state.effect=id;
 showEffects();
 const upload=document.getElementById('edit');
 if(upload && !upload.classList.contains('hidden')){let b=document.getElementById('render');if(b)b.scrollIntoView({behavior:'smooth',block:'center'})}
}
function makeCard(x){
 const selected=state.effect===x.id;
 const b=document.createElement('button');b.type='button';
 b.className='effect-card';b.setAttribute('aria-pressed',String(selected));
 b.setAttribute('aria-label',x.name+', '+x.desc+(selected?', selected':''));
 b.append(makePoster(x));
 if(['lean-in','spotlight','moody','slow-push','locked-on','headline-box'].includes(x.id)){
   const badge=document.createElement('span');badge.className='featured';badge.textContent='POPULAR';b.append(badge);
 }
 const body=document.createElement('div');body.className='card-body';
 const title=document.createElement('div');title.className='card-title';title.textContent=(x.idx+1)+'. '+x.name;
 const desc=document.createElement('div');desc.className='card-desc';desc.textContent=x.desc;
 const foot=document.createElement('div');foot.className='card-footer';
 const cat=document.createElement('span');cat.textContent=CLASS_LABEL[x.type];
 const selectedTag=document.createElement('span');selectedTag.className='card-choose';selectedTag.textContent=selected?'✓ SELECTED':'TAP TO SELECT';
 foot.append(cat,selectedTag);body.append(title,desc,foot);b.append(body);b.onclick=()=>choose(x.id);
 return b;
}
function updateSelection(){
 const chosen=BY_ID[state.effect]||rows[4];
 for(const id of ['chooseSelected','editSelected']){
   const slot=document.getElementById(id);
   if(!slot)continue;
   slot.textContent='';
   const words=document.createElement('div');
   const name=document.createElement('strong');name.textContent='✓ Selected: '+chosen.name;
   const desc=document.createElement('small');desc.textContent=chosen.desc;
   words.append(name,desc);slot.append(words);
   if(id==='chooseSelected'){
     const btn=document.createElement('button');btn.textContent='Next: Upload video →';btn.onclick=()=>document.getElementById('uploadPanel')?.scrollIntoView({behavior:'smooth',block:'center'});
     slot.append(btn);
   }
 }
 const btn=document.getElementById('render');if(btn)btn.textContent='✦ Generate with '+chosen.name;
}
function drawFilters(){
 for(const id of ['chooseFilters','editFilters']){
  const outer=document.getElementById(id);if(!outer)continue;outer.replaceChildren();
  for(const [key,name] of FILTERS){
    const b=document.createElement('button');b.type='button';b.textContent=name;
    if(filter===key)b.className='active';
    b.setAttribute('aria-pressed',String(filter===key));
    b.onclick=()=>{filter=key;showEffects()};outer.append(b);
  }
 }
}
function showEffectsNew(){
 const selected=rows.filter(match);
 for(const id of ['chooseGrid','effects']){
   const host=document.getElementById(id);if(!host)continue;
   host.classList.add('effect-gallery');host.replaceChildren();
   if(!selected.length){let e=document.createElement('div');e.className='effect-results-empty';e.textContent='Is search ke liye koi effect nahi mila. All 51 try karo.';host.append(e)}
   else selected.forEach(x=>host.append(makeCard(x)));
 }
 for(const id of ['chooseCount','editCount']){const x=document.getElementById(id);if(x)x.textContent=selected.length+' of 51 effects · ek preview par tap karo'}
 drawFilters();updateSelection();
}
function startPicker(){
 if(typeof state==='undefined'){return}
 showEffects=showEffectsNew;
 for(const [inputId] of [['chooseSearch'],['search']]){
  const el=document.getElementById(inputId);if(!el)continue;
  el.oninput=()=>{searchValue=el.value;const second=document.getElementById(inputId==='search'?'chooseSearch':'search');if(second)second.value=searchValue;showEffectsNew()}
 }
 showEffectsNew();
}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',startPicker,{once:true})}else{startPicker()}
})();