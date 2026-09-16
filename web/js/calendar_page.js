/* SUOT Neo — Календарь + Время (Часть 25)
   Месячная сетка, события, ДР сотрудников, категории-цвета, агенда дня. */
window.calendarPage = function () {
  return {
    // текущий отображаемый месяц: year, month (1..12), day (для перехода)
    year: 0,
    month: 0,
    today: "",
    grid: [],           // 42 ячейки [{d, date, inMonth, today, events}]
    eventModal: false,  // модалка события
    ev: { id: 0, title: "", date: "", time: "09:00", all_day: false,
          category_id: 0, repeat: "", remind_min: 0, note: "", location: "" },
    cats: [],           // категории [{id,name,color}]
    catModal: false,    // модалка категории
    cat: { id: 0, name: "", color: "#4F8DFF" },
    editing: false,
    loading: false,
    selDay: "",         // выбранный день для агенды
    agenda: [],         // агенда дня
    icons: window.ICONS,
    ru: (a, b) => I18N.lang === "ru" ? a : b,
    wd: I18N.lang === "ru"
      ? ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
      : ["Mo","Tu","We","Th","Fr","Sa","Su"],

    async init() {
      const d = new Date();
      this.year = d.getFullYear();
      this.month = d.getMonth() + 1;
      this.today = this.fmt(d);
      this.selDay = this.today;
      await this.loadData();
    },

    fmt(d) {
      const p = (n) => String(n).padStart(2, "0");
      return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
    },
    curDate() { return this.year + "-"
      + String(this.month).padStart(2, "0") + "-01"; },

    // количество дней в месяце
    dim(y, m) { return new Date(y, m, 0).getDate(); },

    weekStart(dateStr) {  // понедельник как начало недели
      const [y, m, d] = dateStr.split("-").map(Number);
      const wd = (new Date(y, m - 1, d).getDay() + 6) % 7;
      return wd;
    },

    async loadData() {
      this.loading = true;
      const [y, m] = [this.year, this.month];
      const start = this.curDate();
      const last = this.dim(y, m);
      const end = y + "-" + String(m).padStart(2, "0")
        + "-" + String(last).padStart(2, "0");
      try {
        const [evs, cats] = await Promise.all([
          API.get("/calendar/events?start=" + start + "&end=" + end
            + "&include_bdays=1"),
          API.get("/calendar/categories"),
        ]);
        this.cats = cats.categories || [];
        this.buildGrid(evs.events || []);
      } catch (e) { Toast.show(e.message, "error"); }
      this.loading = false;
      await this.loadAgenda();
    },

    buildGrid(events) {
      const [y, m] = [this.year, this.month];
      const first = y + "-" + String(m).padStart(2, "0") + "-01";
      const offset = this.weekStart(first);
      const daysInMonth = this.dim(y, m);
      let prev = this.dim(m === 1 ? y - 1 : y, m === 1 ? 12 : m - 1);
      const byDate = {};
      for (const e of events) { (byDate[e.date] = byDate[e.date] || []).push(e); }
      this.grid = [];
      const mk = (date, d, inMonth) => ({
        d, date, inMonth,
        today: date === this.today,
        events: (byDate[date] || []).slice(0, 3),
        more: (byDate[date] || []).length,
      });
      for (let i = 0; i < 42; i++) {
        const cell = i - offset + 1;
        if (cell < 1) {
          const pm = m === 1 ? 12 : m - 1;
          const py = m === 1 ? y - 1 : y;
          this.grid.push(mk(
            py + "-" + String(pm).padStart(2, "0")
              + "-" + String(prev - (0 - cell)).padStart(2, "0"),
            prev - (0 - cell), false));
        } else if (cell > daysInMonth) {
          const nm = m === 12 ? 1 : m + 1;
          const ny = m === 12 ? y + 1 : y;
          this.grid.push(mk(
            ny + "-" + String(nm).padStart(2, "0")
              + "-" + String(cell - daysInMonth).padStart(2, "0"),
            cell - daysInMonth, false));
        } else {
          this.grid.push(mk(
            y + "-" + String(m).padStart(2, "0")
              + "-" + String(cell).padStart(2, "0"), cell, true));
        }
      }
    },

    monthLabel() {
      const R = ["Январь","Февраль","Март","Апрель","Май","Июнь",
                 "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"];
      const E = ["Jan","Feb","Mar","Apr","May","Jun",
                 "Jul","Aug","Sep","Oct","Nov","Dec"];
      return (I18N.lang === "ru" ? R : E)[this.month - 1]
        + " " + this.year;
    },

    delta(months) {
      const total = (this.year * 12 + (this.month - 1) + months);
      this.year = Math.floor(total / 12);
      this.month = total % 12 + 1;
      this.loadData();
    },
    todayBtn() {
      const d = new Date();
      this.year = d.getFullYear();
      this.month = d.getMonth() + 1;
      this.selDay = this.today;
      this.loadData();
    },

    selectDay(date) { this.selDay = date; this.loadAgenda(); },

    async loadAgenda() {
      try {
        const r = await API.get("/calendar/agenda?day=" + this.selDay);
        this.agenda = r.items || [];
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* ── события ── */
    openNew(day) {
      this.editing = false;
      this.ev = { id: 0, title: "", date: day || this.selDay,
        time: "09:00", all_day: false,
        category_id: this.cats.length ? this.cats[0].id : 0,
        repeat: "", remind_min: 0, note: "", location: "" };
      this.eventModal = true;
    },
    openEdit(ev) {
      this.editing = true;
      this.ev = {
        id: ev.id || 0, title: ev.title || "",
        date: ev.date, time: ev.time || "09:00",
        all_day: !!ev.all_day,
        category_id: ev.category_id || 0,
        repeat: ev.repeat || "", remind_min: ev.remind_min || 0,
        note: ev.note || "", location: ev.location || "",
      };
      this.eventModal = true;
    },
    catName(id) {
      for (const c of this.cats) if (c.id === id) return c.name;
      return "—";
    },
    catColor(id) {
      for (const c of this.cats) if (c.id === id) return c.color;
      return "#4F8DFF";
    },
    async saveEvent() {
      if (!this.ev.title.trim()) { Toast.show("Укажите название", "error"); return; }
      try {
        const body = this.ev;
        if (this.editing)
          await API.put("/calendar/events/" + this.ev.id, body);
        else
          await API.post("/calendar/events", body);
        Toast.show("Событие сохранено", "ok");
        this.eventModal = false;
        this.loadData();
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async delEvent() {
      if (!confirm("Удалить событие?")) return;
      try {
        await API.del("/calendar/events/" + this.ev.id);
        Toast.show("Событие удалено", "ok");
        this.eventModal = false;
        this.loadData();
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* ── категории ── */
    openCats() {
      this.catModal = true;
      this.cat = { id: 0, name: "", color: "#4F8DFF" };
    },
    openCatEdit(c) {
      this.cat = { id: c.id, name: c.name, color: c.color };
    },
    async saveCat() {
      if (!this.cat.name.trim()) { Toast.show("Укажите название", "error"); return; }
      try {
        if (this.cat.id)
          await API.put("/calendar/categories/" + this.cat.id,
            { name: this.cat.name, color: this.cat.color });
        else
          await API.post("/calendar/categories",
            { name: this.cat.name, color: this.cat.color });
        Toast.show("Категория сохранена", "ok");
        this.loadData();
      } catch (e) { Toast.show(e.message, "error"); }
    },
    async delCat(c) {
      if (!confirm("Удалить категорию?")) return;
      try {
        await API.del("/calendar/categories/" + c.id);
        Toast.show("Категория удалена", "ok");
        this.loadData();
      } catch (e) { Toast.show(e.message, "error"); }
    },

    /* короткая подпись события в ячейке */
    evTag(e) {
      const t = (e.time && !e.all_day ? e.time + " " : "") + (e.title || "");
      return t.slice(0, 26);
    },
  };
};