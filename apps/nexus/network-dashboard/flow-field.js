(() => {
  "use strict";

  const canvas = document.getElementById("flow-canvas");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const previousCleanup = window.nexusPageCleanup;
  let width = 0;
  let height = 0;
  let particles = [];
  let frame = 0;
  let lastTime = 0;
  let active = true;
  let activity = 0.18;
  let targetActivity = 0.18;
  let downActivity = 0.5;
  let observer;
  const downTotalElement = document.getElementById("gateway-down-total");
  const upTotalElement = document.getElementById("gateway-up-total");
  let downRate = 0;
  let upRate = 0;
  let downTotal = 0;
  let upTotal = 0;
  let sampleTime = 0;
  let lastCounterPaint = 0;
  let hasTotals = false;

  function createParticle(direction, initial = true) {
    const start = 62;
    const end = Math.max(start + 1, width - 62);
    return {
      direction,
      x: initial ? start + Math.random() * (end - start) : direction === 1 ? start : end,
      y: height * (direction === 1 ? 0.60 : 0.82) + (Math.random() - 0.5) * Math.min(28, height * 0.25),
      speed: 34 + Math.random() * 72,
      size: 0.7 + Math.random() * 1.25,
      alpha: 0.25 + Math.random() * 0.65,
      phase: Math.random() * Math.PI * 2,
    };
  }

  function seedParticles() {
    const count = width < 520 ? 34 : 58;
    particles = Array.from({ length: count }, (_, index) => createParticle(index % 3 === 2 ? -1 : 1));
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    seedParticles();
  }

  function drawLane(direction) {
    const start = 62;
    const end = Math.max(start + 1, width - 62);
    const lane = direction === 1 ? 0.60 : 0.82;
    const gradient = context.createLinearGradient(start, 0, end, 0);
    gradient.addColorStop(0, "rgba(98,245,255,0)");
    gradient.addColorStop(0.18, direction === 1 ? "rgba(98,245,255,.16)" : "rgba(167,139,255,.10)");
    gradient.addColorStop(0.82, direction === 1 ? "rgba(98,245,255,.10)" : "rgba(167,139,255,.16)");
    gradient.addColorStop(1, "rgba(167,139,255,0)");
    context.beginPath();
    for (let x = start; x <= end; x += 8) {
      const y = height * lane + Math.sin(x * 0.025 + direction) * 4;
      if (x === start) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
    context.strokeStyle = gradient;
    context.lineWidth = 0.8;
    context.stroke();
  }

  function paint(now = 0) {
    if (!active) return;
    const elapsed = lastTime ? Math.min(0.04, (now - lastTime) / 1000) : 0.016;
    lastTime = now;
    activity += (targetActivity - activity) * 0.08;
    context.clearRect(0, 0, width, height);
    context.globalCompositeOperation = "lighter";
    drawLane(1);
    drawLane(-1);

    const start = 62;
    const end = Math.max(start + 1, width - 62);
    for (const particle of particles) {
      const directionActivity = particle.direction === 1 ? 0.55 + downActivity * 0.65 : 0.55 + (1 - downActivity) * 0.65;
      particle.x += particle.direction * particle.speed * (0.55 + activity * 2.1) * directionActivity * elapsed;
      if ((particle.direction === 1 && particle.x > end) || (particle.direction === -1 && particle.x < start)) {
        Object.assign(particle, createParticle(particle.direction, false));
      }
      const progress = Math.max(0, Math.min(1, (particle.x - start) / (end - start)));
      const edgeFade = Math.min(1, progress * 8, (1 - progress) * 8);
      const y = particle.y + Math.sin(now * 0.0015 + particle.phase) * 2.2;
      const alpha = particle.alpha * edgeFade * (0.65 + activity * 0.35);
      const color = particle.direction === 1 ? "98,245,255" : "167,139,255";
      const tail = 5 + particle.speed * 0.11 * (0.7 + activity);
      context.beginPath();
      context.moveTo(particle.x - particle.direction * tail, y);
      context.lineTo(particle.x, y);
      context.strokeStyle = `rgba(${color},${alpha * 0.48})`;
      context.lineWidth = particle.size;
      context.stroke();
      context.beginPath();
      context.arc(particle.x, y, particle.size, 0, Math.PI * 2);
      context.fillStyle = `rgba(${color},${alpha})`;
      context.shadowColor = `rgba(${color},.8)`;
      context.shadowBlur = 7;
      context.fill();
    }
    context.shadowBlur = 0;
    context.globalCompositeOperation = "source-over";
    paintCounters(now);
    if (!reducedMotion.matches) frame = requestAnimationFrame(paint);
  }

  function formatKb(bytes) {
    const kilobytes = Math.max(0, Number(bytes) || 0) / 1024;
    const decimals = kilobytes < 1000 ? 2 : 0;
    return kilobytes.toLocaleString("en-US", {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
  }

  function paintCounters(now) {
    if (!hasTotals || now - lastCounterPaint < 80) return;
    lastCounterPaint = now;
    const elapsed = Math.max(0, (now - sampleTime) / 1000);
    downTotalElement.textContent = formatKb(downTotal + downRate * elapsed);
    upTotalElement.textContent = formatKb(upTotal + upRate * elapsed);
  }

  function update(down, up, totalDownBytes, totalUpBytes) {
    downRate = Math.max(0, Number(down) || 0);
    upRate = Math.max(0, Number(up) || 0);
    downTotal = Math.max(0, Number(totalDownBytes) || 0);
    upTotal = Math.max(0, Number(totalUpBytes) || 0);
    sampleTime = performance.now();
    lastCounterPaint = 0;
    hasTotals = true;
    const megabits = (downRate + upRate) * 8 / 1e6;
    targetActivity = Math.min(1, 0.12 + Math.log10(1 + megabits) / 3);
    downActivity = downRate + upRate > 0 ? downRate / (downRate + upRate) : 0.5;
    if (reducedMotion.matches) paint(sampleTime);
  }

  window.nexusFlowUpdate = update;
  resize();
  if (window.ResizeObserver) {
    observer = new ResizeObserver(resize);
    observer.observe(canvas);
  } else {
    window.addEventListener("resize", resize);
  }
  frame = requestAnimationFrame(paint);

  window.nexusPageCleanup = () => {
    if (typeof previousCleanup === "function") previousCleanup();
    active = false;
    cancelAnimationFrame(frame);
    observer?.disconnect();
    window.removeEventListener("resize", resize);
    if (window.nexusFlowUpdate === update) delete window.nexusFlowUpdate;
  };
})();
