/* ==========================================================================
 *  sim/modules.js — сменные функциональные модули UniDev.
 *
 *  Конструктор UNI: платформа UniBase (моторы N20 150 RPM, энкодеры, дисплей,
 *  датчик батареи) + ОДИН функциональный модуль UniDev, который меняется
 *  магнитным соединением. К UniDev подключают датчики линии, ультразвук,
 *  сервоприводы, светодиодное кольцо — набор зависит от модуля.
 *
 *  Здесь описано, ЧТО именно даёт каждый модуль. Один источник правды:
 *    api.js    — какие вызовы UniDev работают (и что вернуть, если датчика нет);
 *    render.js — как модуль выглядит на роботе;
 *    sim.js    — какие датчики показывать в HUD.
 *
 *  Геометрия в мм в локальной системе робота: x — вперёд, y — вправо
 *  (совпадает с robot.localToWorld).
 * ========================================================================== */
(function (root) {
  "use strict";

  // Порты UniDev (как в UNI.h): P1..P8
  const P1 = 12, P2 = 13, P3 = 14, P4 = 15;

  // Значение датчика линии, когда датчика нет: «максимально светло»
  // (реальный АЦП 0..4095, тёмная линия ≈ 0). Скетч не примет это за линию.
  const NO_LINE = 4095;

  const MODULES = [
    {
      id: "none",
      name: "Без модуля",
      short: "платформа",
      desc: "Только платформа UniBase: моторы, энкодеры, дисплей, батарея.",
      line: [], ultra: [], servos: [], pixels: 0,
    },
    {
      id: "line2",
      name: "Датчики линии",
      short: "линия ×2",
      desc: "Два датчика линии (P1 слева, P2 справа) — движение по линии.",
      // расставлены по бокам от осевой: линия шириной ~30 мм проходит между ними
      line: [
        { port: P1, x: 74, y: -26, label: "Л" },
        { port: P2, x: 74, y: 26, label: "П" },
      ],
      ultra: [], servos: [], pixels: 0,
    },
    {
      id: "maze",
      name: "Модуль лабиринта",
      short: "лабиринт",
      desc: "Ультразвук вперёд (P1) и по бокам (P2 влево, P3 вправо) — проезд лабиринта.",
      line: [],
      ultra: [
        { port: P1, x: 75, y: 0, a: 0, label: "вперёд" },
        { port: P2, x: 0, y: -60, a: -Math.PI / 2, label: "влево" },
        { port: P3, x: 0, y: 60, a: Math.PI / 2, label: "вправо" },
      ],
      servos: [], pixels: 0,
    },
    {
      id: "ring",
      name: "Светодиодное кольцо",
      short: "кольцо",
      desc: "Кольцо из 12 адресных светодиодов (P1) — индикация и эффекты.",
      line: [], ultra: [], servos: [],
      pixels: 12, pixelPort: P1,
    },
    {
      id: "servo",
      name: "Сервопривод",
      short: "серво",
      desc: "Сервопривод на P1 (например, захват или поворотная башня).",
      line: [], ultra: [],
      servos: [{ port: P1, x: 70, y: 0, label: "серво" }],
      pixels: 0,
    },
  ];

  // Мнемосхемы (папка image/): вид сбоку, одинаковая ширина — складываются
  // в «этажи». Платформа всегда внизу, функциональные модули — над ней.
  const ART = { base: "/image/UniBase.png", dev: "/image/UniDev.png" };

  // Метки на схеме модуля: что именно на нём стоит (координаты в % картинки).
  const MARKS = {
    none:  [],
    line2: [{ x: 22, y: 74, kind: "line", label: "датчик линии" },
            { x: 78, y: 74, kind: "line", label: "датчик линии" }],
    maze:  [{ x: 50, y: 22, kind: "ultra", label: "ультразвук" },
            { x: 6, y: 30, kind: "ultra", label: "ультразвук" },
            { x: 94, y: 30, kind: "ultra", label: "ультразвук" }],
    ring:  [{ x: 50, y: 40, kind: "ring", label: "светодиодное кольцо" }],
    servo: [{ x: 26, y: 38, kind: "servo", label: "сервопривод" }],
  };

  const byId = (id) => MODULES.find((m) => m.id === id) || MODULES[0];
  const indexOf = (id) => Math.max(0, MODULES.findIndex((m) => m.id === id));
  const marksFor = (id) => MARKS[id] || [];

  /* Собрать конфигурацию из этажей: датчики всех установленных модулей
     работают одновременно. Порт физически один, поэтому при совпадении портов
     на разных этажах сообщаем о конфликте — как и на реальном роботе. */
  function combine(floorIds) {
    const line = [], ultra = [], servos = [], conflicts = [];
    let pixels = 0, pixelPort = null;
    const used = new Map();                       // порт → что уже занято
    const take = (port, what, floor) => {
      if (used.has(port)) conflicts.push({ port, a: used.get(port), b: what + " (этаж " + (floor + 2) + ")" });
      else used.set(port, what + " (этаж " + (floor + 2) + ")");   // этаж 1 — платформа
    };
    (floorIds || []).forEach((id, f) => {
      const m = byId(id);
      (m.line || []).forEach((s) => { take(s.port, "датчик линии", f); line.push(s); });
      (m.ultra || []).forEach((s) => { take(s.port, "ультразвук", f); ultra.push(s); });
      (m.servos || []).forEach((s) => { take(s.port, "сервопривод", f); servos.push(s); });
      if (m.pixels > 0) { take(m.pixelPort, "светодиодное кольцо", f); pixels += m.pixels; pixelPort = m.pixelPort; }
    });
    const names = (floorIds || []).map((id) => byId(id).name).filter((n) => n !== "Без модуля");
    return {
      id: "rig", name: names.length ? names.join(" + ") : "Без модуля",
      desc: names.length ? "Этажей: " + floorIds.length : "Только платформа UniBase.",
      line, ultra, servos, pixels, pixelPort, conflicts,
    };
  }

  // сдвиг по списку стрелками ◀ ▶ (по кругу)
  function step(id, dir) {
    const i = indexOf(id);
    return MODULES[(i + dir + MODULES.length) % MODULES.length].id;
  }

  // есть ли на этом порту датчик линии текущего модуля
  const lineAt = (mod, port) => (mod.line || []).find((s) => s.port === port) || null;
  const ultraAt = (mod, port) => (mod.ultra || []).find((s) => s.port === port) || null;

  root.SimModules = { MODULES, ART, byId, indexOf, step, marksFor, combine,
                      lineAt, ultraAt, NO_LINE, PORTS: { P1, P2, P3, P4 } };
})(typeof window !== "undefined" ? window : globalThis);
