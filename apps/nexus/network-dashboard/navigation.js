(() => {
  "use strict";

  const PAGE_SCRIPT = "/navigation.js";
  let navigating = false;
  let scriptVersion = 0;
  const warmedPages = new Set();

  function warmPage(url) {
    if (warmedPages.has(url.href)) return;
    warmedPages.add(url.href);
    fetch(url.href, { credentials: "same-origin" }).catch(() => {
      warmedPages.delete(url.href);
    });
  }

  function loadScript(src) {
    if (src === PAGE_SCRIPT) return Promise.resolve();
    const isEngine = src.includes("/speedtest/engine/speedtest.js");
    if (isEngine && window.Speedtest) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const url = new URL(src, location.origin);
      // 业务脚本使用独立模块作用域；LibreSpeed 保持其原生全局引擎接口。
      if (!isEngine) {
        script.type = "module";
        url.searchParams.set("nav", String(++scriptVersion));
      }
      script.src = url.href;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`页面脚本加载失败：${src}`));
      document.head.appendChild(script);
    });
  }

  function addPageStyles(nextDocument) {
    const existing = new Set(Array.from(document.querySelectorAll('link[rel="stylesheet"]'), link => new URL(link.href, location.origin).pathname));
    for (const link of nextDocument.querySelectorAll('link[rel="stylesheet"]')) {
      const url = new URL(link.getAttribute("href"), location.origin);
      if (existing.has(url.pathname)) continue;
      const style = document.createElement("link");
      style.rel = "stylesheet";
      style.href = url.href;
      document.head.appendChild(style);
      existing.add(url.pathname);
    }
  }

  async function navigate(url, updateHistory = true) {
    if (navigating) return;
    if (updateHistory && url.pathname === location.pathname && !url.hash) return;
    navigating = true;
    document.documentElement.classList.add("page-navigating");
    try {
      const response = await fetch(url.href, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const nextDocument = new DOMParser().parseFromString(await response.text(), "text/html");
      if (!nextDocument.body || !nextDocument.querySelector(".shell")) throw new Error("目标页面结构无效");

      const cleanup = window.nexusPageCleanup;
      window.nexusPageCleanup = null;
      if (typeof cleanup === "function") cleanup();

      const nextBase = nextDocument.querySelector("base[href]");
      let currentBase = document.querySelector("base[href]");
      if (nextBase) {
        if (!currentBase) {
          currentBase = document.createElement("base");
          document.head.prepend(currentBase);
        }
        currentBase.href = nextBase.getAttribute("href");
      } else {
        currentBase?.remove();
      }
      addPageStyles(nextDocument);
      document.title = nextDocument.title;
      document.body.className = nextDocument.body.className;
      document.body.replaceChildren(...Array.from(nextDocument.body.childNodes, node => document.importNode(node, true)));
      if (updateHistory) history.pushState({}, "", url.href);
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });

      const scripts = Array.from(nextDocument.querySelectorAll('script[src]'), script => new URL(script.getAttribute("src"), location.origin).pathname);
      for (const src of scripts) await loadScript(src);
      document.dispatchEvent(new CustomEvent("nexus:page-ready", { detail: { path: url.pathname } }));
    } catch (error) {
      console.error("无刷新导航失败，改用整页加载", error);
      location.assign(url.href);
    } finally {
      navigating = false;
      document.documentElement.classList.remove("page-navigating");
    }
  }

  document.addEventListener("click", event => {
    const link = event.target.closest(".main-nav a[href]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin) return;
    event.preventDefault();
    navigate(url);
  });

  document.addEventListener("pointerenter", event => {
    const link = event.target.closest?.(".main-nav a[href]");
    if (link) warmPage(new URL(link.href, location.href));
  }, true);
  document.addEventListener("touchstart", event => {
    const link = event.target.closest?.(".main-nav a[href]");
    if (link) warmPage(new URL(link.href, location.href));
  }, { passive: true, capture: true });
  window.addEventListener("popstate", () => navigate(new URL(location.href), false));

  const schedule = window.requestIdleCallback || (callback => setTimeout(callback, 250));
  schedule(() => {
    for (const link of document.querySelectorAll(".main-nav a[href]")) {
      const url = new URL(link.href, location.href);
      if (url.pathname !== location.pathname) warmPage(url);
    }
  });
})();
