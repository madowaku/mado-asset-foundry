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
const stageLabels={intake:"01 · Source / License",attribution:"02 · Attribution",runtime:"03 · Godot QA",gallery:"04 · Render Gallery",evidence:"05 · Evidence"};
function renderStages(stages){
  const holder=el("stageList");holder.replaceChildren();
  let completed=0;
  for(const item of stages||[]){
    if(item.status==="completed")completed++;
    const row=document.createElement("li");row.className="stage-"+item.status;
    const name=document.createElement("span");name.textContent=stageLabels[item.stage]||item.stage;
    const value=document.createElement("strong");
    value.textContent={completed:"✓ DONE",running:"● RUNNING",failed:"× FAILED",pending:"○ QUEUED"}[item.status]||"QUEUED";
    row.append(name,value);holder.appendChild(row);
  }
  el("stageCount").textContent=completed+" / "+(stages?.length||5)+" stages";
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
function reviewCounts(d){
  const r=d.visual_review||{total:0,reviewed:0,pending:0,passed:0,rework:0,rejected:0,decisions:{}};
  const node=el("visualSummary");node.replaceChildren();
  for(const [label,value,style] of [
    ["Reviewed",r.reviewed+"/"+r.total,""],
    ["Pass",r.passed,""],
    ["Pending",r.pending,"warning"],
    ["Rework",r.rework,"warning"],
    ["Reject",r.rejected,"negative"]
  ]){
    const chip=document.createElement("span");chip.className="visual-stat "+style;
    chip.textContent=label+": "+value;node.appendChild(chip);
  }
  return r;
}
function finalGate(d){
  const completed=d.review_status==="human_release_review_passed";
  const ready=!!d.visual_review?.ready_for_final_review;
  el("reviewButton").disabled=completed||!ready;
  el("finalGateMessage").textContent=completed
    ?"レビュー記録済み。公開は無効のままです。"
    :ready?"全素材Pass。最終確認の3項目とコメントを記録できます。"
    :"個別の画像をすべてPassにしてください。Pending / Rework / Reject が残る間は最終レビューを停止します。";
}
async function saveAssetDecision(flowId,assetId,select,note,button){
  const reviewer=(el("visualReviewer").value||el("reviewerName").value).trim();
  if(reviewer.length<3){toast("素材ごとの判定者名を入力してください。");el("visualReviewer").focus();return;}
  if(!select.value){toast("Pass / Rework / Reject を選んでください。");return;}
  if(select.value!=="pass"&&note.value.trim().length<5){toast("修正・却下の理由を5文字以上入力してください。");return;}
  button.disabled=true;
  try{
    await api("/api/flows/"+urlId(flowId)+"/assets/"+urlId(assetId)+"/visual",{
      method:"POST",headers:{"Content-Type":"application/json","X-MAF-Action":"cockpit"},
      body:JSON.stringify({reviewer,decision:select.value,note:note.value.trim()})
    });
    toast("素材 "+assetId+" の目視判定を記録しました。");
    await selectFlow(flowId);
  }catch(error){toast("判定を記録できません: "+error.message);}
  finally{button.disabled=false;}
}
function assetCard(flowId,asset,decision,finalized){
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
  const status=document.createElement("span");
  status.className="visual-status "+(decision?.decision||"");
  status.textContent="Visual: "+(decision?.decision||"pending").toUpperCase();
  body.appendChild(status);
  const editor=document.createElement("div");editor.className="visual-decision";
  const selectLabel=document.createElement("label");selectLabel.textContent="DECISION";
  const select=document.createElement("select");select.className="visual-input";
  for(const [value,title] of [["","Choose..."],["pass","Pass · 問題なし"],["rework","Rework · 修正"],["reject","Reject · 不採用"]]){
    const option=document.createElement("option");option.value=value;option.textContent=title;select.appendChild(option);
  }
  select.value=decision?.decision||"";select.disabled=finalized;selectLabel.appendChild(select);
  const noteLabel=document.createElement("label");noteLabel.textContent="REVIEW NOTE";
  const note=document.createElement("textarea");note.className="visual-input";
  note.placeholder="修正点・確認メモ";note.maxLength=1000;note.rows=2;
  note.value=decision?.note||"";note.disabled=finalized;noteLabel.appendChild(note);
  const save=document.createElement("button");save.type="button";save.className="visual-save";
  save.textContent=finalized?"LOCKED":"判定を保存";save.disabled=finalized;
  save.addEventListener("click",()=>saveAssetDecision(flowId,asset.asset_id,select,note,save));
  editor.append(selectLabel,noteLabel,save);body.appendChild(editor);
  card.append(thumb,body);return card;
}
function showAssetCards(){
  const d=state.current;if(!d)return;
  const filter=el("visualFilter").value||"all",decisions=d.visual_review?.decisions||{};
  const visible=d.assets.filter(asset=>{
    const status=decisions[asset.asset_id]?.decision||"pending";
    return filter==="all"||filter===status;
  });
  el("assetGrid").replaceChildren(...visible.map(a=>assetCard(
    d.flow_id,a,decisions[a.asset_id],d.review_status==="human_release_review_passed"
  )));
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
    reviewCounts(d);
    showAssetCards();
    const finished=d.review_status==="human_release_review_passed";
    for(const input of el("reviewForm").querySelectorAll("input,textarea,button"))input.disabled=finished;
    el("visualReviewer").disabled=finished;
    finalGate(d);
    el("reviewMessage").textContent=finished?"✓ 人間のレビュー記録済み。公開は無効です。":"確認した項目のみチェックしてください。";
    flowButtons();
  }catch(error){toast("実行データを読み込めません: "+error.message);}
}
async function trackJob(){
  if(state.checking||!state.job)return;state.checking=true;
  try{
    while(state.job){
      const id=state.job,job=await api("/api/jobs/"+urlId(id));
      renderStages(job.stages);
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
el("visualFilter").addEventListener("change",showAssetCards);
el("visualReviewer").addEventListener("input",()=>{el("reviewerName").value=el("visualReviewer").value;});
el("reviewerName").addEventListener("input",()=>{el("visualReviewer").value=el("reviewerName").value;});
el("launchForm").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!state.canStart||state.job||!el("recipeSelect").value)return;
  try{
    const result=await api("/api/actions/run",{
      method:"POST",headers:{"Content-Type":"application/json","X-MAF-Action":"cockpit"},
      body:JSON.stringify({recipe:el("recipeSelect").value})
    });
    state.job=result.job_id;renderStages([]);launchEnabled();jobMessage("制作ライン起動","Godot QAと実描画を実行します。");trackJob();
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
  if(!state.current.visual_review?.ready_for_final_review){
    el("reviewMessage").textContent="個別の素材をすべてPassにしてから最終レビューへ進んでください。";
    return;
  }
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
