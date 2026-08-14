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

  const byId = (id) => MODULES.find((m) => m.id === id) || MODULES[0];
  const indexOf = (id) => Math.max(0, MODULES.findIndex((m) => m.id === id));

  // сдвиг по списку стрелками ◀ ▶ (по кругу)
  function step(id, dir) {
    const i = indexOf(id);
    return MODULES[(i + dir + MODULES.length) % MODULES.length].id;
  }

  // есть ли на этом порту датчик линии текущего модуля
  const lineAt = (mod, port) => (mod.line || []).find((s) => s.port === port) || null;
  const ultraAt = (mod, port) => (mod.ultra || []).find((s) => s.port === port) || null;

  root.SimModules = { MODULES, byId, indexOf, step, lineAt, ultraAt, NO_LINE, PORTS: { P1, P2, P3, P4 } };
})(typeof window !== "undefined" ? window : globalThis);
