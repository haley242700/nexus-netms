const $ = id => document.getElementById(id);
const esc = value => String(value ?? "--").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const validNumber = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
const number = (value, digits = 1) => validNumber(value) ? Number(value).toFixed(digits) : "--";
let refreshing = false;
let toastTimer;

function eventTime(timestamp) {
  if (!validNumber(timestamp)) return "--";
  const date = new Date(Number(timestamp) * 1000);
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  return sameDay ? date.toLocaleTimeString("zh-CN", {hour12:false}) : date.toLocaleString("zh-CN", {hour12:false, month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit"});
}

function durationText(seconds) {
  return validNumber(seconds) ? `${Number(seconds).toFixed(seconds < 10 ? 1 : 0)}s` : "--";
}

function setHTML(id, html) {
  const element = $(id);
  const scroll = element.scrollTop;
  element.innerHTML = html;
  element.scrollTop = scroll;
}

function notify(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").classList.add("show");
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), 3500);
}

function renderRoams(events) {
  if (!events.length) {
    setHTML("roam-list", `<div class="empty-events"><strong>暂未记录到漫游</strong>终端切换 AP 后，事件会出现在这里。</div>`);
    return;
  }
  const sourceNames = {history:"历史采样", syslog:"系统日志", "syslog+live":"日志＋采样"};
  setHTML("roam-list", events.map(event => {
    const rssi = Number(event.trigger_rssi);
    return `<div class="event-row roam-columns"><div class="event-identity"><strong>${esc(event.client)}</strong><span>${eventTime(event.ts)}</span><small>${esc(event.mac)}</small></div><div class="roam-path"><span>${esc(event.from_ap)}</span><i>→</i><span>${esc(event.to_ap)}</span></div><span class="event-rssi ${validNumber(event.trigger_rssi) && rssi <= -75 ? "weak" : ""}">${validNumber(event.trigger_rssi) ? Math.round(rssi) : "--"} dBm</span><span class="event-duration">${durationText(event.duration_s)}<small>${sourceNames[event.source] || "实时采样"}</small></span></div>`;
  }).join(""));
}

function renderAnomalies(events) {
  if (!events.length) {
    setHTML("anomaly-list", `<div class="empty-events"><strong>暂无异常离线</strong>非漫游导致的终端或 AP 离线会记录在这里。</div>`);
    return;
  }
  const statusNames = {open:"离线中", recovered:"已恢复", history_end:"历史截止"};
  setHTML("anomaly-list", events.map(event => {
    const type = event.entity_type === "ap" ? "AP" : "终端";
    const end = event.status === "open" ? `已持续 ${durationText(Date.now()/1000-event.start_ts)}` : event.status === "recovered" ? `持续 ${durationText(event.end_ts-event.start_ts)}` : "历史日志截止";
    const evidence = Array.isArray(event.evidence) ? event.evidence : [];
    const evidenceHtml = evidence.length ? `<details class="event-evidence"><summary>判断依据 <span>${evidence.length}</span></summary><div class="evidence-list">${evidence.map(item => `<div class="evidence-item"><div><strong>${esc(item.label)}</strong><time>${eventTime(item.ts)}</time></div>${item.detail ? `<p>${esc(item.detail)}</p>` : ""}${item.raw ? `<code>${esc(item.raw)}</code>` : ""}</div>`).join("")}</div></details>` : "";
    const emptyEvidence = evidence.length ? "" : `<small class="reason-empty">暂无补充证据</small>`;
    return `<article class="anomaly-item"><div class="event-row anomaly-columns"><div class="event-identity"><strong>${esc(event.name)}</strong><span>${eventTime(event.start_ts)} · ${type} · ${esc(event.conclusion)}</span><small>${esc(event.ap)} · ${end}</small></div><div class="event-cause"><span class="event-reason ${event.reason === "弱信号线索" ? "weak" : ""}"><i></i>${esc(event.reason)}</span>${emptyEvidence}</div><span class="event-status ${esc(event.status)}">${statusNames[event.status] || "未知"}</span></div>${evidenceHtml}</article>`;
  }).join(""));
}

function render(data) {
  const roam = data.roam, anomalies = data.anomalies;
  $("events-since").textContent = data.since || "今天";
  $("roam-total").textContent = roam.count || 0;
  $("roam-duration").textContent = number(roam.avgDuration, 1);
  $("duration-samples").textContent = `${roam.durationSamples || 0} 个有效样本`;
  $("roam-rssi").textContent = number(roam.avgRssi, 1);
  const apStats = Array.isArray(roam.apStats) ? roam.apStats : [];
  $("ap-stats").innerHTML = apStats.length ? apStats.map(item => `<article title="${esc(item.name)}：接入 ${item.joinCount}，离开 ${item.leaveCount}"><span class="ap-stat-name">${esc(item.name)}</span><small class="ap-stat-join"><b>${Number(item.joinCount) || 0}</b><em>入</em></small><small class="ap-stat-leave"><b>${Number(item.leaveCount) || 0}</b><em>离</em></small></article>`).join("") : `<div class="ap-stats-empty">暂无 AP 统计数据</div>`;
  $("anomaly-total").textContent = anomalies.total;
  $("anomaly-split").textContent = `终端 ${anomalies.clientCount} · AP ${anomalies.apCount}`;
  $("active-anomalies").textContent = anomalies.active;
  $("reason-strip").innerHTML = anomalies.reasons.length ? anomalies.reasons.map(item => `<span>${esc(item.reason)}<b>${item.count}</b></span>`).join("") : `<span>暂无原因分类数据</span>`;
  renderRoams(roam.recent);
  renderAnomalies(anomalies.recent);
  $("live-text").textContent = "LIVE";
  $("live-pill").classList.remove("error");
}

async function refreshEvents() {
  if (refreshing) return;
  refreshing = true;
  try {
    const response = await fetch("/api/events", {cache:"no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    console.error(error);
    $("live-text").textContent = "STALE";
    $("live-pill").classList.add("error");
    notify("事件数据刷新失败，页面保留上一次结果");
  } finally {
    refreshing = false;
  }
}

function updateClock() {
  $("clock").textContent = new Date().toLocaleTimeString("zh-CN", {hour12:false});
}
updateClock();
setInterval(updateClock, 1000);
refreshEvents();
setInterval(refreshEvents, 3000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshEvents(); });
