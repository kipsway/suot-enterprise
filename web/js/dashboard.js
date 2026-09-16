/* SUOT Neo — Дашборд 3.0 (Часть 24): KPI, календарь, таймлайн + dnd-виджеты,
   «Мои задачи сегодня», лента активности, ярлыки видов. */
(function () {
  const WID_DEFAULT = ["kpi", "tasks", "activity", "overdue", "recent",
                       "calendar", "shortcuts"];

  window.dashBoard = function () {
    return {
      period: "all",
      stats: null,
      loading: true,
      calYear: new Date().getFullYear(),
      calMonth: new Date().getMonth(),
      calEvents: [],
      calLoading: false,
      calDnD: null,             // {table,id,field}
      pngBusy: false,

      /* ── Дашборд 3.0 ── */
      tasks: [],
      activities: [],
      actLoading: false,
      widgetOrder: WID_DEFAULT.slice(),
      dragging: null,

      icons: window.ICONS,
      t: (k) => I18N.t(k),
      ru: (a, b) => I18N.lang === "ru" ? a : b,

      async init() {
        await this.load();
        await this.loadCalendar();
        this.loadTasks();
        this.loadActivity();
        this.restoreOrder();
      },

      /* ── dnd-виджеты (Часть 24) ── */
      saveOrder() {
        try {
          localStorage.setItem("suot_dash_order",
            JSON.stringify(this.widgetOrder));
        } catch (_) {}
      },
      restoreOrder() {
        try {
          const raw = localStorage.getItem("suot_dash_order");
          this.widgetOrder = raw ? JSON.parse(raw) : WID_DEFAULT.slice();
        } catch (_) { this.widgetOrder = WID_DEFAULT.slice(); }
        this.$nextTick(() => this.applyOrder());
      },
      applyOrder() {
        const box = document.querySelector(".dash-widgets");
        if (!box) return;
        for (const wid of this.widgetOrder) {
          const el = box.querySelector('[data-wid="' + wid + '"]');
          if (el) box.appendChild(el);
        }
      },
      dragStart(wid, e) {
        this.dragging = wid;
        if (e && e.dataTransfer) {
          e.dataTransfer.effectAllowed = "move";
          try { e.dataTransfer.setData("text/plain", wid); } catch (_) {}
        }
      },
      dragEnter(wid) {
        if (this.dragging && this.dragging !== wid) {
          const box = document.querySelector(".dash-widgets");
          const a = box.querySelector('[data-wid="' + this.dragging + '"]');
          const b = box.querySelector('[data-wid="' + wid + '"]');
          if (a && b && a !== b) box.insertBefore(a, b);
        }
      },
      dropDone(wid) {
        if (!this.dragging) return;
        this.widgetOrder = [...document.querySelectorAll(".dash-widgets .dash-w")]
          .map((el) => el.getAttribute("data-wid"))
          .filter((x) => WID_DEFAULT.includes(x));
        this.saveOrder();
        this.dragging = null;
      },
      widLabel(w) {
        const map = {
          kpi: this.ru("Показатели", "Metrics"),
          tasks: this.ru("Мои задачи сегодня", "Today's tasks"),
          activity: this.ru("Лента активности", "Activity feed"),
          overdue: this.ru("Просрочки", "Overdue"),
          recent: this.ru("Последние события", "Recent events"),
          calendar: this.ru("Календарь", "Calendar"),
          shortcuts: this.ru("Разделы", "Sections"),
        };
        return map[w] || w;
      },

      async loadTasks() {
        try {
          const res = await API.get("/dash/tasks");
          this.tasks = res.tasks || [];
        } catch (e) { this.tasks = []; }
      },
      async loadActivity() {
        this.actLoading = true;
        try {
          const res = await API.get("/dash/activity?limit=25");
          this.activities = res.items || [];
        } catch (e) { this.activities = []; }
        this.actLoading = false;
      },
      taskClass(t) {
        if (t.overdue) return "dt-over";
        if (t.days === 0) return "dt-warn";
        return "dt-ok";
      },
      taskBadge(t) {
        if (t.overdue) return this.ru("просрочено", "overdue");
        if (t.days === 0) return this.ru("сегодня", "today");
        return "+" + t.days;
      },
      openTask(t) {
        Alpine.store("tabs").open(t.section);
      },
      sevClass(s) {
        const v = String(s || "").toLowerCase();
        if (v === "warning") return "b-orange";
        if (v === "error" || v === "critical") return "b-red";
        return "b-blue";
      },
      actTime(ts) {
        if (!ts) return "";
        const s = String(ts);
        return s.length >= 16 ? s.slice(0, 16).replace("T", " ") : s;
      },

      async setPeriod(p) {
        this.period = p;
        await this.load();
        await this.loadCalendar();
      },
      async load() {
        this.loading = true;
        try {
          this.stats = await API.get("/dash/stats?period=" + this.period);
        } catch (e) { Toast.show(e.message, "error"); }
        this.loading = false;
      },

      /* ── KPI ── */
      kpis() {
        if (!this.stats) return [];
        const c = this.stats.counts;
        const od = this.stats.overdue_total;
        const items = [
          { key: "employees", icon: "users", color: "var(--acc)",
            label: this.ru("Сотрудники", "Employees"), count: c.employees || 0 },
          { key: "violations", icon: "alert", color: "var(--err)",
            label: this.ru("Нарушения", "Violations"), count: c.violations || 0 },
          { key: "ppe", icon: "hardhat", color: "var(--ok)",
            label: this.ru("СИЗ", "PPE"), count: c.ppe || 0 },
          { key: "training", icon: "checkAll", color: "#A855F7",
            label: this.ru("Обучение", "Training"), count: c.training || 0 },
          { key: "overdue", icon: "clock", color: "#F59E0B",
            label: this.ru("Просрочки", "Overdue"), count: od },
        ];
        return items;
      },
      openFiltered(key) {
        if (key === "overdue") {
          Alpine.store("tabs").open("employees");
          setTimeout(() => {
            const tp = window.__tables["employees"];
            if (tp) { tp.q = ""; tp.filters = {}; }
            Toast.show(this.ru(
              "Просрочки: см. колонки с датами", "See overdue date columns"));
          }, 400);
          return;
        }
        Alpine.store("tabs").open(key);
      },

      safetyColor() {
        const s = this.stats ? this.stats.safety : 100;
        if (s >= 80) return "var(--ok)";
        if (s >= 50) return "var(--warn)";
        return "var(--err)";
      },

      /* ── Count-up ── */
      displayCount(el, target) {
        if (window.matchMedia &&
            matchMedia("(prefers-reduced-motion: reduce)").matches)
          return String(target);
        const dur = 500, start = performance.now();
        const step = (now) => {
          const p = Math.min(1, (now - start) / dur);
          el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
          if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
        return "";
      },

      /* ── Календарь ── */
      get calMonthName() {
        const names = this.ru(
          ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль",
           "Август","Сентябрь","Октябрь","Ноябрь","Декабрь"],
          ["January","February","March","April","May","June","July",
           "August","September","October","November","December"]);
        return names[this.calMonth] + " " + this.calYear;
      },
      get calGrid() {
        const y = this.calYear, m = this.calMonth;
        const first = new Date(y, m, 1);
        let startDay = (first.getDay() + 6) % 7;  // Пн=0
        const daysInMonth = new Date(y, m + 1, 0).getDate();
        const daysInPrev = new Date(y, m, 0).getDate();
        const cells = [];
        for (let i = startDay - 1; i >= 0; i--)
          cells.push({ day: daysInPrev - i, out: true, events: [] });
        const evByDate = {};
        for (const e of this.calEvents) {
          const dd = parseInt(e.date.split("-")[2], 10);
          (evByDate[dd] = evByDate[dd] || []).push(e);
        }
        const today = new Date();
        for (let d = 1; d <= daysInMonth; d++) {
          cells.push({
            day: d, out: false,
            today: d === today.getDate() && m === today.getMonth()
                   && y === today.getFullYear(),
            events: evByDate[d] || [],
          });
        }
        while (cells.length % 7 !== 0)
          cells.push({ day: cells.length - startDay - daysInMonth + 1,
                       out: true, events: [] });
        return cells;
      },
      async calMove(delta) {
        this.calMonth += delta;
        if (this.calMonth < 0) { this.calMonth = 11; this.calYear--; }
        if (this.calMonth > 11) { this.calMonth = 0; this.calYear++; }
        await this.loadCalendar();
      },
      async loadCalendar() {
        this.calLoading = true;
        const y = this.calYear, m = this.calMonth;
        const start = `${y}-${String(m + 1).padStart(2, "0")}-01`;
        const end = `${y}-${String(m + 1).padStart(2, "0")}-31`;
        try {
          const res = await API.get(
            `/dash/calendar?start=${start}&end=${end}`);
          this.calEvents = res.events;
        } catch (e) { this.calEvents = []; }
        this.calLoading = false;
      },
      calDayClass(cell) {
        if (cell.out) return "cal-out";
        if (cell.today) return "cal-today";
        if (cell.events.some((e) => e.overdue)) return "cal-overdue";
        if (cell.events.length) return "cal-has";
        return "";
      },
      async calDrop(cell) {
        if (!this.calDnD || cell.out) return;
        const d = this.calDnD;
        const nd = `${this.calYear}-${String(this.calMonth + 1).padStart(2, "0")}-${String(cell.day).padStart(2, "0")}`;
        try {
          await API.post("/dash/reschedule",
            { table: d.table, record_id: d.id, field: d.field,
              new_date: this._toRu(nd) });
          Toast.show(this.ru("Срок перенесён ✓", "Rescheduled ✓"), "success");
          await this.loadCalendar();
        } catch (e) { Toast.show(e.message, "error"); }
        this.calDnD = null;
      },
      _toRu(iso) {
        const [y, m, d] = iso.split("-");
        return `${d}.${m}.${y}`;
      },
      openEvent(e) {
        Alpine.store("tabs").open(e.table);
      },

      /* ── PNG-экспорт дашборда ── */
      exportPng() {
        if (!this.stats) return;
        const canvas = document.createElement("canvas");
        canvas.width = 800; canvas.height = 400;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#0F1115";
        ctx.fillRect(0, 0, 800, 400);
        ctx.fillStyle = "#6366F1";
        ctx.font = "bold 24px Inter, sans-serif";
        ctx.fillText("ОхранаТруда Про — Дашборд", 40, 50);
        ctx.fillStyle = "#A8B0BF";
        ctx.font = "13px Inter, sans-serif";
        ctx.fillText(new Date().toLocaleString("ru"), 40, 72);
        const kpis = this.kpis();
        const cw = 140, gap = 16, x0 = 40, y0 = 110;
        kpis.forEach((k, i) => {
          const x = x0 + i * (cw + gap);
          ctx.fillStyle = "#1A1E26";
          ctx.beginPath();
          ctx.roundRect(x, y0, cw, 90, 12);
          ctx.fill();
          ctx.strokeStyle = "rgba(255,255,255,.08)";
          ctx.stroke();
          ctx.fillStyle = k.color;
          ctx.font = "bold 32px Inter, sans-serif";
          ctx.fillText(String(k.count), x + 14, y0 + 48);
          ctx.fillStyle = "#A8B0BF";
          ctx.font = "12px Inter, sans-serif";
          ctx.fillText(k.label, x + 14, y0 + 72);
        });
        ctx.fillStyle = "#F2F4F8";
        ctx.font = "bold 16px Inter, sans-serif";
        ctx.fillText("Индекс безопасности: " +
          (this.stats ? this.stats.safety : 100) + "/100", 40, 250);
        ctx.fillStyle = "#A8B0BF";
        ctx.font = "13px Inter, sans-serif";
        let y = 280;
        (this.stats ? this.stats.overdue.slice(0, 6) : []).forEach((o) => {
          ctx.fillText(`⚠ ${o.label}: ${o.title} — ${o.date} ` +
            `(${o.days_overdue} дн.)`, 40, y);
          y += 22;
        });
        canvas.toBlob((blob) => {
          if (!blob) return;
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "dashboard_" + new Date().toISOString().slice(0, 10)
            + ".png";
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(a.href);
          Toast.show(this.ru("PNG сохранён ✓", "PNG saved ✓"), "success");
        }, "image/png");
      },
    };
  };
})();