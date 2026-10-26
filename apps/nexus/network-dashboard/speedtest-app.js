const $ = id => document.getElementById(id);
const ENGINE_ROOT = "/speedtest/engine";
const CIRCUMFERENCE = 339.292;
let apSnapshot = null;
let apLoading = false;
let latestData = null;
let toastTimer;

const engine = new Speedtest();
engine.setParameter("url_dl", `${ENGINE_ROOT}/backend/garbage.php`);
engine.setParameter("url_ul", `${ENGINE_ROOT}/backend/empty.php`);
engine.setParameter("url_ping", `${ENGINE_ROOT}/backend/empty.php`);
engine.setParameter("url_getIp", `${ENGINE_ROOT}/backend/getIP.php`);
engine.setParameter("url_telemetry", `${ENGINE_ROOT}/results/telemetry.php`);
engine.setParameter("telemetry_level", "off");

function number(value, digits = 2) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return "--";
  return parsed.toFixed(parsed >= 100 && digits === 2 ? 1 : digits);
}

function wirelessRate(value) {
  const cleaned = String(value ?? "").trim();
  if (!cleaned) return "--";
  const parsed = Number.parseFloat(cleaned);
  return Number.isFinite(parsed) ? `${parsed} Mbps` : cleaned;
}

function text(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function notify(message) {
  clearTimeout(toastTimer);
  text("toast", message);
  $("toast").classList.add("show");
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), 3500);
}

function setClock() {
  text("clock", new Date().toLocaleTimeString("zh-CN", {hour12:false}));
}

function setProgress(value) {
  const progress = Math.max(0, Math.min(1, Number(value) || 0));
  $("speed-progress").style.strokeDashoffset = String(CIRCUMFERENCE * (1 - progress));
}

function setReady(label = "READY") {
  document.body.classList.remove("testing");
  $("speed-toggle").classList.remove("running");
  text("speed-toggle-text", latestData ? "重新测速" : "开始测速");
  text("live-text", label);
  text("speed-phase", label);
}

function renderUpdate(data) {
  latestData = data;
  const state = Number(data.testState);
  const running = state >= 0 && state < 4;
  const download = number(data.dlStatus);
  const upload = number(data.ulStatus);
  text("result-download", download);
  text("result-upload", upload);
  text("result-ping", number(data.pingStatus));
  text("result-jitter", number(data.jitterStatus));
  text("download-progress", state === 1 ? `${Math.round((data.dlProgress || 0) * 100)}%` : download === "--" ? "等待测速" : "已采样");
  text("upload-progress", state === 3 ? `${Math.round((data.ulProgress || 0) * 100)}%` : upload === "--" ? "等待测速" : "已采样");

  const stages = {0:"正在建立测速连接", 1:"正在测试下载速率", 2:"正在测量延迟与抖动", 3:"正在测试上传速率", 4:"测速完成", 5:"测速已停止"};
  text("test-stage", stages[state] || "准备就绪");
  if (state === 2) {
    text("speed-live", number(data.pingStatus));
    text("speed-unit", "ms");
    text("speed-phase", "LATENCY");
    setProgress(data.pingProgress);
  } else {
    const uploadActive = state === 3;
    text("speed-live", uploadActive ? upload : download);
    text("speed-unit", "Mbps");
    text("speed-phase", uploadActive ? "UPLOAD" : "DOWNLOAD");
    setProgress(uploadActive ? data.ulProgress : data.dlProgress);
  }
  if (running) {
    document.body.classList.add("testing");
    $("speed-toggle").classList.add("running");
    text("speed-toggle-text", "停止测速");
    text("live-text", "TESTING");
  }
}

function resetResults() {
  latestData = null;
  analysisRequestId++;
  $("analysis-content").hidden = true;
  $("analysis-empty").hidden = false;
  $("analysis-empty").querySelector("strong").textContent = "测速完成后生成最新成绩";
  $("analysis-empty").querySelector("p").textContent = "本次结果保存后，将与当前设备组合的历史成绩对比。";
  text("analysis-sample", "等待测速");
  for (const id of ["result-download", "result-upload", "result-ping", "result-jitter", "speed-live"]) text(id, "--");
  text("speed-unit", "Mbps");
  text("download-progress", "等待测速");
  text("upload-progress", "等待测速");
  setProgress(0);
}

function toggleTest() {
  if (engine.getState() === 3) {
    engine.abort();
    return;
  }
  resetResults();
  refreshApInfo();
  try {
    engine.setParameter("telemetry_extra", JSON.stringify({apInfo: apSnapshot}));
    engine.start();
    text("test-stage", "正在建立测速连接");
    text("live-text", "TESTING");
  } catch (error) {
    setReady("ERROR");
    text("test-stage", "无法启动测速");
    notify("测速引擎启动失败，请刷新页面后重试");
  }
}

let pageActive = true;
let apController = null;

engine.onupdate = renderUpdate;
engine.onend = aborted => {
  if (!pageActive) return;
  setReady(aborted ? "STOPPED" : "DONE");
  text("test-stage", aborted ? "测速已停止" : "测速完成");
  if (aborted) {
    setProgress(0);
    return;
  }
  const when = new Date().toLocaleTimeString("zh-CN", {hour12:false, hour:"2-digit", minute:"2-digit"});
  text("last-test", when);
  text("last-test-ap", apSnapshot?.connected ? `测速环境：${apSnapshot.apName}` : "本次测速未获取到 AP 信息");
  saveSpeedtestAnalysis(latestData);
  refreshApInfo();
};

let analysisRequestId = 0;
const ANALYSIS_METRICS = [
  {key:"download", label:"下载速率", unit:"Mbps"},
  {key:"upload", label:"上传速率", unit:"Mbps"},
  {key:"ping", label:"网络延迟", unit:"ms"},
  {key:"jitter", label:"抖动", unit:"ms"},
];

function analysisNumber(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "--";
  return parsed >= 100 ? parsed.toFixed(1) : parsed.toFixed(2);
}

function deltaText(item) {
  const delta = Number(item.deltaMedian);
  if (!Number.isFinite(delta)) return "等待更多历史样本";
  const better = item.higherBetter ? delta > 0 : delta < 0;
  const verdict = Math.abs(delta) < 0.001 ? "持平" : better ? "更优" : "偏弱";
  return `较 P50 ${delta > 0 ? "+" : ""}${analysisNumber(delta)} ${item.unit} · ${verdict}`;
}

function renderAnalysis(result) {
  const analysis = result.analysis;
  const scores = result.scores;
  $("analysis-empty").hidden = true;
  $("analysis-content").hidden = false;
  text("analysis-overall", analysisNumber(scores.overall));
  text("analysis-grade", scores.grade);
  $("analysis-score-ring").style.setProperty("--score", scores.overall);
  text("analysis-terminal", result.terminal);
  const access = result.identity.accessType === "wireless" ? "无线" : "有线";
  text("analysis-combo", `${access} · ${result.identity.connectionDevice} → ${result.identity.gateway}`);
  text("analysis-sample", `${analysis.sampleSize} 次样本${analysis.reliable ? "" : " · 样本较少"}`);
  $("analysis-metrics").innerHTML = ANALYSIS_METRICS.map(config => {
    const item = analysis.metrics[config.key];
    const comparison = item.percentiles ? `优于 ${analysisNumber(item.superiority)}% 同组合历史` : `还需 ${analysis.needed} 次启用历史对比`;
    return `<article class="analysis-metric"><div class="analysis-metric-head"><span>${config.label}</span><b>${analysisNumber(scores.metrics[config.key])}</b></div><strong>${analysisNumber(item.current)} ${config.unit}</strong><span>${comparison}</span></article>`;
  }).join("");
  const note = analysis.needed ? `当前组合已保存 ${analysis.sampleSize} 次结果，再完成 ${analysis.needed} 次即可计算历史分位。` : !analysis.reliable ? `当前为 ${analysis.sampleSize} 次早期样本，分位和排名仅供参考；达到 ${analysis.reliableSamples} 次后更稳定。` : `基于当前组合的 ${analysis.sampleSize} 次历史结果计算。`;
  text("analysis-history-note", note);
  $("percentile-area").hidden = Boolean(analysis.needed);
  if (!analysis.needed) {
    $("percentile-rows").innerHTML = ANALYSIS_METRICS.map(config => {
      const item = analysis.metrics[config.key];
      const direction = item.higherBetter ? "越高越好" : "越低越好";
      const cells = [1,5,20,50,80,95,99].map(p => `<td>${analysisNumber(item.percentiles[p])}</td>`).join("");
      return `<tr><td><strong>${config.label}</strong><small>${config.unit} · ${direction}</small></td><td>${analysisNumber(item.current)}</td>${cells}<td>${deltaText(item)}</td></tr>`;
    }).join("");
  }
}

async function saveSpeedtestAnalysis(data) {
  const requestId = ++analysisRequestId;
  $("analysis-content").hidden = true;
  $("analysis-empty").hidden = false;
  $("analysis-empty").querySelector("strong").textContent = "正在保存并分析本次成绩…";
  try {
    const response = await fetch("/api/speedtest-results", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({download:data.dlStatus, upload:data.ulStatus, ping:data.pingStatus, jitter:data.jitterStatus}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    if (!pageActive || requestId !== analysisRequestId) return;
    renderAnalysis(result);
  } catch (error) {
    if (!pageActive || requestId !== analysisRequestId) return;
    $("analysis-empty").querySelector("strong").textContent = "结果分析暂时不可用";
    $("analysis-empty").querySelector("p").textContent = error.message || "测速已完成，但结果未能保存";
    text("analysis-sample", "保存失败");
  }
}

function setContextValue(id, value, fallback = "--") {
  const cleaned = String(value ?? "").trim();
  text(id, cleaned && !["NULL", "UNDEFINED", "NONE"].includes(cleaned.toUpperCase()) ? cleaned : fallback);
}

async function refreshApInfo() {
  if (apLoading || !pageActive) return;
  apLoading = true;
  apController = new AbortController();
  $("ap-refresh").disabled = true;
  try {
    const response = await fetch("/api/ap-info", {cache:"no-store", signal:apController.signal});
    const data = await response.json();
    if (!pageActive) return;
    if (!response.ok) throw new Error(data.note || `HTTP ${response.status}`);
    apSnapshot = data;
    const connected = data.connected === true;
    $("context-indicator").className = `context-indicator ${connected ? "ok" : "error"}`;
    text("ap-context-title", connected ? `${data.apName || "未知 AP"} · 当前接入` : "未识别到无线 AP");
    text("ap-context-note", connected ? "测速前与测速后自动刷新" : (data.note || "有线连接或终端未识别，不影响测速"));
    setContextValue("context-client", data.displayName || data.hostName, data.clientIp || "未知设备");
    setContextValue("context-ip", data.clientIp ? `IP ${data.clientIp}` : "IP --");
    setContextValue("context-ap", data.apName);
    setContextValue("context-ssid", data.ssid ? `SSID ${data.ssid}` : "SSID --");
    setContextValue("context-band", data.band);
    setContextValue("context-channel", data.channel ? `信道 ${data.channel}` : "信道 --");
    setContextValue("context-rssi", data.rssi !== "" && data.rssi !== undefined ? `${data.rssi} dBm` : "--");
    setContextValue("context-rate", wirelessRate(data.rxRate));
    $("context-rssi").classList.toggle("weak", Number(data.rssi) <= -75);
  } catch (error) {
    if (!pageActive || error.name === "AbortError") return;
    apSnapshot = null;
    $("context-indicator").className = "context-indicator error";
    text("ap-context-title", "AP 信息暂不可用");
    text("ap-context-note", "查询失败不影响测速，可稍后手动刷新");
  } finally {
    apLoading = false;
    if (pageActive && $("ap-refresh")) $("ap-refresh").disabled = false;
  }
}

function handlePageHide(event) {
  if (!event.persisted && engine.getState() === 3) engine.abort();
}
$("speed-toggle").addEventListener("click", toggleTest);
$("ap-refresh").addEventListener("click", refreshApInfo);
window.addEventListener("pagehide", handlePageHide);
setClock();
const clockTimer = setInterval(setClock, 1000);
setReady();
refreshApInfo();
const apTimer = setInterval(() => { if (engine.getState() !== 3) refreshApInfo(); }, 15000);
window.nexusPageCleanup = () => {
  pageActive = false;
  clearInterval(clockTimer);
  clearInterval(apTimer);
  apController?.abort();
  window.removeEventListener("pagehide", handlePageHide);
  if (engine.getState() === 3) engine.abort();
};
