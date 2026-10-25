const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const source = fs.readFileSync("apps/nexus/network-dashboard/app.js", "utf8");
const start = source.indexOf("const CLIENT_PAGE_SIZE");
const end = source.indexOf("function renderChannels");
assert(start >= 0 && end > start, "找不到终端分页代码");

const elements = {};
const context = {
  window: {matchMedia: () => ({matches: true})},
  cancelAnimationFrame() {},
  requestAnimationFrame() { return 1; },
  document: {
    getElementById(id) {
      if (!elements[id]) {
        const children = {};
        elements[id] = {
          innerHTML: "", textContent: "", disabled: false,
          addEventListener(event, callback) { this[event] = callback; },
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
vm.runInContext(source.slice(source.indexOf("const REFRESH_INTERVAL"), source.indexOf("function renderGateway")), context);
vm.runInContext(source.slice(start, end), context);

const rows = Array.from({length: 27}, (_, i) => ({
  metric: {client: `设备${i + 1}`, mac: `mac-${i + 1}`, ap: "测试AP", ssid: "测试"},
  value: [0, String(-90 + i)],
}));
const rxRates = rows.map((row, i) => ({metric: {mac: row.metric.mac}, value: [0, String(100 + i)]}));
const traffic = rows.map(row => ({metric: {mac: row.metric.mac, direction: "down"}, value: [0, "1000"]}));
const totals = rows.map(row => ({metric: {mac: row.metric.mac, direction: "down"}, value: [0, "1048576"]}));
const visibleCount = () => (elements["client-list"].innerHTML.match(/class="client-row"/g) || []).length;

context.renderClients(rows, rxRates, traffic, totals);
assert.strictEqual(visibleCount(), 7);
assert.strictEqual(elements["client-range"].textContent, "1–7 / 27 台");
assert.strictEqual(elements["client-page"].textContent, "1 / 4");
assert.strictEqual(elements["client-prev"].disabled, true);
assert(elements["client-list"].innerHTML.includes("协商 <b>100 Mbps</b>"));
assert(elements["client-list"].innerHTML.includes("累计 <b"));

elements["client-next"].click();
assert.strictEqual(visibleCount(), 7);
assert.strictEqual(elements["client-range"].textContent, "8–14 / 27 台");
assert(elements["client-list"].innerHTML.includes("协商 <b>107 Mbps</b>"));
elements["client-next"].click();
elements["client-next"].click();
assert.strictEqual(visibleCount(), 6);
assert.strictEqual(elements["client-range"].textContent, "22–27 / 27 台");
assert.strictEqual(elements["client-next"].disabled, true);

context.renderClients(rows.slice(0, 8), rxRates, traffic, totals);
assert.strictEqual(elements["client-page"].textContent, "2 / 2");
assert.strictEqual(visibleCount(), 1);
assert.strictEqual(elements["client-range"].textContent, "8–8 / 8 台");
context.renderClients([], []);
assert.strictEqual(visibleCount(), 0);
assert.strictEqual(elements["client-range"].textContent, "0 台");
assert.strictEqual(elements["client-page"].textContent, "1 / 1");
console.log("分页测试通过：每页 7 台，协商速率、实时/累计流量及翻页状态均正常。");
