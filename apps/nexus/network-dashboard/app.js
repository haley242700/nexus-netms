const $ = (id) => document.getElementById(id);
const value = (row) => Number(row?.value?.[1] ?? 0);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const round = (v, n = 1) => Number.isFinite(v) ? v.toFixed(n) : "--";
const REFRESH_INTERVAL = 3000;
const ANIMATION_DURATION = 700;
const numberAnimations = new Map();

function formatRate(bytesPerSecond) {
  const bits = Math.max(0, Number(bytesPerSecond) || 0) * 8;
  if (bits < 1) return {value: "0", unit: "Kbps"};
  if (bits >= 1e9) return {value: (bits / 1e9).toFixed(2), unit: "Gbps"};
  if (bits >= 1e6) return {value: (bits / 1e6).toFixed(bits >= 1e8 ? 1 : 2), unit: "Mbps"};
  return {value: (bits / 1e3).toFixed(bits >= 1e5 ? 0 : 1), unit: "Kbps"};
}

function formatBytes(bytes) {
  const amount = Math.max(0, Number(bytes) || 0);
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(Math.max(1, amount)) / Math.log(1024)));
  const scaled = amount / (1024 ** index);
  return {value: scaled.toFixed(index === 0 ? 0 : scaled >= 100 ? 1 : 2), unit: units[index]};
}

function rateText(bytesPerSecond) {
  const rate = formatRate(bytesPerSecond);
  return `${rate.value} ${rate.unit}`;
}

function bytesText(bytes) {
  const total = formatBytes(bytes);
  return `${total.value} ${total.unit}`;
}

function setLiveText(id, text) {
  const element = $(id);
  if (element) element.textContent = text;
}

function animateNumber(key, element, target, formatter) {
  if (!element) return;
  if (target === null || target === undefined || !Number.isFinite(Number(target))) {
    const state = numberAnimations.get(key);
    if (state?.frame) cancelAnimationFrame(state.frame);
    numberAnimations.delete(key);
    element.textContent = "--";
    return;
  }
  const next = Math.max(0, Number(target) || 0);
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  let state = numberAnimations.get(key);
  if (!state) {
    state = {current: next, frame: 0};
    numberAnimations.set(key, state);
    element.textContent = formatter(next);
    return;
  }
  if (state.frame) cancelAnimationFrame(state.frame);
  const start = state.current;
  if (reduced || Math.abs(next - start) < .001) {
    state.current = next;
    state.frame = 0;
    element.textContent = formatter(next);
    return;
  }
  const started = performance.now();
  const tick = now => {
    const progress = Math.min(1, (now - started) / ANIMATION_DURATION);
    state.current = start + (next - start) * (1 - (1 - progress) ** 3);
    element.textContent = formatter(state.current);
    state.frame = progress < 1 ? requestAnimationFrame(tick) : 0;
  };
  state.frame = requestAnimationFrame(tick);
}

function animateContainer(id, items) {
  const container = $(id);
  items.forEach(item => animateNumber(item.key, container.querySelector(item.selector), item.value, item.formatter));
}

let refreshing = false;
let toastTimer;

async function query(promql) {
  const response = await fetch(`/api/query?query=${encodeURIComponent(promql)}`, {cache: "no-store"});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (data.status !== "success") throw new Error(data.error || "Prometheus query failed");
  return data.data.result;
}

async function rangeQuery(promql) {
  const end = Math.floor(Date.now() / 1000);
  const params = new URLSearchParams({query: promql, start: end - 3600, end, step: 60});
  const response = await fetch(`/api/query_range?${params}`, {cache: "no-store"});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (data.status !== "success") throw new Error(data.error || "Prometheus range query failed");
  return data.data.result;
}

function notify(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").classList.add("show");
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), 3500);
}

function drawLatency(series) {
  const points = (series[0]?.values || []).map(p => Number(p[1])).filter(Number.isFinite);
  if (points.length < 2) {
    $("latency-line").setAttribute("d", "");
    $("latency-area").setAttribute("d", "");
    return;
  }
  const min = Math.min(...points), max = Math.max(...points);
  const spread = Math.max(max - min, .4);
  const low = Math.max(0, min - spread * .35), high = max + spread * .35;
  const coords = points.map((v, i) => [i * 600 / (points.length - 1), 185 - (v - low) / (high - low) * 155]);
  const line = coords.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" ");
  $("latency-line").setAttribute("d", line);
  $("latency-area").setAttribute("d", `${line} L600,210 L0,210 Z`);
  $("chart-current").textContent = round(points.at(-1), 2);
}

const AP_ORDER = ["一楼主卧AP", "一楼北卧AP", "一楼客厅AP", "负一客厅AP", "负一卧室AP", "负一电脑房AP"];

function sumByDirection(rows, direction) {
  return rows.filter(row => row.metric.direction === direction).reduce((sum,row) => sum + value(row), 0);
}

function totalsBy(rows, label) {
  const totals = new Map();
  rows.forEach(row => totals.set(row.metric[label], (totals.get(row.metric[label]) || 0) + value(row)));
  return totals;
}

function renderGateway(rows, totalRows) {
  const down = sumByDirection(rows, "down"), up = sumByDirection(rows, "up");
  const totalDown = sumByDirection(totalRows, "down"), totalUp = sumByDirection(totalRows, "up");
  const total = formatRate(down + up);
  setLiveText("gateway-unit", total.unit);
  animateNumber("gateway.rate", $("gateway-rate"), down + up, v => formatRate(v).value);
  animateNumber("gateway.down", $("gateway-down"), down, rateText);
  animateNumber("gateway.up", $("gateway-up"), up, rateText);
  animateNumber("gateway.total", $("gateway-history"), totalDown + totalUp, bytesText);
  window.nexusFlowUpdate?.(down, up, totalDown, totalUp);
}

function renderApThroughput(rows, totalRows) {
  const rates = totalsBy(rows, "ap"), totals = totalsBy(totalRows, "ap");
  const ordered = [...rates.entries()].sort((a,b) => {
    const ai = AP_ORDER.indexOf(a[0]), bi = AP_ORDER.indexOf(b[0]);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
  });
  const max = Math.max(1, ...rates.values());
  $("ap-throughput-list").innerHTML = ordered.map(([ap,rate], index) => {
    const load = Math.max(0, Math.min(100, rate / max * 100));
    return `<div class="ap-rate" style="--load:${load.toFixed(1)}%"><span>${esc(ap)}</span><strong data-rate="${index}">${rateText(rate)}</strong><small>关联累计 <b data-total="${index}">${bytesText(totals.get(ap) || 0)}</b></small></div>`;
  }).join("") || `<div class="loading">暂无 AP 吞吐数据</div>`;
  animateContainer("ap-throughput-list", ordered.flatMap(([ap,rate], index) => [
    {key: `ap.${ap}.rate`, selector: `[data-rate="${index}"]`, value: rate, formatter: rateText},
    {key: `ap.${ap}.total`, selector: `[data-total="${index}"]`, value: totals.get(ap) || 0, formatter: bytesText},
  ]));
}

function renderTopClients(rows, totalRows) {
  const totals = totalsBy(totalRows, "mac");
  const top = [...rows].sort((a,b) => value(b) - value(a)).slice(0,3);
  $("top-client-list").innerHTML = top.map((row,index) => `
    <div class="top-client"><span class="top-rank">0${index + 1}</span><div class="top-client-name"><strong title="${esc(row.metric.client)}">${esc(row.metric.client)}</strong><span data-rate="${index}">${rateText(value(row))}</span><small>累计 <b data-total="${index}">${totals.has(row.metric.mac) ? bytesText(totals.get(row.metric.mac)) : "--"}</b></small></div></div>
  `).join("") || `<div class="loading">暂无终端流量</div>`;
  animateContainer("top-client-list", top.flatMap((row,index) => [
    {key: `top.${row.metric.mac}.rate`, selector: `[data-rate="${index}"]`, value: value(row), formatter: rateText},
    {key: `top.${row.metric.mac}.total`, selector: `[data-total="${index}"]`, value: totals.has(row.metric.mac) ? totals.get(row.metric.mac) : null, formatter: bytesText},
  ]));
}

function renderAps(aps, clientRows, pingRows, utilRows, channelRows) {
  const clients = new Map(clientRows.map(r => [r.metric.ap, value(r)]));
  const pings = new Map(pingRows.map(r => [r.metric.name, value(r)]));
  const utils = new Map(utilRows.map(r => [`${r.metric.ap}|${r.metric.band}`, value(r)]));
  const channels = new Map(channelRows.map(r => [`${r.metric.ap}|${r.metric.band}`, value(r)]));
  const order = new Map(["一楼主卧AP", "一楼北卧AP", "一楼客厅AP", "负一客厅AP", "负一卧室AP", "负一电脑房AP"].map((v,i) => [v,i]));
  aps.sort((a,b) => (order.get(a.metric.ap) ?? 99) - (order.get(b.metric.ap) ?? 99));
  $("ap-grid").innerHTML = aps.map(row => {
    const m = row.metric, online = value(row) === 1;
    const radio = ["2.4G", "5G"].map(band => {
      const util = utils.get(`${m.ap}|${band}`), channel = channels.get(`${m.ap}|${band}`);
      return `<div class="radio-row"><span>${band}</span><div class="radio-track"><div class="radio-fill" style="width:${Math.max(0, Math.min(100, util || 0))}%"></div></div><span>${channel ? Math.round(channel) : "--"}</span></div>`;
    }).join("");
    return `<article class="ap-card"><div class="ap-title"><strong>${esc(m.ap)}</strong><span class="online-state" style="color:${online ? "var(--green)" : "var(--red)"}"><i></i>${online ? "ONLINE" : "OFFLINE"}</span></div><div class="ap-model">${esc(m.model)} · ${esc(m.ip)}</div><div class="ap-numbers"><div class="ap-clients"><strong>${Math.round(clients.get(m.ap) || 0)}</strong><span>关联终端</span></div><div class="ap-ping">${round(pings.get(m.ap), 1)} ms<span>LAN LATENCY</span></div></div>${radio}</article>`;
  }).join("");
}

const CLIENT_PAGE_SIZE = 7;
let clientPage = 1;
let latestClientRows = [];
let latestRxRateRows = [];
let latestClientTraffic = [];
let latestClientTotals = [];

function renderClients(rows, rxRateRows, throughputRows = [], totalRows = []) {
  latestClientRows = rows;
  latestRxRateRows = rxRateRows;
  latestClientTraffic = throughputRows;
  latestClientTotals = totalRows;
  const rxRates = new Map(rxRateRows.map(row => [row.metric.mac, value(row)]));
  const rates = totalsBy(throughputRows, "mac"), totals = totalsBy(totalRows, "mac");
  rows.sort((a,b) => value(a) - value(b));
  const pageCount = Math.max(1, Math.ceil(rows.length / CLIENT_PAGE_SIZE));
  clientPage = Math.min(Math.max(clientPage, 1), pageCount);
  const start = (clientPage - 1) * CLIENT_PAGE_SIZE;
  const visible = rows.slice(start, start + CLIENT_PAGE_SIZE);
  $("client-list").innerHTML = visible.map((row,index) => {
    const mac = row.metric.mac;
    const rssi = value(row), width = Math.max(3, Math.min(100, rssi + 100));
    const level = rssi < -75 ? "bad" : rssi < -67 ? "warn" : "";
    const negotiated = rxRates.has(mac) ? `${Math.round(rxRates.get(mac))} Mbps` : "--";
    return `<div class="client-row"><div class="client-name"><strong>${esc(row.metric.client)}</strong><span>${esc(row.metric.ap)} · ${esc(row.metric.ssid)} · 协商 <b>${negotiated}</b></span><span class="client-traffic">实时 <b data-rate="${index}">${rateText(rates.get(mac) || 0)}</b> · 累计 <b data-total="${index}">${totals.has(mac) ? bytesText(totals.get(mac)) : "--"}</b></span></div><div class="signal-track"><div class="signal-fill ${level}" style="width:${width}%"></div></div><div class="client-rssi">${Math.round(rssi)} <small>dBm</small></div></div>`;
  }).join("") || `<div class="loading">暂无终端数据</div>`;
  animateContainer("client-list", visible.flatMap((row,index) => [
    {key: `client.${row.metric.mac}.rate`, selector: `[data-rate="${index}"]`, value: rates.get(row.metric.mac) || 0, formatter: rateText},
    {key: `client.${row.metric.mac}.total`, selector: `[data-total="${index}"]`, value: totals.has(row.metric.mac) ? totals.get(row.metric.mac) : null, formatter: bytesText},
  ]));
  $("client-page").textContent = `${clientPage} / ${pageCount}`;
  $("client-range").textContent = rows.length ? `${start + 1}–${Math.min(start + CLIENT_PAGE_SIZE, rows.length)} / ${rows.length} 台` : "0 台";
  $("client-prev").disabled = clientPage <= 1;
  $("client-next").disabled = clientPage >= pageCount;
}

$("client-prev").addEventListener("click", () => {
  if (clientPage > 1) {
    clientPage--;
    renderClients(latestClientRows, latestRxRateRows, latestClientTraffic, latestClientTotals);
  }
});
$("client-next").addEventListener("click", () => {
  if (clientPage < Math.ceil(latestClientRows.length / CLIENT_PAGE_SIZE)) {
    clientPage++;
    renderClients(latestClientRows, latestRxRateRows, latestClientTraffic, latestClientTotals);
  }
});

function renderChannels(utilRows, channelRows) {
  const channels = new Map(channelRows.map(r => [`${r.metric.ap}|${r.metric.band}`, value(r)]));
  utilRows.sort((a,b) => value(b) - value(a));
  $("channel-list").innerHTML = utilRows.slice(0, 7).map(row => {
    const m = row.metric, util = value(row), channel = channels.get(`${m.ap}|${m.band}`);
    return `<div class="channel-row"><div class="channel-name"><strong>${esc(m.ap)}</strong><span>CHANNEL ${channel ? Math.round(channel) : "--"}</span></div><span class="band-badge">${esc(m.band)}</span><div class="channel-track"><div class="channel-fill" style="width:${Math.min(100, util)}%"></div></div><span class="channel-value">${Math.round(util)}%</span></div>`;
  }).join("");
}

let pageActive = true;

async function refresh() {
  if (refreshing || !pageActive) return;
  refreshing = true;
  try {
    const [aps, clients, apClients, pings, utils, channels, totalRows, fiveRows, rssiRows, weakRows, mloRows, collectorRows, gatewayTraffic, gatewayTotals, apTraffic, apTotals, rxRates, clientTraffic, clientTotals, history] = await Promise.all([
      query('reyee_ap_online{kind="ap"} * on(ap,sn) group_left(model,ip) reyee_ap_info'),
      query('reyee_client_rssi_dbm'),
      query('reyee_ap_clients{kind="ap"}'),
      query('probe_duration_seconds{job="ap_ping"} * 1000'),
      query('reyee_ap_channel_utilization_percent'),
      query('reyee_ap_channel'),
      query('reyee_clients_total'),
      query('count(reyee_client_rssi_dbm{band="5G"}) or vector(0)'),
      query('avg(reyee_client_rssi_dbm)'),
      query('count(reyee_client_rssi_dbm < -75) or vector(0)'),
      query('sum(reyee_client_mlo_enabled) or vector(0)'),
      query('reyee_exporter_collect_success'),
      query('reyee_gateway_throughput_bps'),
      query('reyee_gateway_traffic_bytes_total'),
      query('reyee_ap_throughput_bps'),
      query('reyee_ap_traffic_bytes_total'),
      query('reyee_client_rxrate_mbps'),
      query('reyee_client_throughput_bps'),
      query('reyee_client_traffic_bytes_total'),
      rangeQuery('avg(probe_duration_seconds{job="ap_ping"}) * 1000')
    ]);
    if (!pageActive) return;
    const online = aps.filter(r => value(r) === 1).length;
    const avgPing = pings.length ? pings.reduce((s,r) => s + value(r), 0) / pings.length : 0;
    const avgRssi = value(rssiRows[0]);
    const weak = value(weakRows[0]);
    const collector = value(collectorRows[0]) === 1;
    const health = Math.max(0, Math.min(100, Math.round((aps.length ? online / aps.length : 0) * 65 + (collector ? 20 : 0) + (pings.every(r => value(r) < 20) ? 15 : 5) - weak * 2)));
    $("ap-online").textContent = online;
    $("ap-total").textContent = aps.length;
    $("client-total").textContent = Math.round(value(totalRows[0]));
    $("five-g").textContent = Math.round(value(fiveRows[0]));
    $("avg-rssi").textContent = Math.round(avgRssi);
    $("signal-quality").textContent = avgRssi > -60 ? "信号优秀" : avgRssi > -70 ? "信号良好" : "值得关注";
    $("avg-ping").textContent = round(avgPing, 1);
    $("weak-count").textContent = Math.round(weak);
    $("health-score").textContent = health;
    $("health-label").textContent = health >= 95 ? "运行卓越" : health >= 85 ? "运行良好" : "需要关注";
    $("health-ring").style.strokeDashoffset = 351.86 * (1 - health / 100);
    $("collector-status").textContent = collector ? "NORMAL" : "STALE";
    $("mlo-count").textContent = Math.round(value(mloRows[0]));
    $("live-text").textContent = "LIVE";
    $("live-pill").classList.remove("error");
    renderGateway(gatewayTraffic, gatewayTotals);
    renderApThroughput(apTraffic, apTotals);
    renderAps(aps, apClients, pings, utils, channels);
    renderClients(clients, rxRates, clientTraffic, clientTotals);
    renderChannels(utils, channels);
    drawLatency(history);
  } catch (error) {
    if (!pageActive) return;
    console.error(error);
    $("live-text").textContent = "STALE";
    $("live-pill").classList.add("error");
    notify("数据刷新失败，页面保留上一次结果");
  } finally {
    refreshing = false;
  }
}

function updateClock() {
  $("clock").textContent = new Date().toLocaleTimeString("zh-CN", {hour12: false});
}
function handleVisibility() {
  if (!document.hidden) refresh();
}
updateClock();
const clockTimer = setInterval(updateClock, 1000);
refresh();
const refreshTimer = setInterval(refresh, REFRESH_INTERVAL);
document.addEventListener("visibilitychange", handleVisibility);
window.nexusPageCleanup = () => {
  pageActive = false;
  clearInterval(clockTimer);
  clearInterval(refreshTimer);
  document.removeEventListener("visibilitychange", handleVisibility);
  for (const state of numberAnimations.values()) {
    if (state.frame) cancelAnimationFrame(state.frame);
  }
  numberAnimations.clear();
};
