/* ==========================================================================
 *  sim/sim.js — драйвер симулятора.
 *
 *  Связывает интерпретатор (cpp/interp) с моделью (robot/world) и рендером.
 *  Главное: маппинг ВИРТУАЛЬНОГО времени скетча на РЕАЛЬНЫЕ кадры rAF —
 *  за кадр «съедаем» dtReal*speed виртуальных мс, прокручивая физику фикс-
 *  шагом; delay()/движения растягиваются на несколько кадров (плавно).
 * ========================================================================== */
(function (root) {
  "use strict";
  const { SimCpp, SimRobot, SimWorld, SimRender, SimApi, SimModules } = root;

  const PHYS_DT = 5;        // мс на под-шаг физики
  const ROBOT_R = 80;       // радиус робота для столкновений, мм
  const MAX_FRAME_MS = 120; // ограничение скачка времени за кадр
  const WORK_CAP = 30000;   // защита от зависания: операций интерпретатора за кадр
  // Сколько виртуального времени «стоит» один проход loop(). Без этого скетч с
  // непрерывным loop() (типичный линиислед: читаем датчики → крутим моторы, без
  // delay()) никогда не делает yield — время не идёт и робот стоит на месте.
  // На реальной плате проход loop() тоже занимает время; берём ~1 мс.
  const LOOP_MS = 1;

  function Sim(canvas) {
    this.canvas = canvas; this.ctx = canvas.getContext("2d");
    this.speed = 1; this.running = false;
    this.world = SimWorld.scenario("arena");
    this.robot = new SimRobot();
    this.machine = null; this.gen = null; this.phase = "idle"; this.pending = null;
    this.clock = 0; this.trail = []; this.rays = []; this.displayText = "";
    this.err = null;
    this.onSerial = null; this.onState = null;
    this._raf = null; this._last = 0; this._loops = 0;
    // Конструктор: платформа UniBase внизу + «этажи» функциональных модулей
    // UniDev над ней (магнитное соединение). floors[0] — второй этаж.
    this.floors = ["line2"];
    this._resetRobot();
  }

  // --- этажи конструктора (смена «на лету», как перестановка магнитного модуля) ---
  Sim.prototype.setFloor = function (i, id) {
    if (i < 0 || i >= this.floors.length) return;
    this.floors[i] = SimModules.byId(id).id;
    this.reset();                      // датчики сменились — начинаем с чистого листа
  };
  Sim.prototype.stepFloor = function (i, dir) {
    if (i < 0 || i >= this.floors.length) return;
    this.setFloor(i, SimModules.step(this.floors[i], dir));
  };
  Sim.prototype.addFloor = function (id) {
    this.floors.push(SimModules.byId(id || "none").id);
    this.reset();
  };
  Sim.prototype.removeFloor = function (i) {
    if (this.floors.length <= 1 || i < 0 || i >= this.floors.length) return;
    this.floors.splice(i, 1);
    this.reset();
  };
  Sim.prototype.setFloors = function (ids) {
    this.floors = (ids && ids.length ? ids : ["none"]).map((id) => SimModules.byId(id).id);
    this.reset();
  };
  // объединённая конфигурация всех этажей — её и «видит» скетч
  Sim.prototype.getModule = function () { return SimModules.combine(this.floors); };

  // совместимость с одноэтажным API
  Sim.prototype.setModule = function (id) { this.setFloors([id]); };
  Sim.prototype.stepModule = function (dir) { this.stepFloor(0, dir); };

  Sim.prototype.setScenario = function (name) {
    this.running = false; cancelAnimationFrame(this._raf);
    this.phase = "idle"; this.gen = null; this.pending = null;
    this.world = SimWorld.scenario(name);
    this._resetRobot(); this.render(); this._emit();
  };

  Sim.prototype._resetRobot = function () {
    const s = this.world.start;
    this.robot.reset(s.x, s.y, s.th);
    this.clock = 0; this.trail = [{ x: this.robot.x, y: this.robot.y }];
    this.rays = []; this.displayText = ""; this.err = null;
    this.battery = 100;                       // % заряда (садится от работы моторов)
    this.pixels = new Array(24).fill(null);   // состояние светодиодного кольца
    this.pixelFx = null;                      // текущий эффект кольца
    this.servoAngle = null;                   // угол сервопривода, град
  };

  // загрузка скетча: парсинг + сборка машины
  Sim.prototype.load = function (source) {
    const self = this;
    const ctx = {
      clock: () => self.clock,
      serial: (t) => { if (self.onSerial) self.onSerial(t); },
      display: (t) => { self.displayText = t; },
      // платформа UniBase
      battery: () => Math.round(self.battery),
      // сменный модуль UniDev: датчики берутся из его описания
      module: () => self.getModule(),
      pixel: (i, r, g, b) => {
        const n = self.getModule().pixels || 0;
        if (i >= 0 && i < n) { self.pixels[i] = [r | 0, g | 0, b | 0]; self.pixelFx = null; }
      },
      pixelsAll: (r, g, b) => {
        const n = self.getModule().pixels || 0;
        const off = !r && !g && !b;
        for (let i = 0; i < n; i++) self.pixels[i] = off ? null : [r | 0, g | 0, b | 0];
        self.pixelFx = null;
      },
      pixelsEffect: (name, r, g, b) => { self.pixelFx = { name, r: r | 0, g: g | 0, b: b | 0 }; },
      servo: (port, ang) => { self.servoAngle = Math.max(0, Math.min(180, ang | 0)); },
    };
    const ast = SimCpp.parse(source);                 // бросает CppError при ошибке
    const host = SimApi.build(this.robot, this.world, ctx);
    this.machine = SimCpp.createMachine(ast, { classes: host.classes, env: host.env });
    return true;
  };

  Sim.prototype.run = function () {
    if (!this.machine) return;
    this._resetRobot();
    this.gen = this.machine.runSetup(); this.phase = "setup"; this.pending = null;
    this.running = true; this._last = performance.now();
    this._emit();
    const tick = (now) => {
      if (!this.running) return;
      this._frame(now);
      this._raf = requestAnimationFrame(tick);
    };
    cancelAnimationFrame(this._raf);
    this._raf = requestAnimationFrame(tick);
  };

  Sim.prototype.stop = function () {
    this.running = false; cancelAnimationFrame(this._raf);
    this.robot.stop(); this.render(); this._emit();
  };

  Sim.prototype.reset = function () {
    this.running = false; cancelAnimationFrame(this._raf);
    this.phase = "idle"; this.gen = null; this.pending = null;
    this._resetRobot(); this.render(); this._emit();
  };

  // ---- один кадр: «съесть» dtReal*speed виртуальных мс ----
  Sim.prototype._frame = function (now) {
    let dtReal = now - this._last; this._last = now;
    if (dtReal > MAX_FRAME_MS) dtReal = MAX_FRAME_MS;
    let budget = dtReal * this.speed;
    let work = 0;

    while (budget > 0 && this.running && this.phase !== "done") {
      if (++work > WORK_CAP) break;                    // защита от зависания за кадр

      if (this.pending && this.pending.sleep != null) {
        const take = Math.min(budget, this.pending.sleep);
        this._advance(take); this.pending.sleep -= take; budget -= take;
        if (this.pending.sleep <= 1e-6) this.pending = null;
        continue;
      }
      if (this.pending && this.pending.wait) {
        const step = Math.min(PHYS_DT, budget);
        this._advance(step); budget -= step; this.pending.elapsed += step;
        const done = this.pending.fn();
        const timedOut = this.pending.maxMs > 0 && this.pending.elapsed >= this.pending.maxMs;
        if (done || timedOut) this.pending = null;
        continue;
      }
      // нет ожидания — крутим интерпретатор
      let r;
      try { r = this.gen.next(); }
      catch (e) { this._fail(e); return; }
      if (r.done) {
        const wasLoop = this.phase === "loop";
        if (!this._nextPhase()) break;
        // проход loop() съедает квант времени: физика движется даже без delay()
        if (wasLoop) { this._advance(LOOP_MS); budget -= LOOP_MS; }
        continue;
      }
      const q = r.value || {};
      if (q.sleep != null) this.pending = { sleep: Math.max(0, q.sleep) };
      else if (typeof q.wait === "function") this.pending = { wait: true, fn: q.wait, maxMs: q.maxMs || 0, elapsed: 0 };
      // {breathe} — просто продолжаем (учитывается work-бюджетом)
    }
    this.render(); this._emit();
  };

  // переход setup → loop → loop → … ; false = всё закончилось
  Sim.prototype._nextPhase = function () {
    if (this.phase === "setup") {
      if (this.machine.hasLoop()) { this.phase = "loop"; this.gen = this.machine.runLoop(); return true; }
      this.phase = "done"; this.running = false; return false;
    }
    if (this.phase === "loop") {
      if (++this._loops > 200000) { this.phase = "done"; this.running = false; return false; }
      this.gen = this.machine.runLoop(); return true;
    }
    return false;
  };

  // прокрутить физику на ms виртуальных мс (под-шагами), со столкновениями
  Sim.prototype._advance = function (ms) {
    let left = ms;
    while (left > 1e-6) {
      const dt = Math.min(PHYS_DT, left);
      const px = this.robot.x, py = this.robot.y;
      this.robot.step(dt / 1000);
      this.clock += dt; left -= dt;
      // Расход батареи: ток покоя + нагрузка моторов (для getBatteryPower()).
      // Подобрано под ~1.5 часа непрерывной езды, как у реальной платформы.
      const load = (Math.abs(this.robot.vL) + Math.abs(this.robot.vR)) / (2 * SimRobot.MAX_SPEED);
      this.battery = Math.max(0, this.battery - (0.002 + 0.018 * load) * (dt / 1000));
      if (this.world.hitsAt(this.robot.x, this.robot.y, ROBOT_R)) {
        this.robot.x = px; this.robot.y = py;     // не въезжаем в стену
        this.robot.stop(); this.robot.task = null; this.robot.collided = true;
      }
      const tl = this.trail, last = tl[tl.length - 1];
      if (!last || Math.hypot(this.robot.x - last.x, this.robot.y - last.y) > 8) {
        tl.push({ x: this.robot.x, y: this.robot.y });
        if (tl.length > 4000) tl.shift();
      }
    }
  };

  Sim.prototype._fail = function (e) {
    this.running = false; cancelAnimationFrame(this._raf);
    this.err = e.message || String(e);
    if (this.onSerial) this.onSerial("⛔ " + this.err + "\n");
    this.render(); this._emit();
  };

  Sim.prototype.resize = function () {
    const r = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, Math.round(r.width * dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * dpr));
    this.render();
  };

  Sim.prototype.render = function () {
    const r = this.robot, w = this.world, mod = this.getModule();
    // Показываем ровно те датчики, которые несёт установленный модуль.
    const rays = (mod.ultra || []).map((s) => {
      const p = r.localToWorld(s.x, s.y), a = r.th + (s.a || 0);
      const d = w.rayDistance(p.x, p.y, a, 2000) || 2000;
      return { x0: p.x, y0: p.y, x1: p.x + d * Math.cos(a), y1: p.y + d * Math.sin(a), label: s.label };
    });
    const lineDots = (mod.line || []).map((s) => {
      const p = r.localToWorld(s.x, s.y);
      return { x: p.x, y: p.y, on: w.floorAt(p.x, p.y) < 1500, label: s.label };
    });
    this._sensors = {
      ultra: (mod.ultra || []).map((s, i) => {
        const p = r.localToWorld(s.x, s.y);
        return { label: s.label, mm: w.rayDistance(p.x, p.y, r.th + (s.a || 0), 2000) };
      }),
      line: lineDots.map((d) => ({ label: d.label, on: d.on })),
    };
    SimRender.draw(this.ctx, this.canvas, this.world, this.robot, {
      rays, lineDots, trail: this.trail,
      module: mod, pixels: this.pixels, pixelFx: this.pixelFx,
      servoAngle: this.servoAngle, clock: this.clock,
    });
    this._hud();
  };

  Sim.prototype._hud = function () {
    const ctx = this.ctx;
    ctx.font = "12px monospace"; ctx.textBaseline = "top";
    const lines = [
      "t=" + (this.clock / 1000).toFixed(2) + "с  " + (this.running ? "▶" : "❚❚") + "  x" + this.speed,
      "x=" + this.robot.x.toFixed(0) + " y=" + this.robot.y.toFixed(0) + " θ=" + this.robot.headingDeg().toFixed(0) + "°",
    ];
    lines.push("модуль: " + this.getModule().name);
    const s = this._sensors;
    if (s) {
      if (s.line.length) lines.push("линия  " + s.line.map((d) => d.label + (d.on ? "▮" : "▯")).join("  "));
      if (s.ultra.length) lines.push("ультразвук  " + s.ultra.map((u) => u.label + " " + (u.mm || 0)).join("  ") + " мм");
    }
    if (this.servoAngle != null) lines.push("серво: " + this.servoAngle + "°");
    lines.push("батарея: " + Math.round(this.battery) + "%");
    if (this.displayText) lines.push("экран: " + this.displayText);
    if (this.robot.collided) lines.push("столкновение!");
    ctx.fillStyle = "rgba(15,22,32,0.80)";
    ctx.fillRect(8, 8, 260, 16 * lines.length + 8);
    ctx.fillStyle = "#cfe8e8";
    lines.forEach((str, i) => ctx.fillText(str, 14, 13 + i * 16));
  };

  Sim.prototype._emit = function () { if (this.onState) this.onState(this.getState()); };
  Sim.prototype.getState = function () {
    const m = this.getModule();
    return { running: this.running, phase: this.phase, clock: this.clock, speed: this.speed,
      scenario: this.world.name, collided: this.robot.collided, err: this.err,
      floors: this.floors.slice(), moduleName: m.name, moduleDesc: m.desc,
      conflicts: m.conflicts || [], battery: Math.round(this.battery) };
  };

  root.Sim = Sim;
})(typeof window !== "undefined" ? window : globalThis);
