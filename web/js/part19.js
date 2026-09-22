/* SUOT Neo — Часть 19: плагины (палитра+тулбар) и центр резервных копий. */

document.addEventListener("alpine:init", () => {
  Alpine.store("plugins", {
    list: [],
    raw: [],
    loaded: false,

    async load() {
      try {
        const [lst, raw] = await Promise.all([
          API.get("/plugins"), API.get("/plugins/raw")]);
        this.list = lst.items;
        this.raw = raw.items;
        this.loaded = true;
        window.__refreshPluginCommands();
      } catch (_) {}
    },

    byId(id) { return this.list.find((p) => p.id === id) || null; },
    isEnabled(id) {
      const p = this.byId(id);
      return p ? p.enabled : false;
    },

    async toggle(id) {
      const cur = this.isEnabled(id);
      try {
        await API.post(`/plugins/${id}/toggle`,
          { enabled: !cur });
        await this.load();
        Toast.show(I18N.t("tbl.savedOk"), "success");
        Sounds.play("click");
      } catch (e) { Toast.show(e.message, "error"); }
    },

    toolbarFor(key) {
      const out = [];
      for (const p of this.raw)
        for (const b of (p.toolbar || []))
          if (!b.table || b.table === "*" || b.table === key)
            out.push({ id: p.id + ":" + b.behavior,
                       tooltip: b.tooltip || p.name,
                       icon: b.icon || "layers",
                       behavior: b.behavior });
      return out;
    },

    commandList() {
      const out = [];
      for (const p of this.raw)
        for (const c of (p.commands || []))
          out.push({ id: "plug:" + p.id + ":" + c.behavior,
                     group: I18N.lang === "ru" ? "Плагины" : "Plugins",
                     label: c.title,
                     icon: window.ICONS.layers,
                     behavior: c.behavior });
      return out;
    },
  });
});

/* Команды плагинов для палитры */
window.PLUGIN_COMMANDS = [];

window.__refreshPluginCommands = function () {
  try {
    const st = Alpine.store("plugins");
    if (!st) return;
    window.PLUGIN_COMMANDS = st.commandList().map((c) => ({
      ...c,
      run: () => window.__pluginRun(c.behavior),
    }));
  } catch (_) {}
};

/* Выполнить поведение на активной таблице */
window.__pluginRun = function (behavior) {
  const panes = [...document.querySelectorAll(".tabpane")]
    .filter((p) => p.offsetParent !== null);
  for (const pane of panes) {
    const d = Alpine.$data(pane.firstElementChild || pane);
    if (d && typeof d.pluginAction === "function") {
      d.pluginAction(behavior);
      return;
    }
  }
  Toast.show(I18N.lang === "ru"
    ? "Откройте таблицу для этого действия"
    : "Open a table first", "error");
};

/* ── Центр резервных копий ── */

window.backupCenter = function () {
  return {
    open: false,
    items: [],
    settings: { enabled: true, keep: 5 },
    statsFor: null,          // предпросмотр выбранного архива
    restoreConfirm: null,    // имя файла
    busy: false,

    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    async openCenter() {
      this.open = true;
      await Promise.all([this.load(), this.loadSettings()]);
    },
    async load() {
      try {
        const r = await API.get("/backup/list");
        this.items = r.items;
      } catch (e) { /* не-админ */ }
    },
    async loadSettings() {
      try {
        this.settings = await API.get("/backup/settings");
      } catch (_) {}
    },
    async saveSettings() {
      try {
        await API.post("/backup/settings", this.settings);
        Toast.show(I18N.t("tbl.savedOk"), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async create() {
      this.busy = true;
      try {
        const r = await API.post("/backup/create");
        Toast.show(this.ru("Бэкап создан: ", "Backup created: ")
          + r.file, "success");
        Sounds.play("success");
        await this.load();
      } catch (e) {
        Toast.show(e.message, "error");
        Sounds.play("error");
      }
      this.busy = false;
    },
    async openFolder() {
      try {
        await API.post("/backup/open-folder");
        Toast.show(this.ru("Папка открыта в проводнике",
          "Folder opened"), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async preview(name) {
      try {
        this.statsFor = await API.get(
          "/backup/stats?name=" + encodeURIComponent(name));
      } catch (e) { Toast.show(e.message, "error"); }
    },
    askRestore(name) {
      this.restoreConfirm = name;
      this.statsFor = null;
    },
    async doRestore() {
      const name = this.restoreConfirm;
      this.restoreConfirm = null;
      this.busy = true;
      try {
        await API.post("/backup/restore?name=" +
          encodeURIComponent(name));
        Sounds.play("success");
        location.reload();
      } catch (e) {
        Toast.show(e.message, "error");
        Sounds.play("error");
        this.busy = false;
      }
    },
    async download(name) {
      // Скачивание идёт через fetch с токеном: plain <a href> без
      // Authorization получал бы 401.
      try {
        const res = await fetch("/api/backup/download?name=" +
          encodeURIComponent(name), { headers: API.authHeaders() });
        if (!res.ok) throw new Error("HTTP " + res.status);
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = name;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          URL.revokeObjectURL(a.href);
          a.remove();
        }, 4000);
      } catch (e) { Toast.show(e.message, "error"); }
    },
    fmtSize(n) {
      return n > 1048576 ? (n / 1048576).toFixed(1) + " МБ"
        : n > 1024 ? (n / 1024).toFixed(0) + " КБ" : n + " Б";
    },
  };
};
