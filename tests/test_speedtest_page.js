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
  if (!html.includes('src="/navigation.js"')) throw new Error(`${name} 缺少无刷新导航`);
}

const navigation = fs.readFileSync(`${dashboard}/navigation.js`, "utf8");
for (const token of ["nexusPageCleanup", "history.pushState", 'window.addEventListener("popstate"', 'script.type = "module"', "warmPage"]) {
  if (!navigation.includes(token)) throw new Error(`无刷新导航缺少 ${token}`);
}
for (const name of ["app.js", "events.js", "speedtest-app.js"]) {
  const script = fs.readFileSync(`${dashboard}/${name}`, "utf8");
  if (!script.includes("window.nexusPageCleanup")) throw new Error(`${name} 缺少离开页面清理`);
}

const page = fs.readFileSync(`${dashboard}/speedtest.html`, "utf8");
const app = fs.readFileSync(`${dashboard}/speedtest-app.js`, "utf8");
const css = fs.readFileSync(`${dashboard}/speedtest.css`, "utf8");
for (const id of ["speed-toggle", "result-download", "result-upload", "result-ping", "result-jitter", "context-client", "context-ap", "context-rssi", "context-rate", "speed-analysis", "analysis-overall", "analysis-metrics", "percentile-rows", "analysis-combo"]) {
  if (!page.includes(`id="${id}"`)) throw new Error(`测速页缺少 ${id}`);
}
if (!page.includes('<base href="/speedtest/engine/">')) throw new Error("Web Worker 路径未固定");
if (!page.includes('/speedtest/engine/speedtest.js')) throw new Error("缺少 LibreSpeed 引擎");
if (!app.includes('fetch("/api/ap-info"')) throw new Error("缺少 AP 查询");
if (app.includes("/api/ap-info?")) throw new Error("AP 查询不得接受浏览器伪造 IP");
if (!app.includes('engine.setParameter("telemetry_level", "off")')) throw new Error("不应默认开启测速遥测");
if (!app.includes("refreshApInfo();")) throw new Error("缺少 AP 刷新");
if (!app.includes('fetch("/api/speedtest-results"')) throw new Error("缺少测速结果保存");
if (!app.includes("[1,5,20,50,80,95,99]")) throw new Error("缺少七档历史分位");
if (!app.includes("saveSpeedtestAnalysis(latestData)")) throw new Error("测速完成未触发分析");
if (!page.includes("下载 40% · 上传 25% · 延迟 20% · 抖动 15%")) throw new Error("缺少评分权重说明");
if (!page.includes("无线 2401 Mbps、有线 2500 Mbps 分别为 100 分")) throw new Error("缺少有线/无线速率满分标准");
if (!page.includes("无线延迟</strong>≤5 ms 满分")) throw new Error("缺少无线延迟评分标准");
if (!css.includes("@media (max-width:720px)")) throw new Error("缺少移动端布局");
const rateSource = app.match(/function wirelessRate\([\s\S]*?\n\}/)?.[0];
if (!rateSource) throw new Error("缺少协商速率格式化");
const formatWirelessRate = new Function(`${rateSource}; return wirelessRate;`)();
if (formatWirelessRate("1441M") !== "1441 Mbps" || formatWirelessRate(1201) !== "1201 Mbps") throw new Error("协商速率单位格式化错误");
const compose = fs.readFileSync("apps/nexus/docker-compose.yaml", "utf8");
for (const token of ["SPEEDTEST_DB_PATH: /app/speedtest/speedtest.db", "./speedtest:/app/speedtest", 'command: ["python", "/app/dashboard/dashboard_server.py"]', "PYTHONPATH: /app"]) {
  if (!compose.includes(token)) throw new Error(`测速分析容器配置缺少 ${token}`);
}
console.log("测速页面验证通过：导航、评分、历史分位、AP 上下文、移动端和容器配置完整。");
