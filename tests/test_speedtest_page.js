const fs = require("fs");

const dashboard = "apps/nexus/network-dashboard";
const pages = [
  ["index.html", 'class="active" href="/"'],
  ["events.html", 'class="active" href="/events"'],
  ["speedtest.html", 'class="active" href="/speedtest"'],
];
for (const [name, active] of pages) {
  const html = fs.readFileSync(`${dashboard}/${name}`, "utf8");
  for (const path of ['href="/"', 'href="/events"', 'href="/speedtest"']) {
    if (!html.includes(path)) throw new Error(`${name} 缺少三页导航 ${path}`);
  }
  if (!html.includes(active)) throw new Error(`${name} 当前页导航状态错误`);
  if (!html.includes("nexus-netms")) throw new Error(`${name} 缺少统一品牌`);
}

const page = fs.readFileSync(`${dashboard}/speedtest.html`, "utf8");
const app = fs.readFileSync(`${dashboard}/speedtest-app.js`, "utf8");
const css = fs.readFileSync(`${dashboard}/speedtest.css`, "utf8");
for (const id of ["speed-toggle", "result-download", "result-upload", "result-ping", "result-jitter", "context-client", "context-ap", "context-rssi", "context-rate"]) {
  if (!page.includes(`id="${id}"`)) throw new Error(`测速页缺少 ${id}`);
}
if (!page.includes('<base href="/speedtest/engine/">')) throw new Error("Web Worker 路径未固定");
if (!page.includes('/speedtest/engine/speedtest.js')) throw new Error("缺少 LibreSpeed 引擎");
if (!app.includes('fetch("/api/ap-info"')) throw new Error("缺少 AP 查询");
if (app.includes("/api/ap-info?")) throw new Error("AP 查询不得接受浏览器伪造 IP");
if (!app.includes('engine.setParameter("telemetry_level", "off")')) throw new Error("不应默认开启测速遥测");
if (!app.includes("refreshApInfo();")) throw new Error("缺少 AP 刷新");
if (!css.includes("@media (max-width:720px)")) throw new Error("缺少移动端布局");
const rateSource = app.match(/function wirelessRate\([\s\S]*?\n\}/)?.[0];
if (!rateSource) throw new Error("缺少协商速率格式化");
const formatWirelessRate = new Function(`${rateSource}; return wirelessRate;`)();
if (formatWirelessRate("1441M") !== "1441 Mbps" || formatWirelessRate(1201) !== "1201 Mbps") throw new Error("协商速率单位格式化错误");
console.log("测速页面验证通过：三页导航、统一品牌、测速指标、AP 上下文、速率单位和移动端结构完整。");
