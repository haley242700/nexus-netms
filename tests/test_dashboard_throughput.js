const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const source = fs.readFileSync("apps/nexus/network-dashboard/app.js", "utf8");
const flowSource = fs.readFileSync("apps/nexus/network-dashboard/flow-field.js", "utf8");
const page = fs.readFileSync("apps/nexus/network-dashboard/index.html", "utf8");
const styles = fs.readFileSync("apps/nexus/network-dashboard/styles.css", "utf8");
assert(!styles.includes(".health-visual { display: none; }"), "窄屏不得隐藏网络健康度");
assert(styles.includes(".hero { flex-direction: column; }"));
assert(page.includes("<span>网络健康度</span>") && page.includes("<span>无线质量分</span>"), "双圆环必须使用醒目的中文名称");
assert(page.includes('id="quality-score"') && page.includes('id="quality-ring"'));
assert(page.includes('data-score-kind="health"') && page.includes('data-score-kind="quality"'), "两个圆环都必须可点击");
assert(page.includes('id="score-modal"') && page.includes('id="score-detail-rows"'), "缺少评分明细弹窗");
assert(styles.includes("width: min(520px,100%)"), "弹窗必须使用紧凑宽度");
assert(styles.includes("rgba(29,40,63,.30)") && styles.includes("rgba(10,17,30,.30)") && styles.includes("blur(28px)"), "弹窗必须使用 70% 透明毛玻璃背景");
assert(styles.includes(".score-modal.is-open") && source.includes("setTimeout(hide, 220)"), "弹窗必须支持渐入渐出");
assert(!source.includes("radio-track") && !source.includes("radio-fill"), "AP 矩阵信道编号旁不得显示进度条");
assert(source.includes("channel.automatic ? \" · 自动\" : \"\""), "AP 矩阵必须标识自动信道");
assert(source.includes("r.metric.mode === \"auto\""), "AP 矩阵必须读取信道模式");
assert(page.includes('id="flow-canvas"'));
assert(page.includes('class="flow-node-meter wan-meter"><span>上行总量'));
assert(page.includes('class="flow-node-meter home-meter"><span>下行总量'));
assert(!page.includes('id="top-client-list"'));
assert(!source.includes("renderTopClients(topClients"));
const elements = {};
const frames = [];
const flowUpdates = [];
const context = {
  window: {matchMedia: () => ({matches: true}), nexusFlowUpdate: (down, up, totalDown, totalUp) => flowUpdates.push({down, up, totalDown, totalUp})},
  performance: {now: () => 0},
  requestAnimationFrame: callback => { frames.push(callback); return frames.length; },
  cancelAnimationFrame() {},
  document: {
    getElementById(id) {
      if (!elements[id]) {
        const children = {};
        elements[id] = {
          textContent: "", innerHTML: "",
          querySelector(selector) {
            if (!children[selector]) children[selector] = {textContent: ""};
            return children[selector];
          },
        };
      }
      return elements[id];
    },
  },
};
context.$ = context.document.getElementById;
context.value = row => Number(row.value[1]);
context.round = (v, n = 1) => Number.isFinite(v) ? v.toFixed(n) : "--";
context.esc = value => String(value ?? "");
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("const REFRESH_INTERVAL"), source.indexOf("let refreshing")), context);
vm.runInContext(source.slice(source.indexOf("const AP_ORDER"), source.indexOf("function renderAps")), context);
vm.runInContext(source.slice(source.indexOf("function renderAps"), source.indexOf("const CLIENT_PAGE_SIZE")), context);

assert.strictEqual(context.formatRate(0).value, "0");
assert.strictEqual(context.formatRate(12500000).unit, "Mbps");
assert.strictEqual(Number(context.formatRate(12500000).value), 100);
assert.strictEqual(context.formatBytes(1073741824).unit, "GB");
assert.strictEqual(context.bytesText(1536), "1.50 KB");
assert.strictEqual(context.rssiExperienceScore(-50), 97, "-50 dBm 仅扣 3 个信号子分");
assert.strictEqual(context.rssiExperienceScore(-60), 90);
assert.strictEqual(context.rssiExperienceScore(-67), 75);
assert.strictEqual(context.rssiExperienceScore(-75), 40);
assert.strictEqual(context.rssiExperienceScore(-85), 0);
assert(Math.abs(context.rssiExperienceScore(-55) - 93.5) < .001, "锚点之间应线性过渡");
assert.strictEqual(context.wirelessQuality(-50, 0, 10, [{value:[0,"10"]},{value:[0,"20"]}]), 96, "无线质量按 50/30/20 加权");
assert.strictEqual(context.wirelessQuality(-40, 0, 10, [{value:[0,"0"]}]), 100);
assert.strictEqual(context.wirelessQuality(-90, 10, 10, [{value:[0,"100"]}]), 0);
assert.strictEqual(context.wirelessQuality(-70, 2, 10, [{value:[0,"50"]}]), 65);
const healthDetails = context.networkHealthDetails(6, 6, true, [{value:[0,"1"]}], 0);
assert.strictEqual(healthDetails.score, 100);
assert.strictEqual(healthDetails.metrics.length, 4, "健康度明细包含三项得分和弱信号扣分");
assert.strictEqual(healthDetails.metrics[0].contribution, 65);
assert.strictEqual(context.networkHealthDetails(5, 6, false, [{value:[0,"25"]}], 2).score, 55);
const qualityDetails = context.wirelessQualityDetails(-50, 0, 10, [{value:[0,"10"]},{value:[0,"20"]}]);
assert.strictEqual(qualityDetails.score, 96);
assert.strictEqual(qualityDetails.metrics.length, 3);
assert.strictEqual(qualityDetails.metrics[0].contribution, 48.5);
assert.strictEqual(qualityDetails.metrics[1].contribution, 30);
assert.strictEqual(qualityDetails.metrics[2].contribution, 17);
assert(source.includes("setInterval(refresh, REFRESH_INTERVAL)"));

context.renderGateway([
  {metric: {direction: "down"}, value: [0, "12500000"]},
  {metric: {direction: "up"}, value: [0, "1250000"]},
], [
  {metric: {direction: "down"}, value: [0, "1073741824"]},
  {metric: {direction: "up"}, value: [0, "536870912"]},
]);
assert.strictEqual(Number(elements["gateway-rate"].textContent), 110);
assert(elements["gateway-down"].textContent.includes("100"));
assert(!source.includes('animateNumber("gateway.total"'), "总累计不得与上下行分开动画");
assert.deepStrictEqual(flowUpdates.at(-1), {down: 12500000, up: 1250000, totalDown: 1073741824, totalUp: 536870912});
assert(flowSource.includes("paintCounters(now)"));
assert(flowSource.includes("formatKb"));
assert(flowSource.includes('document.getElementById("gateway-history")'));
assert(flowSource.includes('totalElement.textContent = `${formatKb(estimatedDown + estimatedUp)} KB`;'), "总累计必须同帧显示上下行之和");
const anchorSource = flowSource.match(/function nextTotalAnchor\(actual, estimated\) \{[\s\S]*?\n  \}/)?.[0];
assert(anchorSource, "缺少单调不减校准函数");
const nextTotalAnchor = new Function(`${anchorSource}; return nextTotalAnchor;`)();
assert.strictEqual(nextTotalAnchor(100, 120), 120, "滞后样本不得让数字倒退");
assert.strictEqual(nextTotalAnchor(130, 120), 130, "实际值领先时应向前校准");
assert.strictEqual(nextTotalAnchor(0, 120), 120, "计数器重置不得让数字倒退");

context.renderApThroughput([
  {metric: {ap: "一楼主卧AP", direction: "up"}, value: [0, "1000000"]},
  {metric: {ap: "一楼主卧AP", direction: "down"}, value: [0, "1000000"]},
  {metric: {ap: "负一客厅AP", direction: "down"}, value: [0, "500000"]},
], [
  {metric: {ap: "一楼主卧AP", direction: "up"}, value: [0, "1048576"]},
  {metric: {ap: "一楼主卧AP", direction: "down"}, value: [0, "1048576"]},
]);
assert(elements["ap-throughput-list"].innerHTML.includes("一楼主卧AP"));
assert(elements["ap-throughput-list"].innerHTML.includes("16.00 Mbps"));
assert(elements["ap-throughput-list"].innerHTML.includes("2.00 MB"));

context.testAps = [
  {metric: {ap: "负一卧室AP", model: "EAP162", ip: "192.168.110.10"}, value: [0, "1"]},
];
context.testChannels = [
  {metric: {ap: "负一卧室AP", band: "2.4G", mode: "auto"}, value: [0, "1"]},
  {metric: {ap: "负一卧室AP", band: "5G", mode: "manual"}, value: [0, "149"]},
];
vm.runInContext("renderAps(testAps, [], [], testChannels)", context);
assert(elements["ap-grid"].innerHTML.includes("CH 1 · 自动"), "自动信道必须显示当前编号和模式");
assert(elements["ap-grid"].innerHTML.includes("CH 149</span>"), "手动信道不得添加自动标识");

const animated = {textContent: ""};
context.window.matchMedia = () => ({matches: false});
context.animateNumber("animation-test", animated, 0, String);
context.animateNumber("animation-test", animated, 100, String);
assert.strictEqual(frames.length, 1);
frames.shift()(350);
assert(Number(animated.textContent) > 0 && Number(animated.textContent) < 100);
frames.shift()(700);
assert.strictEqual(Number(animated.textContent), 100);
console.log("吞吐测试通过：实时/累计、单位换算、数据流联动、3 秒定时及数字滚动均正确。");
