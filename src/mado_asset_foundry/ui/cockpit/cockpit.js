"use strict";
const state={flows:[],current:null,job:null,canStart:false,checking:false};
const el=id=>document.getElementById(id);
const urlId=value=>encodeURIComponent(value);
async function api(path,options={}){
  const res=await fetch(path,{cache:"no-store",...options});
  const payload=(res.headers.get("content-type")||"").includes("application/json")?await res.json():{detail:await res.text()};
  if(!res.ok)throw Error(typeof payload.detail==="string"?payload.detail:"HTTP "+res.status);
  return payload;
}
function toast(value){
  const node=el("toast");node.textContent=value;node.hidden=false;
  clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.hidden=true,6000);
}
function jobMessage(title,description,running=true){
  el("jobBox").hidden=false;el("jobTitle").textContent=title;
  el("jobDescription").textContent=description;el("jobSpinner").hidden=!running;
}
function launchEnabled(){el("launchButton").disabled=!state.canStart||!el("recipeSelect").value||!!state.job;}
async function loadStatus(){
  const s=await api("/api/status");state.canStart=s.can_start;
  el("engineMode").textContent=s.can_start?"● GODOT READY":"◇ READ-ONLY MODE";
  if(s.active_job&&!state.job){state.job=s.active_job;trackJob();}
  launchEnabled();
}
async function loadRecipes(){
  const data=await api("/api/recipes"),select=el("recipeSelect"),saved=select.value;
  select.replaceChildren();
  const empty=document.createElement("option");empty.value="";
  empty.textContent=data.recipes.length?"レシピを選択...":"レシピが見つかりません";
  select.appendChild(empty);
  for(const recipe of data.recipes){
    const option=document.createElement("option");option.value=recipe.name;
    option.textContent=recipe.name;select.appendChild(option);
  }
  select.value=data.recipes.some(item=>item.name===saved)?saved:"";launchEnabled();
}
function metrics(){
  el("runTotal").textContent=state.flows.length;
  el("pendingTotal").textContent=state.flows.filter(f=>f.review_status!=="human_release_review_passed").length;
  el("assetTotal").textContent=state.flows.reduce((n,f)=>n+(f.asset_count||0),0);
  el("runPill").textContent=state.flows.length+" RUNS";
}
function flowButtons(){
  const list=el("runList");list.replaceChildren();
  if(!state.flows.length){
    const node=document.createElement("div");node.className="empty-state";
    node.textContent="実行履歴はまだありません。左のレシピから最初の制作フローを起動できます。";list.appendChild(node);return;
  }
  for(const flow of state.flows){
    const btn=document.createElement("button");btn.type="button";
    btn.className="run-button"+(state.current&&state.current.flow_id===flow.flow_id?" active":"");
    const badge=document.createElement("span");badge.className="run-badge";badge.textContent="◈";
    const meta=document.createElement("span");meta.className="run-meta";
    const strong=document.createElement("strong");strong.textContent=flow.flow_id;
    const small=document.createElement("small");
    small.textContent=flow.asset_count+" assets · "+(flow.review_status==="human_release_review_passed"?"レビュー済み":"レビュー待ち");
    meta.append(strong,small);
    const arrow=document.createElement("span");arrow.className="run-arrow";arrow.textContent="↗";
    btn.append(badge,meta,arrow);btn.addEventListener("click",()=>selectFlow(flow.flow_id));list.appendChild(btn);
  }
}
async function loadFlows(preferred=null){
  const result=await api("/api/flows");state.flows=result.flows;metrics();
  const target=preferred||(state.current&&state.current.flow_id)||(state.flows[0]&&state.flows[0].flow_id);
  if(target&&state.flows.some(f=>f.flow_id===target))await selectFlow(target);
  else{
    state.current=null;el("emptyInspection").hidden=false;el("detailArea").hidden=true;
    el("selectedRunLabel").textContent="RUN NOT SELECTED";flowButtons();
  }
}
function mark(id,yes){
  el(id).textContent=yes?"✓ PASSED":"◌ REVIEW";
  el(id).style.color=yes?"#a5ebcd":"#f5b590";
}
function assetCard(flowId,asset){
  const card=document.createElement("article");card.className="asset-card";
  const thumb=document.createElement("div");thumb.className="asset-thumb";
  const img=document.createElement("img");img.loading="lazy";
  img.src="/api/flows/"+urlId(flowId)+"/assets/"+urlId(asset.asset_id)+"/image";
  img.alt=asset.title||asset.asset_id;thumb.appendChild(img);
  const body=document.createElement("div");body.className="asset-body";
  const head=document.createElement("strong");head.textContent=asset.title||asset.asset_id;body.appendChild(head);
  for(const value of [asset.creator||"Unknown creator","Source: "+asset.source_id,asset.license+" · "+asset.license_status]){
    const line=document.createElement("span");line.textContent=value;body.appendChild(line);
  }
  card.append(thumb,body);return card;
}
async function selectFlow(flowId){
  try{
    const d=await api("/api/flows/"+urlId(flowId));state.current=d;
    el("selectedRunLabel").textContent=flowId.toUpperCase();
    el("emptyInspection").hidden=true;el("detailArea").hidden=false;
    el("godotLabel").textContent=d.godot_version||"GODOT";
    const image="/api/flows/"+urlId(flowId)+"/gallery";
    el("galleryImage").src=image;el("galleryOpenLink").href=image;
    const credits="/api/flows/"+urlId(flowId)+"/credits";
    el("creditsOpenLink").href=credits;
    try{const res=await fetch(credits,{cache:"no-store"});el("creditsText").textContent=res.ok?await res.text():"CREDITS を取得できません";}
    catch{el("creditsText").textContent="CREDITS を取得できません";}
    mark("intakeEvidence",d.assets.every(a=>a.license_status==="eligible"));
    mark("attributionEvidence",true);mark("runtimeEvidence",d.runtime_status==="passed");
    mark("visualEvidence",d.gallery_status==="captured");
    mark("reviewEvidence",d.review_status==="human_release_review_passed");
    el("imageHash").textContent=d.screenshot_sha256||"—";
    el("creditsHash").textContent=d.credits_sha256||"—";
    el("assetGrid").replaceChildren(...d.assets.map(a=>assetCard(flowId,a)));
    const finished=d.review_status==="human_release_review_passed";
    for(const input of el("reviewForm").querySelectorAll("input,textarea,button"))input.disabled=finished;
    el("reviewMessage").textContent=finished?"✓ 人間のレビュー記録済み。公開は無効です。":"確認した項目のみチェックしてください。";
    flowButtons();
  }catch(error){toast("実行データを読み込めません: "+error.message);}
}
async function trackJob(){
  if(state.checking||!state.job)return;state.checking=true;
  try{
    while(state.job){
      const id=state.job,job=await api("/api/jobs/"+urlId(id));
      if(job.status==="completed"){
        state.job=null;jobMessage("完成！","ギャラリーを確認して人間のレビューに進めます。",false);
        toast("制作フローが完成しました。");await loadFlows(job.flow_id);
      }else if(job.status==="failed"){
        state.job=null;jobMessage("制作が停止しました",job.error||"サーバーログを確認してください。",false);
        toast("制作フローが停止しました。");
      }else{
        jobMessage("制作ライン稼働中","素材・ライセンス・実Godot・撮影を処理中...");
        await new Promise(resolve=>setTimeout(resolve,1500));
      }
    }
  }catch(error){state.job=null;toast("実行状況を取得できません: "+error.message);}
  finally{state.checking=false;launchEnabled();}
}
el("recipeSelect").addEventListener("change",launchEnabled);
el("launchForm").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!state.canStart||state.job||!el("recipeSelect").value)return;
  try{
    const result=await api("/api/actions/run",{
      method:"POST",headers:{"Content-Type":"application/json","X-MAF-Action":"cockpit"},
      body:JSON.stringify({recipe:el("recipeSelect").value})
    });
    state.job=result.job_id;launchEnabled();jobMessage("制作ライン起動","Godot QAと実描画を実行します。");trackJob();
  }catch(error){toast("実行できません: "+error.message);}
});
el("reviewForm").addEventListener("submit",async event=>{
  event.preventDefault();if(!state.current)return;
  const payload={
    reviewer:el("reviewerName").value.trim(),notes:el("reviewNotes").value.trim(),
    visual_approved:el("visualCheck").checked,
    attribution_approved:el("creditsCheck").checked,
    rights_approved_for_game_embedding:el("rightsCheck").checked
  };
  if(!payload.visual_approved||!payload.attribution_approved||!payload.rights_approved_for_game_embedding){
    el("reviewMessage").textContent="3項目すべてを確認してから記録してください。";return;
  }
  if(!window.confirm("画像・クレジット・利用権の確認を記録します。公開許可にはなりません。続けますか？"))return;
  try{
    el("reviewButton").disabled=true;
    const id=state.current.flow_id;
    const result=await api("/api/flows/"+urlId(id)+"/review",{
      method:"POST",headers:{"Content-Type":"application/json","X-MAF-Action":"cockpit"},
      body:JSON.stringify(payload)
    });
    el("reviewMessage").textContent="✓ "+result.reviewer+" の確認を記録。公開は無効です。";
    toast("レビューを記録しました。");await loadFlows(id);
  }catch(error){
    el("reviewMessage").textContent="レビューできません: "+error.message;
    el("reviewButton").disabled=false;
  }
});
el("refreshButton").addEventListener("click",async()=>{
  try{await Promise.all([loadStatus(),loadRecipes()]);await loadFlows();toast("最新状態を読み込みました。");}
  catch(error){toast(error.message);}
});
(async()=>{try{await Promise.all([loadStatus(),loadRecipes()]);await loadFlows();}
catch(error){toast("Cockpitを読み込めません: "+error.message);}})();
