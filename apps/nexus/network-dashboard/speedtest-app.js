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

function environmentName(data) {
  for (const key of ["apName", "switchName", "switchModel"]) {
    const value = String(data?.[key] ?? "").trim();
    if (value && !["undefined", "null", "none"].includes(value.toLowerCase())) return value;
  }
  return "未识别接入设备";
}

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
  text("last-test-ap", `测速环境：${environmentName(apSnapshot)}`);
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
  return `较 50% ${delta > 0 ? "+" : ""}${analysisNumber(delta)} ${item.unit} · ${verdict}`;
}

function percentileChart(config, item) {
  const percentiles = [1,5,20,50,80,95,99];
  const numericPoints = percentiles.map(p => ({p, value:Number(item.percentiles[p])}));
  const points = item.higherBetter ? numericPoints : numericPoints.slice().reverse().map((point, index) => ({p:percentiles[index], value:point.value}));
  const current = Number(item.current);
  const values = points.map(point => point.value).filter(Number.isFinite);
  if (Number.isFinite(current)) values.push(current);
  if (!values.length) return "";

  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * 0.14, Math.abs(maximum) * 0.02, 1);
  minimum = Math.max(0, minimum - padding);
  maximum += padding;
  const width = 560;
  const height = 235;
  const left = 24;
  const right = 24;
  const top = 62;
  const bottom = 43;
  const baseline = height - bottom;
  const x = index => left + index * (width - left - right) / (points.length - 1);
  const y = value => top + (maximum - value) * (baseline - top) / (maximum - minimum);
  const coordinates = points.map((point, index) => ({...point, x:x(index), y:y(point.value)}));
  const line = coordinates.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
  const area = `M${coordinates[0].x},${baseline} ${coordinates.map(point => `L${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ")} L${coordinates[coordinates.length - 1].x},${baseline} Z`;
  const median = points.find(point => point.p === 50);
  const best = points[points.length - 1];
  const worst = points[0];
  const direction = `${item.higherBetter ? "数值越高越好" : "数值越低越好"} · 向右更优`;
  const gradientId = `percentile-gradient-${config.key}`;
  const arrowId = `percentile-arrow-${config.key}`;
  const arrowGradientId = `percentile-arrow-gradient-${config.key}`;
  const grid = [0,0.5,1].map(ratio => {
    const gridY = top + ratio * (baseline - top);
    return `<line class="chart-grid" x1="${left}" y1="${gridY}" x2="${width - right}" y2="${gridY}"/>`;
  }).join("");
  const nodes = coordinates.map(point => {
    const role = point.p === best.p ? "最佳" : point.p === worst.p ? "最差" : point.p === 50 ? "中位" : "分位";
    return `<circle class="chart-node ${role === "最佳" ? "best" : role === "最差" ? "worst" : ""}" cx="${point.x}" cy="${point.y.toFixed(2)}" r="${point.p === 50 ? 4.5 : 3.5}"><title>${point.p}% · ${role}：${analysisNumber(point.value)} ${item.unit}</title></circle>`;
  }).join("");
  const labels = coordinates.map(point => `<text class="chart-axis-label" x="${point.x}" y="${height - 15}" text-anchor="middle">${point.p}%</text>`).join("");
  const superiority = Number(item.superiority);
  let currentReference = "";
  if (Number.isFinite(current) && Number.isFinite(superiority)) {
    const currentPercentile = Math.max(1, Math.min(99, superiority));
    const upperIndex = coordinates.findIndex(point => point.p >= currentPercentile);
    let currentX = coordinates[0].x;
    let currentY = coordinates[0].y;
    if (upperIndex < 0) {
      currentX = coordinates[coordinates.length - 1].x;
      currentY = coordinates[coordinates.length - 1].y;
    } else if (upperIndex > 0) {
      const lower = coordinates[upperIndex - 1];
      const upper = coordinates[upperIndex];
      const ratio = (currentPercentile - lower.p) / (upper.p - lower.p);
      currentX = lower.x + (upper.x - lower.x) * ratio;
      currentY = lower.y + (upper.y - lower.y) * ratio;
    }
    const labelX = Math.max(65, Math.min(width - 65, currentX));
    const percentileLabel = Number(currentPercentile.toFixed(1));
    const arrowPath = `M${labelX.toFixed(2)},30 C${labelX.toFixed(2)},43 ${currentX.toFixed(2)},${(currentY - 28).toFixed(2)} ${currentX.toFixed(2)},${(currentY - 9).toFixed(2)}`;
    currentReference = `<rect class="chart-current-badge" x="${(labelX - 44).toFixed(2)}" y="4" width="88" height="21" rx="10.5"/><text class="chart-current-label" x="${labelX.toFixed(2)}" y="18" text-anchor="middle">本次 · ${percentileLabel}%</text><path class="chart-current-arrow" d="${arrowPath}" stroke="url(#${arrowGradientId})" marker-end="url(#${arrowId})"/><circle class="chart-current-halo" cx="${currentX.toFixed(2)}" cy="${currentY.toFixed(2)}" r="9"/><circle class="chart-current-dot" cx="${currentX.toFixed(2)}" cy="${currentY.toFixed(2)}" r="3.5"><title>本次 ${analysisNumber(current)} ${item.unit} · 优劣分位 ${percentileLabel}%</title></circle>`;
  }
  const stat = (label, point, className) => `<div class="${className}"><span>${point.p}% · ${label}</span><strong>${analysisNumber(point.value)}</strong><small>${item.unit}</small></div>`;
  const aria = points.map(point => `${point.p}% ${analysisNumber(point.value)} ${item.unit}`).join("，");

  return `<article class="percentile-card ${config.key}"><div class="percentile-card-head"><div><strong>${config.label}</strong><span>${direction}</span></div><div class="percentile-current"><span>本次</span><strong>${analysisNumber(item.current)} <small>${item.unit}</small></strong></div></div><div class="percentile-stats">${stat("最佳", best, "best")}${stat("中位", median, "median")}${stat("最差", worst, "worst")}</div><svg class="percentile-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${config.label}优劣历史分位，${direction}。${aria}"><defs><linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1"><stop class="chart-fill-start"/><stop class="chart-fill-end" offset="1"/></linearGradient><linearGradient id="${arrowGradientId}" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ff7ad9" stop-opacity=".22"/><stop offset="1" stop-color="#ff7ad9"/></linearGradient><marker id="${arrowId}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path class="chart-current-arrowhead" d="M0,0 L7,3.5 L0,7 L1.8,3.5 Z"/></marker></defs>${grid}<line class="chart-median-line" x1="${left}" y1="${y(median.value).toFixed(2)}" x2="${width - right}" y2="${y(median.value).toFixed(2)}"/><text class="chart-median-label" x="${left}" y="${(y(median.value) - 7).toFixed(2)}">50% 中位</text><path class="chart-area" d="${area}" fill="url(#${gradientId})"/><path class="chart-line" d="${line}"/>${nodes}${labels}${currentReference}</svg><div class="percentile-footer"><span>${deltaText(item)}</span><strong>优于 ${analysisNumber(item.superiority)}% 同组合历史</strong></div></article>`;
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
    $("percentile-charts").innerHTML = ANALYSIS_METRICS.map(config => percentileChart(config, analysis.metrics[config.key])).join("");
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
