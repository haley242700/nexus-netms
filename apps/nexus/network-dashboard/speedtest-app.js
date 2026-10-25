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

engine.onupdate = renderUpdate;
engine.onend = aborted => {
  setReady(aborted ? "STOPPED" : "DONE");
  text("test-stage", aborted ? "测速已停止" : "测速完成");
  if (aborted) {
    setProgress(0);
    return;
  }
  const when = new Date().toLocaleTimeString("zh-CN", {hour12:false, hour:"2-digit", minute:"2-digit"});
  text("last-test", when);
  text("last-test-ap", apSnapshot?.connected ? `测速环境：${apSnapshot.apName}` : "本次测速未获取到 AP 信息");
  refreshApInfo();
};

function setContextValue(id, value, fallback = "--") {
  const cleaned = String(value ?? "").trim();
  text(id, cleaned && !["NULL", "UNDEFINED", "NONE"].includes(cleaned.toUpperCase()) ? cleaned : fallback);
}

async function refreshApInfo() {
  if (apLoading) return;
  apLoading = true;
  $("ap-refresh").disabled = true;
  try {
    const response = await fetch("/api/ap-info", {cache:"no-store"});
    const data = await response.json();
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
    apSnapshot = null;
    $("context-indicator").className = "context-indicator error";
    text("ap-context-title", "AP 信息暂不可用");
    text("ap-context-note", "查询失败不影响测速，可稍后手动刷新");
  } finally {
    apLoading = false;
    $("ap-refresh").disabled = false;
  }
}

$("speed-toggle").addEventListener("click", toggleTest);
$("ap-refresh").addEventListener("click", refreshApInfo);
window.addEventListener("beforeunload", () => { if (engine.getState() === 3) engine.abort(); });
setClock();
setInterval(setClock, 1000);
setReady();
refreshApInfo();
setInterval(() => { if (engine.getState() !== 3) refreshApInfo(); }, 15000);
