/* ==========================================================================
 *  sim/render.js — отрисовка арены и робота (Canvas2D).
 *  Мир в мм (y вниз) → экран с авто-вписыванием и отступами.
 * ========================================================================== */
(function (root) {
  "use strict";
  const R = root.SimRobot;

  function view(canvas, world) {
    const pad = 16;
    const sx = (canvas.width - pad * 2) / world.w;
    const sy = (canvas.height - pad * 2) / world.h;
    const s = Math.min(sx, sy);
    const ox = (canvas.width - world.w * s) / 2;
    const oy = (canvas.height - world.h * s) / 2;
    return { s, ox, oy, X: (x) => ox + x * s, Y: (y) => oy + y * s };
  }

  function draw(ctx, canvas, world, robot, opts) {
    opts = opts || {};
    const v = view(canvas, world);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // фон вне арены
    ctx.fillStyle = "#0f1620"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    // пол арены
    ctx.fillStyle = "#f3efe6";
    ctx.fillRect(v.X(0), v.Y(0), world.w * v.s, world.h * v.s);

    // сетка 200 мм
    ctx.strokeStyle = "rgba(0,0,0,0.06)"; ctx.lineWidth = 1;
    for (let gx = 0; gx <= world.w; gx += 200) { ctx.beginPath(); ctx.moveTo(v.X(gx), v.Y(0)); ctx.lineTo(v.X(gx), v.Y(world.h)); ctx.stroke(); }
    for (let gy = 0; gy <= world.h; gy += 200) { ctx.beginPath(); ctx.moveTo(v.X(0), v.Y(gy)); ctx.lineTo(v.X(world.w), v.Y(gy)); ctx.stroke(); }

    // линия на полу
    if (world.line) {
      ctx.strokeStyle = "#1a1a1a"; ctx.lineWidth = (world.line.width || 30) * v.s;
      ctx.lineJoin = "round"; ctx.lineCap = "round";
      ctx.beginPath();
      world.line.pts.forEach((p, i) => i ? ctx.lineTo(v.X(p.x), v.Y(p.y)) : ctx.moveTo(v.X(p.x), v.Y(p.y)));
      if (world.line.closed) ctx.closePath();
      ctx.stroke();
    }

    // препятствия
    ctx.fillStyle = "#9aa4ad"; ctx.strokeStyle = "#5b6671"; ctx.lineWidth = 1.5;
    for (const o of world.obstacles) {
      ctx.beginPath();
      if (o.type === "rect") ctx.rect(v.X(o.x), v.Y(o.y), o.w * v.s, o.h * v.s);
      else if (o.type === "circle") ctx.arc(v.X(o.x), v.Y(o.y), o.r * v.s, 0, 7);
      ctx.fill(); ctx.stroke();
    }

    // рамка арены
    ctx.strokeStyle = "#3a4650"; ctx.lineWidth = 2;
    ctx.strokeRect(v.X(0), v.Y(0), world.w * v.s, world.h * v.s);

    // лучи датчиков (если переданы)
    if (opts.rays) for (const r of opts.rays) {
      ctx.strokeStyle = "rgba(0,135,138,0.5)"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(v.X(r.x0), v.Y(r.y0)); ctx.lineTo(v.X(r.x1), v.Y(r.y1)); ctx.stroke();
      ctx.fillStyle = "#00878a"; ctx.beginPath(); ctx.arc(v.X(r.x1), v.Y(r.y1), 3, 0, 7); ctx.fill();
    }

    drawRobot(ctx, v, robot, opts);

    // точки датчиков линии (тёмно-красная = над линией, белая = над полом)
    if (opts.lineDots) for (const d of opts.lineDots) {
      ctx.beginPath(); ctx.arc(v.X(d.x), v.Y(d.y), 4.5, 0, 7);
      ctx.fillStyle = d.on ? "#c0392b" : "#ffffff"; ctx.fill();
      ctx.strokeStyle = "#222"; ctx.lineWidth = 1; ctx.stroke();
    }

    // след (трасса центра)
    if (opts.trail && opts.trail.length > 1) {
      ctx.strokeStyle = "rgba(0,135,138,0.45)"; ctx.lineWidth = 1.5;
      ctx.beginPath(); opts.trail.forEach((p, i) => i ? ctx.lineTo(v.X(p.x), v.Y(p.y)) : ctx.moveTo(v.X(p.x), v.Y(p.y))); ctx.stroke();
    }
  }

  function drawRobot(ctx, v, robot, opts) {
    const X = v.X, Y = v.Y, s = v.s;
    ctx.save();
    ctx.translate(X(robot.x), Y(robot.y));
    ctx.rotate(robot.th);                 // локальная: +x вперёд, +y вправо
    const mm = (px) => px * s;
    // колёса
    ctx.fillStyle = "#222";
    rr(ctx, mm(-22), mm(R.TRACK_MM / 2 - 9), mm(44), mm(18), mm(4));      // правое
    rr(ctx, mm(-22), mm(-R.TRACK_MM / 2 - 9), mm(44), mm(18), mm(4));     // левое
    // опоры (ролики)
    ctx.fillStyle = "#888";
    dot(ctx, mm(62), 0, mm(7)); dot(ctx, mm(-62), 0, mm(7));
    // корпус
    ctx.fillStyle = robot.collided ? "#c0392b" : "#00878a";
    ctx.strokeStyle = "#00585a"; ctx.lineWidth = 1.5;
    rr(ctx, mm(-72), mm(-60), mm(150), mm(120), mm(14), true);
    // нос (направление)
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.moveTo(mm(78), 0); ctx.lineTo(mm(50), mm(-22)); ctx.lineTo(mm(50), mm(22)); ctx.closePath(); ctx.fill();
    drawModule(ctx, mm, opts || {});
    ctx.restore();
  }

  /* Установленный модуль UniDev — рисуем прямо на платформе, чтобы было видно,
     что «примагничено»: площадка модуля + его начинка (кольцо, серво, УЗ-глаза). */
  function drawModule(ctx, mm, opts) {
    const mod = opts.module;
    if (!mod || mod.id === "none") return;

    // площадка модуля на «спине» платформы
    ctx.fillStyle = "#2b6ea8"; ctx.strokeStyle = "#1d4f78"; ctx.lineWidth = 1.2;
    rr(ctx, mm(-34), mm(-34), mm(68), mm(68), mm(6), true);
    // магнитные контакты
    ctx.fillStyle = "#d8dee3";
    dot(ctx, mm(-24), mm(-24), mm(3.5)); dot(ctx, mm(-24), mm(24), mm(3.5));
    dot(ctx, mm(24), mm(-24), mm(3.5)); dot(ctx, mm(24), mm(24), mm(3.5));

    if (mod.pixels > 0) drawRing(ctx, mm, mod, opts);
    if ((mod.servos || []).length) drawServo(ctx, mm, mod, opts);
    if ((mod.ultra || []).length) drawUltra(ctx, mm, mod);
    if ((mod.line || []).length) drawLineHeads(ctx, mm, mod);
  }

  function drawRing(ctx, mm, mod, opts) {
    const n = mod.pixels, Rr = 26, t = (opts.clock || 0) / 1000;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      const px = Math.cos(a) * Rr, py = Math.sin(a) * Rr;
      ctx.fillStyle = pixelColor(i, n, opts, t);
      dot(ctx, mm(px), mm(py), mm(4.5));
      ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.lineWidth = 0.8; ctx.stroke();
    }
  }

  // цвет светодиода: явно заданный, эффект или «погашен»
  function pixelColor(i, n, opts, t) {
    const fx = opts.pixelFx;
    if (fx) {
      const rgb = [fx.r, fx.g, fx.b];
      if (fx.name === "rainbow") return "hsl(" + Math.round(((i / n) * 360 + t * 120) % 360) + ",85%,55%)";
      if (fx.name === "running" || fx.name === "rotating" || fx.name === "spinner")
        return (i === Math.floor(t * 6) % n) ? rgbCss(rgb) : "#20303f";
      if (fx.name === "breathing") {
        const k = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 3));
        return rgbCss(rgb.map((c) => Math.round(c * k)));
      }
      if (fx.name === "sparkle")
        return ((i * 7 + Math.floor(t * 8)) % 5 === 0) ? rgbCss(rgb) : "#20303f";
      return rgbCss(rgb);
    }
    const p = opts.pixels && opts.pixels[i];
    return p ? rgbCss(p) : "#20303f";
  }
  const rgbCss = (c) => "rgb(" + (c[0] | 0) + "," + (c[1] | 0) + "," + (c[2] | 0) + ")";

  function drawServo(ctx, mm, mod, opts) {
    const s = mod.servos[0];
    ctx.fillStyle = "#37474f";
    rr(ctx, mm(s.x - 12), mm(s.y - 10), mm(24), mm(20), mm(3));
    // качалка поворачивается на заданный угол (0..180 → -90..+90 от оси)
    const ang = ((opts.servoAngle == null ? 90 : opts.servoAngle) - 90) * Math.PI / 180;
    ctx.save();
    ctx.translate(mm(s.x), mm(s.y)); ctx.rotate(ang);
    ctx.fillStyle = "#ffd35c";
    rr(ctx, 0, mm(-2.5), mm(26), mm(5), mm(2));
    ctx.restore();
    ctx.fillStyle = "#90a4ae"; dot(ctx, mm(s.x), mm(s.y), mm(3));
  }

  function drawUltra(ctx, mm, mod) {
    for (const u of mod.ultra) {
      ctx.save();
      ctx.translate(mm(u.x), mm(u.y)); ctx.rotate(u.a || 0);
      ctx.fillStyle = "#2b6ea8"; ctx.strokeStyle = "#1d4f78"; ctx.lineWidth = 1;
      rr(ctx, mm(-4), mm(-16), mm(9), mm(32), mm(2), true);
      ctx.fillStyle = "#cfd8dc";                    // «глаза» датчика
      dot(ctx, mm(0.5), mm(-8), mm(5)); dot(ctx, mm(0.5), mm(8), mm(5));
      ctx.restore();
    }
  }

  function drawLineHeads(ctx, mm, mod) {
    for (const s of mod.line) {                     // корпуса датчиков линии под носом
      ctx.fillStyle = "#37474f";
      rr(ctx, mm(s.x - 7), mm(s.y - 6), mm(14), mm(12), mm(2));
    }
  }

  function rr(ctx, x, y, w, h, r, stroke) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath(); ctx.fill(); if (stroke) ctx.stroke();
  }
  function dot(ctx, x, y, r) { ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); }

  root.SimRender = { draw, view };
})(typeof window !== "undefined" ? window : globalThis);
