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
for (const id of ["speed-toggle", "result-download", "result-upload", "result-ping", "result-jitter", "context-client", "context-ap", "context-rssi", "context-rate", "speed-analysis", "analysis-overall", "analysis-metrics", "percentile-charts", "analysis-combo"]) {
  if (!page.includes(`id="${id}"`)) throw new Error(`测速页缺少 ${id}`);
}
if (page.includes("percentile-rows") || page.includes("percentile-scroll")) throw new Error("旧分位表格应完全移除");
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
if (!page.includes("无线 1000 / 1600 / 2401 Mbps 为 85 / 93 / 100 分")) throw new Error("缺少无线速率评分标准");
if (!page.includes("有线 1000 / 1600 / 2000 / 2500 Mbps 为 80 / 88 / 95 / 100 分")) throw new Error("缺少有线速率评分标准");
if (!page.includes("无线延迟</strong>≤5 ms 满分")) throw new Error("缺少无线延迟评分标准");
if (!css.includes("@media (max-width:720px)")) throw new Error("缺少移动端布局");
if (!css.includes("grid-template-columns: repeat(2,minmax(0,1fr))") || !css.includes(".percentile-charts { grid-template-columns: 1fr; }")) throw new Error("分位图表缺少桌面双列或移动单列布局");
const numberSource = app.match(/function analysisNumber\([\s\S]*?\n\}/)?.[0];
const deltaSource = app.match(/function deltaText\([\s\S]*?\n\}/)?.[0];
const chartSource = app.match(/function percentileChart\([\s\S]*?\n\}/)?.[0];
if (!numberSource || !deltaSource || !chartSource) throw new Error("缺少分位图表渲染函数");
const renderPercentileChart = new Function(`${numberSource}\n${deltaSource}\n${chartSource}; return percentileChart;`)();
const latencyChart = renderPercentileChart({key:"ping", label:"网络延迟"}, {current:4, unit:"ms", higherBetter:false, deltaMedian:-1, superiority:80, percentiles:{1:2,5:3,20:4,50:5,80:7,95:9,99:12}});
if ((latencyChart.match(/class="chart-node/g) || []).length !== 7) throw new Error("分位图表必须包含七个节点");
if (!latencyChart.includes("P1 · 最佳") || !latencyChart.includes("P99 · 最差")) throw new Error("低延迟指标的最佳／最差方向错误");
if (!latencyChart.includes("chart-current-arrow") || !latencyChart.includes("本次 · P20") || latencyChart.includes("chart-current-line") || !latencyChart.includes("P50 中位") || latencyChart.includes("NaN")) throw new Error("本次成绩箭头或延迟百分位方向异常");
const downloadChart = renderPercentileChart({key:"download", label:"下载速率"}, {current:1600, unit:"Mbps", higherBetter:true, deltaMedian:100, superiority:80, percentiles:{1:500,5:800,20:1000,50:1500,80:1600,95:2000,99:2400}});
if (!downloadChart.includes("本次 · P80") || !downloadChart.includes("P99 · 最佳") || !downloadChart.includes("P1 · 最差")) throw new Error("速率百分位或最佳／最差方向异常");
if (!css.includes("--current: #ff7ad9") || !css.includes("color: var(--current)")) throw new Error("本次成绩缺少独立强调色");
const flatChart = renderPercentileChart({key:"jitter", label:"抖动"}, {current:0, unit:"ms", higherBetter:false, deltaMedian:0, superiority:50, percentiles:{1:0,5:0,20:0,50:0,80:0,95:0,99:0}});
if (flatChart.includes("NaN") || flatChart.includes("Infinity")) throw new Error("相同分位值导致图表坐标异常");
const rateSource = app.match(/function wirelessRate\([\s\S]*?\n\}/)?.[0];
if (!rateSource) throw new Error("缺少协商速率格式化");
const formatWirelessRate = new Function(`${rateSource}; return wirelessRate;`)();
if (formatWirelessRate("1441M") !== "1441 Mbps" || formatWirelessRate(1201) !== "1201 Mbps") throw new Error("协商速率单位格式化错误");
const compose = fs.readFileSync("apps/nexus/docker-compose.yaml", "utf8");
for (const token of ["SPEEDTEST_DB_PATH: /app/speedtest/speedtest.db", "./speedtest:/app/speedtest", 'command: ["python", "/app/dashboard/dashboard_server.py"]', "PYTHONPATH: /app"]) {
  if (!compose.includes(token)) throw new Error(`测速分析容器配置缺少 ${token}`);
}
console.log("测速页面验证通过：导航、评分、历史分位、AP 上下文、移动端和容器配置完整。");
