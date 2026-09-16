/* SUOT Neo — Часть 17: центр настроек.
 * Appearance: 5 тем, акцент, шрифт, масштаб, стекло, плотность,
 *             радиусы, водяной знак. Живой предпросмотр при наведении.
 * Hotkeys:    персональные переназначаемые горячие клавиши.
 * Экспорт/импорт/сброс настроек.
 */

window.Appearance = {
  defaults: { theme: "dark", accent: "#6366F1", font_family: "system",
              font_scale: 1.0, glass: true, density: "comfortable",
              radius: "md", watermark: "", custom_css: "",
              show_counters: false },

  PRESETS: ["#6366F1", "#3B82F6", "#06B6D4", "#10B981",
            "#F59E0B", "#F43F5E"],
  s: null,

  THEMES: [
    { id: "auto",   label: "Авто",     sw: "#8A8FA3" },
    { id: "dark",   label: "Тёмная",   sw: "#0F1115" },
    { id: "light",  label: "Светлая",  sw: "#F5F6F8" },
    { id: "ocean",  label: "Океан",    sw: "#0B1E33" },
    { id: "forest", label: "Лес",      sw: "#0E1F17" },
    { id: "sunset", label: "Закат",    sw: "#241119" },
  ],
  FONTS: [
    { id: "system",  label: "Системный" },
    { id: "serif",   label: "Serif" },
    { id: "mono",    label: "Mono" },
    { id: "rounded", label: "Округлый" },
  ],

  async load() {
    try {
      this.s = await API.get("/settings/appearance");
    } catch (_) {
      this.s = { ...this.defaults };
    }
    this.apply(this.s);
    try {
      const wm = await API.get("/settings/appearance");
      window.SUOT_WATERMARK = wm.watermark || "";
    } catch (_) {}
  },

  hexA(hex, a) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  },

  apply(s) {
    if (!s) return;
    const de = document.documentElement;
    const theme = s.theme === "auto"
      ? (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)")
        .matches ? "light" : "dark")
      : (s.theme || "dark");
    de.dataset.theme = theme;
    de.dataset.sysTheme = s.theme;
    document.body.dataset.theme = theme;
    this._watchAuto(s.theme);
    de.style.setProperty("--acc", s.accent);
    de.style.setProperty("--acc-soft", this.hexA(s.accent, 0.14));
    de.style.setProperty("--acc-glow", this.hexA(s.accent, 0.35));
    const fams = {
      system: '"Segoe UI", system-ui, -apple-system, sans-serif',
      serif: 'Georgia, "Times New Roman", serif',
      mono: 'Consolas, "Cascadia Mono", "Courier New", monospace',
      rounded: '"Trebuchet MS", Verdana, "Segoe UI", sans-serif' };
    de.style.setProperty("--font-app", fams[s.font_family] || fams.system);
    de.dataset.density = s.density;
    de.dataset.radius = s.radius;
    de.classList.toggle("no-glass", !s.glass);
    document.body.style.zoom = String(s.font_scale || 1);
    this.applyUserCss(s.custom_css || "");
  },

  _watchAuto(theme) {
    if (theme === "auto" && window.matchMedia && !this._autoMq) {
      this._autoMq = window.matchMedia("(prefers-color-scheme: light)");
      const on = (e) => {
        if (this.s && this.s.theme === "auto") {
          document.documentElement.dataset.theme =
            e.matches ? "light" : "dark";
          document.body.dataset.theme =
            e.matches ? "light" : "dark";
        }
      };
      if (typeof this._autoMq.addEventListener === "function")
        this._autoMq.addEventListener("change", on);
      else this._autoMq.addListener(on);
    }
  },

  applyUserCss(css) {
    let el = document.getElementById("user-css");
    if (!css) {
      if (el) el.remove();
      return;
    }
    if (!el) {
      el = document.createElement("style");
      el.id = "user-css";
      document.head.appendChild(el);
    }
    el.textContent = css;
  },

  async saveCustomCss() {
    await this.save({ custom_css: (this.draft.custom_css || "") });
    Toast.show(I18N.t("tbl.savedOk"), "success");
  },

  /* Живой предпросмотр: применить временно / вернуть сохранённое */
  preview(s) { this.apply({ ...this.s, ...s }); },
  cancelPreview() { this.apply(this.s); },

  async save(patch) {
    if (!this.s) {
      const cur = document.body.dataset.theme ||
                  document.documentElement.dataset.theme || "dark";
      this.s = { ...this.defaults, theme: cur };
    }
    this.s = { ...this.s, ...patch };
    this.apply(this.s);
    try { await API.post("/settings/appearance", this.s); }
    catch (e) { Toast.show(e.message, "error"); }
  },
};

window.Hotkeys = {
  DEFAULTS: { palette: "Ctrl+K", new_record: "Ctrl+N", search: "Ctrl+F",
              help: "F1", theme_toggle: "Ctrl+Shift+T",
              ai_chat: "Ctrl+I", export_table: "Ctrl+E", refresh: "F5",
              quick_capture: "Ctrl+Q" },
  LABELS: { palette: "Палитра команд", new_record: "Новая запись",
            search: "Поиск по таблице", help: "Справка",
            theme_toggle: "Сменить тему", ai_chat: "AI-чат",
            export_table: "Экспорт таблицы", refresh: "Обновить данные",
            quick_capture: "Быстрая заметка" },
  bindings: { ...this.DEFAULTS },
  capturing: null, // имя действия во время захвата

  comboOf(e) {
    const k = e.key;
    if (["Control", "Shift", "Alt", "Meta"].includes(k)) return "";
    let key = k.length === 1 ? k.toUpperCase() : k;
    const parts = [];
    if (e.ctrlKey || e.metaKey) parts.push("Ctrl");
    if (e.shiftKey) parts.push("Shift");
    if (e.altKey) parts.push("Alt");
    parts.push(key);
    return parts.join("+");
  },

  matches(e, combo) {
    return !!combo && this.comboOf(e) === combo;
  },

  editable(t) {
    return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" ||
                 t.isContentEditable || t.tagName === "SELECT");
  },

  async load() {
    try {
      const h = await API.get("/settings/hotkeys");
      this.bindings = { ...this.DEFAULTS, ...h };
    } catch (_) {
      this.bindings = { ...this.DEFAULTS };
    }
  },

  onKeydown(e) {
    if (this.capturing) return;               // захват обрабатывает UI
    const b = this.bindings || {};
    const ed = this.editable(e.target);
    for (const action of Object.keys(b)) {
      if (!this.matches(e, b[action])) continue;
      // В полях ввода перехватываем только Ctrl/Media-комбо и F-клавиши
      const isFn = /^F\d{1,2}$/.test(b[action]);
      const hasMod = /^(Ctrl|Alt)/.test(b[action]);
      if (ed && !isFn && !hasMod) continue;
      e.preventDefault();
      this.run(action);
      return true;
    }
    return false;
  },

  run(action) {
    switch (action) {
      case "palette":
        document.dispatchEvent(new CustomEvent("suot-palette-open",
          { bubbles: true }));
        break;
      case "theme_toggle": {
        const ids = Appearance.THEMES.map((t) => t.id);
        const i = ids.indexOf(Appearance.s ? Appearance.s.theme : "dark");
        Appearance.save({ theme: ids[(i + 1) % ids.length] });
        break; }
      default:
        document.dispatchEvent(new CustomEvent("suot-hotkey-" +
          action.replace(/_/g, "-"), { bubbles: true }));
    }
    Sounds.play("click");
  },
};

window.addEventListener("keydown", (e) => {
  try { Hotkeys.onKeydown(e); } catch (_) {}
}, true);

/* ── Alpine-компонент центра настроек ── */

window.settingsCenter = function () {
  return {
    open: false,
    tab: "look",                 // look | keys
    draft: { ...window.Appearance.defaults },

    hotkeys: {},
    hkCapture: null,             // имя действия в режиме захвата
    hkConflict: "",
    resetConfirm: false,
    pwdForm: { old: "", p1: "", p2: "" },

    async changePassword() {
      const f = this.pwdForm;
      if (!f.old || !f.p1 || !f.p2) return;
      if (f.p1 !== f.p2) {
        Toast.show(I18N.lang === "ru"
          ? "Пароли не совпадают" : "Passwords do not match", "error");
        Sounds.play("error");
        return;
      }
      try {
        await API.post("/auth/change_password",
          { old_password: f.old, new_password: f.p1 });
        Toast.show(I18N.t("tbl.savedOk"), "success");
        Sounds.play("success");
        this.pwdForm = { old: "", p1: "", p2: "" };
      } catch (e) {
        Toast.show(e.message, "error");
        Sounds.play("error");
      }
    },
    themes: window.Appearance.THEMES,
    fonts: window.Appearance.FONTS,
    icons: window.ICONS,
    t: (k) => I18N.t(k),
    ru: (a, b) => I18N.lang === "ru" ? a : b,

    openCenter(tab) {
      this.tab = tab || "look";
      this.draft = { ...(window.Appearance.s ||
        window.Appearance.defaults) };
      this.hotkeys = { ...window.Hotkeys.bindings };
      this.open = true;
      this.resetConfirm = false;
      this.hkCapture = null;
    },

    /* Живой предпросмотр темы */
    hoverTheme(id) { window.Appearance.preview({ theme: id }); },
    leaveTheme() { window.Appearance.cancelPreview(); },
    pickTheme(id) {
      this.draft.theme = id;
      window.Appearance.save({ theme: id });
    },

    pickAccent(ev) {
      window.Appearance.save({ accent: ev.target.value });
      this.draft.accent = ev.target.value;
    },
    setFont(id) { window.Appearance.save({ font_family: id });
                  this.draft.font_family = id; },
    setScale(v) { window.Appearance.save({ font_scale: v });
                  this.draft.font_scale = v; },
    toggleGlass() { window.Appearance.save({ glass: !this.draft.glass });
                    this.draft.glass = !this.draft.glass; },
    setGlass(v) {
      if (this.draft.glass === v) return;
      this.toggleGlass();
    },
    setDensity(d) { window.Appearance.save({ density: d });
                    this.draft.density = d; },
    setRadius(r) { window.Appearance.save({ radius: r });
                   this.draft.radius = r; },
    async saveWatermark() {
      await window.Appearance.save({ watermark: this.draft.watermark });
      window.SUOT_WATERMARK = this.draft.watermark;
      Toast.show(I18N.t("tbl.savedOk"), "success");
    },

    async saveCustomCss() {
      await window.Appearance.save(
        { custom_css: this.draft.custom_css || "" });
      window.Appearance.applyUserCss(this.draft.custom_css || "");
      Toast.show(I18N.t("tbl.savedOk"), "success");
      Sounds.play("success");
    },

    /* Хоткеи */
    startCapture(action) {
      this.hkCapture = action;
      this.hkConflict = "";
      this._capHandler = (e) => {
        e.preventDefault(); e.stopPropagation();
        if (e.key === "Escape") { this.stopCapture(); return; }
        const combo = window.Hotkeys.comboOf(e);
        if (!combo) return;
        const clash = Object.entries(this.hotkeys)
          .find(([k, v]) => v === combo && k !== action);
        if (clash) {
          this.hkConflict = window.Hotkeys.LABELS[clash[0]] || clash[0];
          return;
        }
        this.hotkeys[action] = combo;
        this.persistHotkeys();
        this.stopCapture();
      };
      window.addEventListener("keydown", this._capHandler,
                              { capture: true });
    },
    stopCapture() {
      this.hkCapture = null;
      if (this._capHandler)
        window.removeEventListener("keydown", this._capHandler,
                                   { capture: true });
    },
    clearHotkey(action) {
      this.hotkeys[action] = window.Hotkeys.DEFAULTS[action];
      this.persistHotkeys();
    },
    async persistHotkeys() {
      try {
        await API.post("/settings/hotkeys", { hotkeys: this.hotkeys });
        await window.Hotkeys.load();
        Toast.show(I18N.t("tbl.savedOk"), "success");
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* Сброс всего */
    async doReset() {
      try {
        const r = await API.post("/settings/reset");
        window.Appearance.s = r.appearance;
        window.Appearance.apply(window.Appearance.s);
        await window.Hotkeys.load();
        this.draft = { ...window.Appearance.s };
        this.hotkeys = { ...window.Hotkeys.bindings };
        Toast.show(I18N.t("tbl.savedOk"), "success");
      } catch (e) { Toast.show(e.message, "error"); }
      this.resetConfirm = false;
    },

    /* Экспорт / импорт */
    async exportSettings() {
      try {
        const res = await fetch("/api/settings/export", { headers:
          { Authorization: "Bearer " + (localStorage.getItem("suot_token") ||
            sessionStorage.getItem("suot_token_session") || "") } });
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "suot-settings.json";
        a.click();
        URL.revokeObjectURL(a.href);
        Sounds.play("success");
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async importSettings(file) {
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        await API.post("/settings/import", data);
        await window.Appearance.load();
        await window.Hotkeys.load();
        this.draft = { ...window.Appearance.s };
        this.hotkeys = { ...window.Hotkeys.bindings };
        Toast.show(I18N.t("tbl.savedOk"), "success");
        Sounds.play("success");
      } catch (e) { Toast.show(e.message, "error"); }
    },
  };
};
