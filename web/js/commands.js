/* SUOT Next — Command Bus (Блок 5).
   Единый реестр команд: id, RU/EN-подписи, иконка, группа, run().
   Правило: каждая команда ведёт на ПРОВЕРЕННЫЙ существующий обработчик
   (событие или метод) — фиктивных команд нет. Представления открываются
   через Navigation Registry (Alpine.store('next')), без дублирования.
   Клавиатура: существующие биндинги Hotkeys не дублируются; здесь только
   Alt+1..9 (в workspace.js) и оживление мёртвых F5/Ctrl+F. */
(function () {
  "use strict";

  function lang() {
    try { return (window.I18N && I18N.lang) || "ru"; }
    catch (_) { return "ru"; }
  }

  function fire(name, detail) {
    document.dispatchEvent(
      new CustomEvent(name, { bubbles: true, detail: detail || {} }));
  }

  function tabs() {
    try { return Alpine.store("tabs"); } catch (_) { return null; }
  }

  function next() {
    try { return Alpine.store("next"); } catch (_) { return null; }
  }

  /* hotkey: имя действия в window.Hotkeys (подсказка берётся живьём). */
  const COMMANDS = [
    { id: "palette", ru: "Командная палитра", en: "Command palette",
      icon: "command", group: "command", hotkey: "palette",
      run() { fire("suot-palette-open"); } },
    { id: "workspace", ru: "Рабочая область", en: "Workspace",
      icon: "layers", group: "command",
      run() { fire("suot-ws-toggle"); } },
    { id: "search", ru: "Поиск по программе", en: "Search everything",
      icon: "search", group: "command", hotkey: "search",
      run() { fire("suot-palette-open"); } },
    { id: "theme", ru: "Сменить тему", en: "Cycle theme",
      icon: "sun", group: "command", hotkey: "theme_toggle",
      run() {
        if (window.Hotkeys && typeof window.Hotkeys.run === "function") {
          window.Hotkeys.run("theme_toggle");
          return;
        }
        const root = document.querySelector("[x-data^=\"suotApp\"]");
        const data = root ? Alpine.$data(root) : null;
        if (data && typeof data.toggleTheme === "function") data.toggleTheme();
      } },
    { id: "help", ru: "Справка и горячие клавиши", en: "Help and shortcuts",
      icon: "star", group: "command", hotkey: "help",
      run() { fire("suot-hotkey-help"); } },
    { id: "settings", ru: "Настройки", en: "Settings",
      icon: "settings", group: "command",
      run() { fire("suot-open-settings"); } },
    { id: "tasks", ru: "Центр задач", en: "Task center",
      icon: "clock", group: "command",
      run() { fire("suot-tasks-open"); } },
    { id: "documents", ru: "Документы", en: "Documents",
      icon: "fileText", group: "command",
      run() { const n = next(); if (n) n.open("documents"); } },
    { id: "refresh-app", ru: "Перезагрузить приложение", en: "Reload app",
      icon: "refresh", group: "command", hotkey: "refresh",
      run() { location.reload(); } },
    { id: "logout", ru: "Выйти", en: "Log out",
      icon: "logout", group: "command",
      run() { fire("suot-logout"); } },
  ];

  const byId = {};
  COMMANDS.forEach((c) => { byId[c.id] = c; });

  function labelOf(cmd, L) {
    if (!cmd) return "";
    const langNow = L || lang();
    return langNow === "en" ? (cmd.en || cmd.ru) : (cmd.ru || cmd.en);
  }

  function shortcutFor(cmd) {
    try {
      if (cmd && cmd.hotkey && window.Hotkeys && window.Hotkeys.bindings) {
        return window.Hotkeys.bindings[cmd.hotkey] || "";
      }
    } catch (_) {}
    return "";
  }

  const bus = {
    all() { return COMMANDS.slice(); },
    get(id) { return byId[id] || null; },
    labelOf, shortcutFor, lang,
    search(q) {
      const needle = String(q || "").trim().toLowerCase();
      if (!needle) return this.all();
      return COMMANDS.filter((c) => (
        (c.ru || "") + " " + (c.en || "") + " " + c.id + " " +
        (c.group || "")
      ).toLowerCase().includes(needle));
    },
    run(id) {
      const cmd = typeof id === "string" ? this.get(id) : id;
      if (!cmd || typeof cmd.run !== "function") return false;
      try { cmd.run(); return true; }
      catch (_) { return false; }
    },
    /* Открытие вида — через реестр (single source of truth). */
    openView(id, context) {
      const nx = next();
      if (!nx || typeof nx.open !== "function") return false;
      try { return !!nx.open(id, context); }
      catch (_) { return false; }
    },
    /* Строгое открытие: false если нет точного совпадения (для палитры). */
    openViewExact(idOrKey, context) {
      const nx = next();
      if (!nx || typeof nx.openViewExact !== "function") return false;
      try { return !!nx.openViewExact(idOrKey, context); }
      catch (_) { return false; }
    },
    tabs,
  };

  window.SUOT_COMMANDS = bus;

  /* Оживляем мёртвые хоткеи: F5 (перезагрузка) и Ctrl+F (поиск).
     Ctrl+N (new-record) и Ctrl+E (export-table) слушателей не имеют —
     осознанно не трогаем (см. трекер), чтобы не вешать поведение наобум. */
  document.addEventListener("suot-hotkey-refresh", () => {
    try { location.reload(); } catch (_) {}
  });
  document.addEventListener("suot-hotkey-search", () => {
    fire("suot-palette-open");
  });
})();
