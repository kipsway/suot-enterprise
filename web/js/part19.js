/* SUOT Neo — Часть 19: плагины (палитра+тулбар) и центр резервных копий. */

/* SUOT Neo — Часть 19: плагины (палитра+тулбар) и центр резервных копий.
   Блок 8 (Capability v2): гейты по capabilities, per-user настройки,
   гранты на write-возможности. Зеркало BEHAVIOR_CAPS — server/routers/plugins_api.py. */

window.PLUGIN_BEHAVIOR_CAPS = {
  copy_tsv: ["table.read", "clipboard"],
  overdue_label: ["table.write"],
};

document.addEventListener("alpine:init", () => {
  Alpine.store("plugins", {
    list: [],
    raw: [],
    loaded: false,
    settingsCache: {},
    editingPid: "",
    editValues: {},
    editBusy: false,
    /* Write-набор: требует гранта администратора (зеркало backend). */
    writeCaps: ["table.write"],

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
    rawById(id) { return this.raw.find((p) => p.id === id) || null; },
    isEnabled(id) {
      const p = this.byId(id);
      return p ? p.enabled : false;
    },
    /* Эффективные капы включённого плагина (с сервера). */
    capsOf(pid) {
      const p = this.rawById(pid);
      return (p && p.granted_capabilities) || [];
    },
    needsGrant(pid) {
      const p = this.byId(pid);
      return !!(p && p.needs_grant);
    },
    /* Поведение разрешено, если плагин включён и все нужные капы выданы. */
    canRun(behavior) {
      const need = window.PLUGIN_BEHAVIOR_CAPS[behavior];
      if (!need) return false;
      for (const p of this.raw) {
        const has = [...(p.commands || []), ...(p.toolbar || [])]
          .some((x) => x && x.behavior === behavior);
        if (!has) continue;
        const caps = p.granted_capabilities || [];
        if (need.every((c) => caps.includes(c))) return true;
      }
      return false;
    },
    ownerOf(behavior) {
      for (const p of this.raw) {
        const has = [...(p.commands || []), ...(p.toolbar || [])]
          .some((x) => x && x.behavior === behavior);
        if (has) return p.id;
      }
      return "";
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

    async setGrants(id, grants) {
      try {
        await API.post(`/plugins/${id}/grants`, { grants });
        await this.load();
        Toast.show(I18N.t("tbl.savedOk"), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },

    async loadSettings(pid) {
      try {
        const r = await API.get(`/plugins/${pid}/settings`);
        this.settingsCache[pid] = r.settings || {};
        return this.settingsCache[pid];
      } catch (e) {
        Toast.show(e.message, "error");
        return {};
      }
    },

    async saveSettings(pid, values) {
      try {
        const r = await API.put(`/plugins/${pid}/settings`, values);
        this.settingsCache[pid] = r.settings || values;
        Toast.show(I18N.t("tbl.savedOk"), "success");
        return true;
      } catch (e) {
        Toast.show(e.message, "error");
        return false;
      }
    },

    schemaOf(pid) {
      const p = this.rawById(pid);
      return (p && p.settings_schema) || [];
    },
    async openSettings(pid) {
      this.editingPid = pid;
      this.editValues = {};
      await this.loadSettings(pid);
      this.editValues = { ...(this.settingsCache[pid] || {}) };
    },
    async saveEditing() {
      if (!this.editingPid) return;
      this.editBusy = true;
      const ok = await this.saveSettings(this.editingPid, this.editValues);
      this.editBusy = false;
      if (ok) this.editingPid = "";
    },

    toolbarFor(key) {
      const out = [];
      for (const p of this.raw) {
        if (!this.canRunAny(p, p.toolbar || [])) continue;
        for (const b of (p.toolbar || [])) {
          if ((!b.table || b.table === "*" || b.table === key) &&
              this.canRun(b.behavior))
            out.push({ id: p.id + ":" + b.behavior,
                       tooltip: I18N.lang === "ru"
                         ? (b.tooltip || p.name)
                         : (b.tooltip_en || b.tooltip || p.name),
                       icon: b.icon || "layers",
                       behavior: b.behavior });
        }
      }
      return out;
    },
    canRunAny(p, items) {
      return (items || []).some((x) => x && this.canRun(x.behavior));
    },

    commandList() {
      const out = [];
      const L = I18N.lang;
      for (const p of this.raw)
        for (const c of (p.commands || [])) {
          if (!this.canRun(c.behavior)) continue;
          out.push({ id: "plug:" + p.id + ":" + c.behavior,
                     group: L === "ru" ? "Плагины" : "Plugins",
                     label: L === "ru"
                       ? (c.title || p.name)
                       : (c.title_en || c.title || p.name),
                     icon: window.ICONS.layers,
                     behavior: c.behavior });
        }
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

/* Выполнить поведение на активной таблице (с гейтом capabilities).
   Настройки плагина-владельца подхватываются из кэша стора. */
window.__pluginRun = async function (behavior) {
  const need = (window.PLUGIN_BEHAVIOR_CAPS || {})[behavior];
  if (!need) {
    Toast.show(I18N.lang === "ru"
      ? `Плагин: неизвестное поведение «${behavior}»`
      : `Unknown behavior: ${behavior}`, "error");
    return;
  }
  let st = null, owner = "", caps = [];
  try {
    st = Alpine.store("plugins");
    if (st) {
      for (const p of (st.raw || [])) {
        const has = [...(p.commands || []), ...(p.toolbar || [])]
          .some((x) => x && x.behavior === behavior);
        if (has) { owner = p.id; caps = p.granted_capabilities || []; break; }
      }
    }
  } catch (_) {}
  const missing = need.filter((c) => !caps.includes(c));
  if (missing.length) {
    Toast.show(I18N.lang === "ru"
      ? `Нет возможности: ${missing.join(", ")} (нужен грант администратора)`
      : `Missing capability: ${missing.join(", ")} (ask admin for grant)`,
      "error");
    return;
  }
  let settings = {};
  try {
    if (st && owner) {
      if (!st.settingsCache[owner]) await st.loadSettings(owner);
      settings = st.settingsCache[owner] || {};
    }
  } catch (_) {}
  /* Активная таблица — через реестр компонентов, fallback — скан панелей. */
  let acted = false;
  try {
    const tabs = Alpine.store("tabs");
    const key = tabs && tabs.active && tabs.active.key;
    const tp = key && window.__tables && window.__tables[key];
    if (tp && typeof tp.pluginAction === "function") {
      await tp.pluginAction(behavior, { settings, plugin: owner });
      acted = true;
    }
  } catch (_) {}
  if (acted) return;
  const panes = [...document.querySelectorAll(".tabpane")]
    .filter((p) => p.offsetParent !== null);
  for (const pane of panes) {
    const d = Alpine.$data(pane.firstElementChild || pane);
    if (d && typeof d.pluginAction === "function") {
      d.pluginAction(behavior, { settings, plugin: owner });
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
