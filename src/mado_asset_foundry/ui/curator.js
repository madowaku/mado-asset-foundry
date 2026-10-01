const state = { runs: [], run: null, summary: null, filter: "all", selectedId: null };
const $ = (id) => document.getElementById(id);

async function request(url, options = {}) {
  const response = await fetch(url, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

async function bootstrap() {
  const payload = await request("/api/runs");
  state.runs = payload.runs;
  renderRunSelect();
  if (state.runs.length) await loadRun(state.runs[0].run_id);
  else renderEmpty();
}

function renderRunSelect() {
  const select = $("runSelect");
  select.innerHTML = state.runs.map(run => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id)} · ${escapeHtml(run.recipe_id)}</option>`).join("");
  select.disabled = !state.runs.length;
  select.onchange = () => loadRun(select.value);
}

async function loadRun(runId) {
  const payload = await request(`/api/runs/${encodeURIComponent(runId)}`);
  state.run = payload.run;
  state.summary = payload.summary;
  $("runSelect").value = runId;
  const visible = filteredAssets();
  state.selectedId = visible[0]?.asset_id ?? null;
  render();
}

function filteredAssets() {
  const assets = state.run?.assets || [];
  if (state.filter === "all") return assets;
  if (state.filter === "favorite") return assets.filter(asset => asset.favorite);
  return assets.filter(asset => asset.curation_decision === state.filter);
}

function render() {
  if (!state.run || !state.run.assets.length) return renderEmpty();
  $("empty").hidden = true;
  $("grid").hidden = false;
  renderSummary();
  renderGrid();
  renderInspector();
}

function renderEmpty() {
  $("empty").hidden = false;
  $("grid").hidden = true;
  $("inspector").hidden = true;
}

function renderSummary() {
  const s = state.summary;
  $("reviewedCount").textContent = s.reviewed;
  $("keepCount").textContent = s.keep;
  $("maybeCount").textContent = s.maybe;
  $("rejectCount").textContent = s.reject;
  $("favoriteCount").textContent = s.favorite;
  $("progressBar").style.width = `${s.total ? (s.reviewed / s.total) * 100 : 0}%`;
}

function renderGrid() {
  const assets = filteredAssets();
  if (assets.length && !assets.some(asset => asset.asset_id === state.selectedId)) state.selectedId = assets[0].asset_id;
  if (!assets.length) state.selectedId = null;
  $("grid").innerHTML = assets.map(asset => {
    const decision = asset.curation_decision || "unreviewed";
    return `<article class="card ${decision} ${asset.asset_id === state.selectedId ? "selected" : ""}" data-id="${escapeHtml(asset.asset_id)}" tabindex="0">
      <div class="card-image"><img loading="lazy" src="/api/runs/${encodeURIComponent(state.run.run_id)}/assets/${encodeURIComponent(asset.asset_id)}/image" alt="${escapeHtml(asset.subject || asset.asset_id)}"></div>
      <span class="badge">${escapeHtml(decision)}</span>${asset.favorite ? '<span class="star">★</span>' : ""}
      <div class="card-meta"><strong>${escapeHtml(asset.subject || "Untitled candidate")}</strong><span>${escapeHtml(asset.asset_id)}</span></div>
    </article>`;
  }).join("");
  document.querySelectorAll(".card").forEach(card => card.addEventListener("click", () => selectAsset(card.dataset.id)));
}

function renderInspector() {
  const asset = selectedAsset();
  $("inspector").hidden = !asset;
  if (!asset) return;
  const assets = filteredAssets();
  $("selectedPosition").textContent = `${assets.findIndex(item => item.asset_id === asset.asset_id) + 1} / ${assets.length}`;
  $("selectedSubject").textContent = asset.subject || "Untitled candidate";
  $("selectedId").textContent = asset.asset_id;
  document.querySelectorAll("[data-action]").forEach(button => {
    button.classList.toggle("active", button.dataset.action === asset.curation_decision || (button.dataset.action === "favorite" && asset.favorite));
  });
}

function selectedAsset() {
  return state.run?.assets.find(asset => asset.asset_id === state.selectedId) || null;
}

function selectAsset(assetId) {
  state.selectedId = assetId;
  renderGrid();
  renderInspector();
  document.querySelector(`.card[data-id="${CSS.escape(assetId)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function mutateSelected(action) {
  const asset = selectedAsset();
  if (!asset) return;
  const body = action === "favorite" ? { favorite: !asset.favorite } : { decision: action };
  const payload = await request(`/api/runs/${encodeURIComponent(state.run.run_id)}/assets/${encodeURIComponent(asset.asset_id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  const index = state.run.assets.findIndex(item => item.asset_id === asset.asset_id);
  state.run.assets[index] = payload.asset;
  state.summary = payload.summary;
  const nextAssets = filteredAssets();
  if (!nextAssets.some(item => item.asset_id === state.selectedId)) {
    const fallbackIndex = Math.min(index, Math.max(0, nextAssets.length - 1));
    state.selectedId = nextAssets[fallbackIndex]?.asset_id || null;
  }
  render();
}

function moveSelection(delta) {
  const assets = filteredAssets();
  if (!assets.length) return;
  let index = assets.findIndex(asset => asset.asset_id === state.selectedId);
  if (index < 0) index = 0;
  index = Math.max(0, Math.min(assets.length - 1, index + delta));
  selectAsset(assets[index].asset_id);
}

function setFilter(filter) {
  state.filter = filter;
  document.querySelectorAll("[data-filter]").forEach(button => button.classList.toggle("active", button.dataset.filter === filter));
  state.selectedId = filteredAssets()[0]?.asset_id || null;
  render();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

document.addEventListener("click", event => {
  const filter = event.target.closest("[data-filter]");
  if (filter) setFilter(filter.dataset.filter);
  const action = event.target.closest("[data-action]");
  if (action) mutateSelected(action.dataset.action);
});

document.addEventListener("keydown", event => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
  const actions = { "1": "reject", "2": "maybe", "3": "keep", "4": "favorite" };
  if (actions[event.key]) { event.preventDefault(); mutateSelected(actions[event.key]); }
  if (event.key === "ArrowRight") { event.preventDefault(); moveSelection(1); }
  if (event.key === "ArrowLeft") { event.preventDefault(); moveSelection(-1); }
});

bootstrap().catch(error => {
  console.error(error);
  $("empty").hidden = false;
  $("empty").innerHTML = `<h2>Curator failed to load</h2><p>${escapeHtml(error.message)}</p>`;
});
