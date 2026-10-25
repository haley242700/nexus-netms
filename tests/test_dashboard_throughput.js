const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const source = fs.readFileSync("apps/nexus/network-dashboard/app.js", "utf8");
const flowSource = fs.readFileSync("apps/nexus/network-dashboard/flow-field.js", "utf8");
const page = fs.readFileSync("apps/nexus/network-dashboard/index.html", "utf8");
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
context.esc = value => String(value ?? "");
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf("const REFRESH_INTERVAL"), source.indexOf("let refreshing")), context);
vm.runInContext(source.slice(source.indexOf("const AP_ORDER"), source.indexOf("function renderAps")), context);

assert.strictEqual(context.formatRate(0).value, "0");
assert.strictEqual(context.formatRate(12500000).unit, "Mbps");
assert.strictEqual(Number(context.formatRate(12500000).value), 100);
assert.strictEqual(context.formatBytes(1073741824).unit, "GB");
assert.strictEqual(context.bytesText(1536), "1.50 KB");
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
assert.strictEqual(elements["gateway-history"].textContent, "1.50 GB");
assert.deepStrictEqual(flowUpdates.at(-1), {down: 12500000, up: 1250000, totalDown: 1073741824, totalUp: 536870912});
assert(flowSource.includes("paintCounters(now)"));
assert(flowSource.includes("formatKb"));

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
