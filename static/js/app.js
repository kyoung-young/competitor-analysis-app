/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   STATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
let currentJobId     = null;
let pollTimer        = null;
let currentPdfFile   = null;
let currentHistoryId = null;
let allHistory       = [];
let selectedSlot     = { 1: null, 2: null };
let selectedFiles    = [];

const RING_C = 132; // 2π × r21

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   INIT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
document.addEventListener("DOMContentLoaded", () => {
  loadHistory();
  // Enter key triggers analysis from URL input
  document.getElementById("competitorUrl")?.addEventListener("keydown", e => {
    if (e.key === "Enter") startAnalysis();
  });
  document.getElementById("ownUrl")?.addEventListener("keydown", e => {
    if (e.key === "Enter") startAnalysis();
  });
});

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
async function startAnalysis() {
  const compUrl = document.getElementById("competitorUrl").value.trim();
  const ownUrl  = document.getElementById("ownUrl").value.trim();
  const errEl   = document.getElementById("formError");

  // reset error
  errEl.textContent = "";
  errEl.classList.add("hidden");

  if (!compUrl) {
    errEl.textContent = "경쟁사 URL을 입력해주세요.";
    errEl.classList.remove("hidden");
    document.getElementById("competitorUrl").focus();
    return;
  }

  const fd = new FormData();
  fd.append("url", compUrl);
  if (ownUrl) fd.append("own_url", ownUrl);
  selectedFiles.forEach(f => fd.append("attachments", f));

  // disable button & show progress
  setBtn(false);
  showPanel("progressCard");
  setRingProgress(5);
  setProgressMsg("분석 준비 중...");
  setStepState("crawling", "active");

  try {
    const res  = await fetch("/analyze", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) { showError(data.error); return; }
    currentJobId = data.job_id;
    pollStatus();
  } catch (e) {
    showError("서버 연결 실패: " + e.message);
  }
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   POLLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function pollStatus() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    if (!currentJobId) return;
    try {
      const res = await fetch(`/status/${currentJobId}`);
      const job = await res.json();
      applyProgress(job);
      if      (job.status === "done")  onDone(job);
      else if (job.status === "error") showError(job.message || "알 수 없는 오류");
      else                             pollStatus();
    } catch { pollStatus(); }
  }, 1500);
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   PROGRESS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function applyProgress(job) {
  const pct = job.progress || 0;

  // progress bar
  const pbar = document.querySelector(".pbar-fill");
  if (pbar) pbar.style.width = pct + "%";

  // ring
  setRingProgress(pct);
  const pctEl = document.getElementById("progPct");
  if (pctEl) {
    // HTML: <span id="progPct">0<small>%</small></span>
    // firstChild is the text node with the number
    if (pctEl.firstChild && pctEl.firstChild.nodeType === 3) {
      pctEl.firstChild.textContent = pct;
    } else {
      pctEl.textContent = pct + "%";
    }
  }

  // message
  setProgressMsg(job.message || "");

  // steps
  const DONE_MAP = {
    crawling:   ["crawling"],
    analyzing:  ["crawling", "analyzing"],
    generating: ["crawling", "analyzing", "generating"],
    saving:     ["crawling", "analyzing", "generating"],
    done:       ["crawling", "analyzing", "generating", "done"],
  };
  const doneSet = new Set(DONE_MAP[job.status] || []);
  const ORDER   = ["crawling", "analyzing", "generating", "done"];

  ORDER.forEach(key => {
    const inDone = doneSet.has(key);
    const isLast = key === [...doneSet].at(-1);
    const active = isLast && job.status !== "done" && job.status !== "saving";
    if (!inDone)  setStepState(key, "pending");
    else if (active) setStepState(key, "active");
    else             setStepState(key, "done");
  });
}

function setStepState(key, state) {
  const el = document.getElementById("step-" + key);
  if (!el) return;
  el.classList.remove("active", "done");
  if (state === "active" || state === "done") el.classList.add(state);

  const dot   = el.querySelector(".s-dot");
  const label = el.querySelector(".s-state");
  if (dot)   dot.textContent   = state === "done" ? "✓" : state === "active" ? "·" : "";
  if (label) label.textContent = state === "done" ? "완료" : state === "active" ? "진행중" : "";
}

function setRingProgress(pct) {
  const arc = document.getElementById("progArc");
  if (arc) arc.style.strokeDashoffset = (RING_C * (1 - pct / 100)).toFixed(2);
}

function setProgressMsg(msg) {
  const el = document.getElementById("progressMsg");
  if (el) el.textContent = msg;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   DONE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function onDone(job) {
  currentPdfFile   = job.pdf_filename;
  currentHistoryId = job.history_id;

  showPanel("resultCard");
  setBtn(true);

  const riEl = document.getElementById("resultInfo");
  if (riEl) {
    const name    = job.company_name    ? esc(job.company_name)    : "";
    const ownName = job.own_company_name ? esc(job.own_company_name) : "";
    riEl.textContent = name
      ? (ownName ? `${name} vs ${ownName} 분석 완료` : `${name} 분석이 완료되었습니다`)
      : "보고서 생성이 완료되었습니다";
  }

  loadHistory();
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   DOWNLOAD / RESET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function downloadReport() {
  if (currentPdfFile) triggerDownload("/download/" + currentPdfFile, currentPdfFile);
}

function triggerDownload(href, name) {
  const a = document.createElement("a");
  a.href = href; a.download = name; a.click();
}

function resetForm() {
  currentJobId = currentPdfFile = currentHistoryId = null;
  if (pollTimer) clearTimeout(pollTimer);
  selectedFiles = [];

  const ids = { competitorUrl: "", ownUrl: "", fileInput: "" };
  Object.entries(ids).forEach(([id, v]) => {
    const el = document.getElementById(id);
    if (el) el.value = v;
  });

  const errEl = document.getElementById("formError");
  if (errEl) { errEl.textContent = ""; errEl.classList.add("hidden"); }

  renderFileList();
  setRingProgress(0);

  // Reset ring number
  const pctEl = document.getElementById("progPct");
  if (pctEl) {
    if (pctEl.firstChild && pctEl.firstChild.nodeType === 3) pctEl.firstChild.textContent = "0";
    else pctEl.textContent = "0%";
  }

  const pbar = document.querySelector(".pbar-fill");
  if (pbar) pbar.style.width = "0%";

  ["crawling", "analyzing", "generating", "done"].forEach(s => setStepState(s, "pending"));
  setProgressMsg("잠시 기다려주세요...");

  setBtn(true);
  showPanel("inputCard");
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   UI HELPERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function showPanel(id) {
  ["inputCard", "progressCard", "resultCard", "errorCard"].forEach(pid => {
    const el = document.getElementById(pid);
    if (el) el.classList.toggle("hidden", pid !== id);
  });
}

function showError(msg) {
  showPanel("errorCard");
  const el = document.getElementById("errorMsg");
  if (el) el.textContent = msg;
  setBtn(true);
}

function setBtn(enabled) {
  const btn = document.getElementById("analyzeBtn");
  if (btn) btn.disabled = !enabled;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   FILE UPLOAD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function onDragOver(e)   { e.preventDefault(); document.getElementById("dropzone")?.classList.add("drag-over"); }
function onDragLeave()   { document.getElementById("dropzone")?.classList.remove("drag-over"); }
function onDrop(e)       { e.preventDefault(); onDragLeave(); addFiles([...e.dataTransfer.files]); }
function onFileSelect(e) { addFiles([...e.target.files]); }

function addFiles(files) {
  const ok = new Set(["pdf", "png", "jpg", "jpeg", "gif", "webp"]);
  files.forEach(f => {
    const ext = f.name.split(".").pop().toLowerCase();
    if (ok.has(ext) && !selectedFiles.find(x => x.name === f.name))
      selectedFiles.push(f);
  });
  renderFileList();
  syncFileInput();
}

function removeFile(name) {
  selectedFiles = selectedFiles.filter(f => f.name !== name);
  renderFileList();
  syncFileInput();
}

function renderFileList() {
  const el = document.getElementById("fileList");
  if (!el) return;
  el.innerHTML = selectedFiles.map(f => `
    <div class="file-chip">
      <span>${f.name.split(".").pop().toUpperCase()}</span>
      <span>${esc(f.name)}</span>
      <span class="file-chip-remove" onclick="removeFile('${f.name.replace(/'/g, "\\'")}')">✕</span>
    </div>`).join("");
}

function syncFileInput() {
  const fi = document.getElementById("fileInput");
  if (!fi) return;
  const dt = new DataTransfer();
  selectedFiles.forEach(f => dt.items.add(f));
  fi.files = dt.files;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   SIDEBAR / HISTORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function toggleHistory() {
  const panel   = document.getElementById("historyPanel");
  const overlay = document.getElementById("sidebarOverlay");
  if (!panel) return;

  const opening = !panel.classList.contains("open");
  panel.classList.toggle("open", opening);
  overlay?.classList.toggle("hidden", !opening);

  if (opening) loadHistory();
}

async function loadHistory() {
  try {
    const res = await fetch("/history");
    allHistory = await res.json();
    renderHistory(allHistory);
    const cnt = document.getElementById("historyCount");
    if (cnt) cnt.textContent = allHistory.length;
  } catch {}
}

function filterHistory(q) {
  const lq = q.toLowerCase();
  renderHistory(lq
    ? allHistory.filter(e =>
        e.url.toLowerCase().includes(lq) ||
        (e.summary?.company_name || "").toLowerCase().includes(lq))
    : allHistory);
}

function renderHistory(list) {
  const el = document.getElementById("historyList");
  if (!el) return;

  if (!list.length) {
    el.innerHTML = `<div class="sb-empty">기록이 없습니다</div>`;
    return;
  }

  el.innerHTML = list.map(e => {
    const company  = e.summary?.company_name || "미상";
    const hasOwn   = e.own_url ? " + 자사 비교" : "";
    const s1 = selectedSlot[1]?.id === e.id ? "slot-active" : "";
    const s2 = selectedSlot[2]?.id === e.id ? "slot-active" : "";

    return `<div class="history-item ${s1} ${s2}" id="hi-${e.id}" onclick="selectHistItem('${e.id}')">
      <div class="hi-r1">
        <span class="hi-co">${esc(company)}</span>
        <span class="hi-mode">전체 분석${hasOwn}</span>
      </div>
      <div class="hi-url">${esc(e.url)}</div>
      <div class="hi-dt">${fmtDate(e.created_at)}</div>
      <div class="hi-acts">
        <button onclick="event.stopPropagation(); histDl('${e.pdf_filename}')">다운로드</button>
        <button onclick="event.stopPropagation(); histDel('${e.id}')">삭제</button>
      </div>
    </div>`;
  }).join("");
}

function selectHistItem(id) {
  const entry = allHistory.find(e => e.id === id);
  if (!entry) return;
  if (selectedSlot[1]?.id === id) { clearDockSlot(1); return; }
  if (selectedSlot[2]?.id === id) { clearDockSlot(2); return; }
  if (!selectedSlot[1])      setDockSlot(1, entry);
  else if (!selectedSlot[2]) setDockSlot(2, entry);
  else                       setDockSlot(1, entry);
}

function histDl(filename) {
  if (filename) triggerDownload("/download/" + filename, filename);
}

async function histDel(id) {
  if (!confirm("이 분석 기록을 삭제할까요?")) return;
  await fetch("/history/" + id, { method: "DELETE" });
  allHistory = allHistory.filter(e => e.id !== id);
  if (selectedSlot[1]?.id === id) clearDockSlot(1);
  if (selectedSlot[2]?.id === id) clearDockSlot(2);
  const cnt = document.getElementById("historyCount");
  if (cnt) cnt.textContent = allHistory.length;
  renderHistory(allHistory);
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   COMPARE DOCK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function setDockSlot(n, entry) {
  selectedSlot[n] = entry;
  const slot = document.querySelector(`.dock-slot[data-slot="${n}"]`);
  if (!slot) return;
  const ph  = slot.querySelector(".dock-ph");
  const sel = slot.querySelector(".dock-sel");
  if (ph)  ph.classList.add("hidden");
  if (sel) {
    sel.classList.remove("hidden");
    const urlEl = sel.querySelector(".dock-sel-url");
    const dtEl  = sel.querySelector(".dock-sel-dt");
    if (urlEl) urlEl.textContent = trunc(entry.url, 30);
    if (dtEl)  dtEl.textContent  = fmtDate(entry.created_at);
  }
  updateDockBtn();
  renderHistory(allHistory);
}

function clearDockSlot(n) {
  selectedSlot[n] = null;
  const slot = document.querySelector(`.dock-slot[data-slot="${n}"]`);
  if (!slot) return;
  const ph  = slot.querySelector(".dock-ph");
  const sel = slot.querySelector(".dock-sel");
  if (ph)  ph.classList.remove("hidden");
  if (sel) sel.classList.add("hidden");
  updateDockBtn();
  renderHistory(allHistory);
}

function updateDockBtn() {
  const btn = document.querySelector(".btn-dock");
  if (btn) btn.disabled = !(selectedSlot[1] && selectedSlot[2]);
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   COMPARE MODAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
async function runComparison() {
  if (!selectedSlot[1] || !selectedSlot[2]) return;
  openCompareModal(selectedSlot[1].id, selectedSlot[2].id);
}

async function openCompareModal(id1, id2) {
  const modal = document.getElementById("compareModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  await loadCompare(id1, id2);
}

function closeCompareModal() {
  document.getElementById("compareModal")?.classList.add("hidden");
}

function handleOverlayClick(e) {
  if (e.target === document.getElementById("compareModal")) closeCompareModal();
}

async function loadCompare(id1, id2) {
  const body = document.getElementById("compareModalBody");
  if (!body) return;
  body.innerHTML = `<div class="modal-spin">
    <svg width="26" height="26" viewBox="0 0 36 36" class="spin-svg">
      <circle cx="18" cy="18" r="14" fill="none" stroke="#E5E5E5" stroke-width="3"/>
      <circle cx="18" cy="18" r="14" fill="none" stroke="#111" stroke-width="3"
        stroke-dasharray="22 66" stroke-linecap="round" transform="rotate(-90 18 18)"/>
    </svg>
    비교 분석 로딩 중...</div>`;
  try {
    const res  = await fetch(`/compare/${id1}/${id2}`);
    const data = await res.json();
    body.innerHTML = data.error
      ? `<p style="color:#999;font-size:13px">${esc(data.error)}</p>`
      : buildCompareHTML(data);
  } catch (e) {
    body.innerHTML = `<p style="color:#999;font-size:13px">로드 실패: ${esc(e.message)}</p>`;
  }
}

function buildCompareHTML(d) {
  const m    = d.meta || {};
  const e1   = m.entry1 || {};
  const e2   = m.entry2 || {};
  const sc   = d.strategy_comparison || {};
  const tc   = d.tracking_comparison || {};
  const diffs = d.key_differences || [];
  const synth = d.application_synthesis || {};

  const tools1   = tc.entry1_tools || [];
  const tools2   = tc.entry2_tools || [];
  const allTools = [...new Set([...tools1, ...tools2])];

  function twoUp(label, items1, items2) {
    const col = (items, tag) => `
      <div class="cmp-pane">
        <div class="cmp-pane-label">${tag}</div>
        ${items.length
          ? items.map(x => `<div class="cmp-list-item">· ${esc(x)}</div>`).join("")
          : `<div class="cmp-list-item" style="color:#bbb">—</div>`}
      </div>`;
    return `<div class="cmp-block">
      <div class="cmp-block-title">${label}</div>
      <div class="cmp-two-up">${col(items1, "분석 A")}${col(items2, "분석 B")}</div>
    </div>`;
  }

  return `
    <div class="cmp-meta">
      <div class="cmp-meta-card">
        <div class="cmp-meta-tag">분석 A</div>
        <div class="cmp-meta-url">${esc(e1.url || "")}</div>
        <div class="cmp-meta-info">${fmtDate(e1.created_at || "")}</div>
      </div>
      <div class="cmp-vs-circle">VS</div>
      <div class="cmp-meta-card">
        <div class="cmp-meta-tag">분석 B</div>
        <div class="cmp-meta-url">${esc(e2.url || "")}</div>
        <div class="cmp-meta-info">${fmtDate(e2.created_at || "")}</div>
      </div>
    </div>

    ${diffs.length ? `<div class="cmp-block">
      <div class="cmp-block-title">주요 차이점</div>
      ${diffs.map(x =>
        `<div class="diff-stripe"><strong>${esc(x.category)}</strong> — ${esc(x.description)}</div>`
      ).join("")}
    </div>` : ""}

    ${allTools.length ? `<div class="cmp-block">
      <div class="cmp-block-title">마테크 도구 비교</div>
      <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:6px">
        ${allTools.map(t => {
          const inA = tools1.includes(t), inB = tools2.includes(t);
          const suf = inA && inB ? "" : inA ? " (A)" : " (B)";
          const bg  = inA && inB ? "#111" : "#555";
          return `<span style="padding:3px 9px;border-radius:12px;background:${bg};color:#fff;font-size:11px">${esc(t)}${suf}</span>`;
        }).join("")}
      </div>
    </div>` : ""}

    ${twoUp("영업 전략 인사이트",   sc.sales?.entry1_insights      || [], sc.sales?.entry2_insights      || [])}
    ${twoUp("마케팅 전략 인사이트", sc.marketing?.entry1_insights  || [], sc.marketing?.entry2_insights  || [])}
    ${twoUp("경영 전략 인사이트",   sc.management?.entry1_insights || [], sc.management?.entry2_insights || [])}

    ${synth.combined_immediate_actions?.length ? `<div class="cmp-block">
      <div class="cmp-block-title">통합 즉시 적용 방안</div>
      ${synth.combined_immediate_actions.map((a, i) =>
        `<div style="padding:7px 0;border-bottom:1px solid #eee;font-size:12px">
          <strong style="margin-right:6px">${i + 1}.</strong>${esc(a)}
        </div>`
      ).join("")}
    </div>` : ""}`;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   UTILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ko-KR", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
    });
  } catch { return iso.slice(0, 16).replace("T", " "); }
}

function trunc(s, n) {
  s = String(s);
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
