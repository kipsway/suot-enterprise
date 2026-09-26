/* ═══ ОхранаТруда Про — сайт-лендинг: JS (esprima-safe, без ?. / ??) ═══ */

(function () {
  "use strict";

  /* ── SVG-иконки Aurora (единый язык с программой, без эмодзи) ── */
  var IC_OPEN = '<svg viewBox="0 0 24 24" aria-hidden="true">';
  var IC_CLOSE = "</svg>";
  var ICONS = {
    users: IC_OPEN + '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>' +
      '<circle cx="9" cy="7" r="4"/>' +
      '<path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>' + IC_CLOSE,
    hardhat: IC_OPEN + '<path d="M4 18v-4a8 8 0 0 1 5-7.4V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1.6A8 8 0 0 1 20 14v4"/>' +
      '<line x1="2" y1="18" x2="22" y2="18"/><line x1="12" y1="4" x2="12" y2="9"/>' + IC_CLOSE,
    cap: IC_OPEN + '<path d="M22 10L12 5 2 10l10 5 10-5z"/>' +
      '<path d="M6 12v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/>' + IC_CLOSE,
    alert: IC_OPEN + '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>' +
      '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>' + IC_CLOSE,
    chart: IC_OPEN + '<line x1="12" y1="20" x2="12" y2="10"/>' +
      '<line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>' + IC_CLOSE,
    calendar: IC_OPEN + '<rect x="3" y="4" width="18" height="18" rx="2"/>' +
      '<line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>' +
      '<line x1="3" y1="10" x2="21" y2="10"/>' + IC_CLOSE,
    printer: IC_OPEN + '<polyline points="6 9 6 2 18 2 18 9"/>' +
      '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>' +
      '<rect x="6" y="14" width="12" height="8"/>' + IC_CLOSE,
    sparkles: IC_OPEN + '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/>' +
      '<path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15z"/>' + IC_CLOSE,
    shield: IC_OPEN + '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>' +
      '<polyline points="9 12 11 14 15 10"/>' + IC_CLOSE,
    zap: IC_OPEN + '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>' + IC_CLOSE,
    globe: IC_OPEN + '<circle cx="12" cy="12" r="10"/>' +
      '<line x1="2" y1="12" x2="22" y2="12"/>' +
      '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>' + IC_CLOSE,
    chat: IC_OPEN + '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>' + IC_CLOSE,
    tool: IC_OPEN + '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>' + IC_CLOSE,
    package: IC_OPEN + '<path d="M16.5 9.4L7.55 4.24"/>' +
      '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>' +
      '<polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>' + IC_CLOSE,
    monitor: IC_OPEN + '<rect x="2" y="3" width="20" height="14" rx="2"/>' +
      '<line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>' + IC_CLOSE,
    rocket: IC_OPEN + '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/>' +
      '<path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>' +
      '<path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>' + IC_CLOSE,
    file: IC_OPEN + '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' +
      '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>' +
      '<line x1="16" y1="17" x2="8" y2="17"/>' + IC_CLOSE,
    refresh: IC_OPEN + '<polyline points="23 4 23 10 17 10"/>' +
      '<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>' + IC_CLOSE,
    grid: IC_OPEN + '<rect x="3" y="3" width="7" height="7"/>' +
      '<rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>' +
      '<rect x="3" y="14" width="7" height="7"/>' + IC_CLOSE,
    clock: IC_OPEN + '<circle cx="12" cy="12" r="10"/>' +
      '<polyline points="12 6 12 12 16 14"/>' + IC_CLOSE,
    edit: IC_OPEN + '<path d="M12 20h9"/>' +
      '<path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>' + IC_CLOSE,
    hash: IC_OPEN + '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/>' +
      '<line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>' + IC_CLOSE,
    key: IC_OPEN + '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>' + IC_CLOSE
  };

  function paintIcons() {
    var els = document.querySelectorAll("[data-ic]");
    for (var i = 0; i < els.length; i++) {
      var name = els[i].getAttribute("data-ic");
      if (name && ICONS[name] && !els[i].getAttribute("data-ic-done")) {
        els[i].innerHTML = ICONS[name];
        els[i].setAttribute("data-ic-done", "1");
      }
    }
  }

  var DW = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  var MONTH = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
  var DW_EN = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
  var MONTH_EN = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];
  var DW_RU = DW;
  var MONTH_RU = MONTH;
  var MONTH_Y = ["Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
    "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"];

  var now = new Date();
  var viewYear = now.getFullYear();
  var viewMonth = now.getMonth(); // 0-11
  var cals = [
    { el: document.getElementById("miniCal"), title: document.getElementById("mcTitle") },
    { el: document.getElementById("miniCal2"), title: document.getElementById("mcTitle2") }
  ];

  /* ── типографика: айлат в camel ── */

  function isLeap(y) { return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0; }

  function daysInMonth(y, m) { return [31, isLeap(y) ? 29 : 28, 31, 30, 31, 30,
    31, 31, 30, 31, 30, 31][m]; }

  /* детерминированные «события» календаря (как в приложении) */
  function dayHasEvent(d, m) { return (d + m * 3) % 7 === 0 || d % 11 === 0; }

  function pad2(n) { return n < 10 ? "0" + n : "" + n; }

  function paintCal(y, m) {
    var dm = daysInMonth(y, m);
    var firstDow = new Date(y, m, 1).getDay(); // 0=Вс
    var lead = (firstDow === 0 ? 6 : firstDow - 1); // понедельник-первый
    var t = now;
    var isCur = (y === t.getFullYear() && m === t.getMonth());
    var html = "";

    for (var w = 0; w < 7; w++) { html += '<div class="dw">' + DW[w] + "</div>"; }

    var total = lead + dm;
    var cells = Math.ceil(total / 7) * 7;
    for (var i = 0; i < cells; i++) {
      var d = i - lead + 1;
      if (d < 1 || d > dm) { html += '<div class="dn off"></div>'; continue; }
      var cls = "dn";
      if (isCur && d === t.getDate()) { cls += " today"; }
      if (dayHasEvent(d, m)) { cls += " ev"; }
      html += '<div class="' + cls + '">' + d + "</div>";
    }
    for (var ci = 0; ci < cals.length; ci++) {
      if (cals[ci].el) {
        cals[ci].el.innerHTML = html;
        cals[ci].title.textContent = MONTH[m] + " " + y;
      }
    }
  }

  function renderCal() { paintCal(viewYear, viewMonth); }

  function moveMonth(delta) {
    viewMonth += delta;
    if (viewMonth > 11) { viewMonth = 0; viewYear++; }
    if (viewMonth < 0) { viewMonth = 11; viewYear--; }
    renderCal();
  }

  var mcBtns = document.querySelectorAll("[data-mc]");
  for (var bi = 0; bi < mcBtns.length; bi++) {
    mcBtns[bi].addEventListener("click", (function (dx) {
      return function () { moveMonth(dx); };
    })(parseInt(mcBtns[bi].getAttribute("data-mc"), 10)));
  }
  renderCal();

  /* ── живое демо: переключение вкладок ── */
  var demoViews = document.querySelectorAll("[data-view]");
  var demoTabs = document.querySelectorAll(".mini-side span[data-tab], .mini-tool[data-tab]");

  function showView(tab) {
    for (var i = 0; i < demoViews.length; i++) {
      if (demoViews[i].getAttribute("data-view") === tab) {
        demoViews[i].style.display = "";
      } else {
        demoViews[i].style.display = "none";
      }
    }
    var sideTabs = document.querySelectorAll(".mini-side span[data-tab]");
    for (var j = 0; j < sideTabs.length; j++) {
      if (sideTabs[j].getAttribute("data-tab") === tab) {
        sideTabs[j].classList.add("active");
      } else {
        sideTabs[j].classList.remove("active");
      }
    }
  }

  for (var ti = 0; ti < demoTabs.length; ti++) {
    (function (el) {
      el.addEventListener("click", function () {
        showView(el.getAttribute("data-tab"));
      });
    })(demoTabs[ti]);
  }
  showView("dashboard");

  /* ── живое демо: поиск по сотрудникам ── */
  var empSearch = document.getElementById("empSearch");
  if (empSearch) {
    empSearch.addEventListener("input", function () {
      var q = empSearch.value.toLowerCase();
      var rows = document.querySelectorAll("#empTable tbody tr");
      for (var ri = 0; ri < rows.length; ri++) {
        var text = rows[ri].textContent.toLowerCase();
        if (!q || text.indexOf(q) !== -1) { rows[ri].style.display = ""; }
        else { rows[ri].style.display = "none"; }
      }
    });
  }

  /* ── KPI-счётчики (бегущий набор) ── */
  var KPI = [
    { el: document.getElementById("kpi1"), target: 148, suffix: "" },
    { el: document.getElementById("kpi2"), target: 1260, suffix: "" },
    { el: document.getElementById("kpi3"), target: 64, suffix: "" }
  ];
  var kpiStarted = false;

  function fmt(n) { return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " "); }

  function tickKpi(k, step) {
    var val = 0;
    var total = Math.max(1, Math.ceil(k.target / Math.max(1, step)));
    var run = 0;
    var timer = setInterval(function () {
      run += step;
      if (run >= k.target) { run = k.target; clearInterval(timer); }
      k.el.textContent = fmt(run);
      total--;
      if (total <= 0) { k.el.textContent = fmt(k.target); clearInterval(timer); }
    }, 24);
  }

  function startKpis() {
    if (kpiStarted) { return; }
    kpiStarted = true;
    for (var i = 0; i < KPI.length; i++) {
      tickKpi(KPI[i], Math.max(1, Math.round(KPI[i].target / 40)));
    }
  }

  /* ── reveal при скролле ── */
  var reveals = document.querySelectorAll(".reveal");
  var io = ("IntersectionObserver" in window) ? new IntersectionObserver(function (entries) {
    for (var i = 0; i < entries.length; i++) {
      if (entries[i].isIntersecting) {
        entries[i].target.classList.add("in");
        io.unobserve(entries[i].target);
        if (entries[i].target.classList.contains("hero-stage")) { startKpis(); }
      }
    }
  }, { threshold: 0.2 }) : null;

  if (io) {
    for (var r = 0; r < reveals.length; r++) { io.observe(reveals[r]); }
  } else {
    for (var r2 = 0; r2 < reveals.length; r2++) { reveals[r2].classList.add("in"); }
    startKpis();
  }

  /* ── тема ── */
  var themeBtn = document.getElementById("themeToggle");
  var savedTheme = null;
  try { savedTheme = localStorage.getItem("suotTheme"); } catch (e) { savedTheme = null; }
  if (savedTheme === "light") { document.body.setAttribute("data-theme", "light"); }

  themeBtn.addEventListener("click", function () {
    var cur = document.body.getAttribute("data-theme") === "light" ? "dark" : "light";
    document.body.setAttribute("data-theme", cur);
    try { localStorage.setItem("suotTheme", cur); } catch (e) { /* нет хранилища */ }
  });

  var siteLangState = "ru";
  function siteLang() { return siteLangState; }
  function T(ru, en) { return siteLangState === "en" ? en : ru; }

  /* ── данные сборки: версия, размеры, хэши, история (downloads/index.json) ── */
  function fmtSize(mb) {
    return mb ? ("· " + (String(mb).replace(".", ",")) + "&nbsp;" + T("МБ", "MB")) : "";
  }
  var lastDlData = null;
  function paintDownloads(data) {
    lastDlData = data;
    var ver = data.version || "2.3.0";
      var hEl = document.getElementById("heroVer");
      if (hEl) { hEl.textContent = ver; }
      var padV = document.getElementById("siteReady");
      if (padV) { padV.textContent = "v" + ver; }
      var rel = data.releases || [];
      var zip = null, setup = null;
      for (var i = 0; i < rel.length; i++) {
        if (rel[i].file.indexOf("portable") !== -1) { zip = rel[i]; }
        if (rel[i].file.indexOf("setup") !== -1) { setup = rel[i]; }
      }
      if (zip) {
        var zs = document.getElementById("dlZipSize");
        var ps = document.getElementById("dlSize");
        var zh = document.getElementById("dlHashZip");
        if (zs) { zs.innerHTML = fmtSize(zip.size_mb); }
        if (ps) { ps.innerHTML = fmtSize(zip.size_mb); }
        if (zh) {
          zh.innerHTML = "SHA-256: <code>" + zip.sha256 + "</code>";
          zh.title = zip.sha256;
        }
      }
      if (setup) {
        var se = document.getElementById("dlSetup");
        var sn = document.getElementById("dlSetupNote");
        var ss = document.getElementById("dlSetupSize");
        if (se) { se.style.display = "inline-flex"; }
        if (sn) { sn.innerHTML = T("Мастер установки, ярлыки, удаление через «Программы и компоненты».",
          "Setup wizard, shortcuts, uninstall via “Programs and Features”."); }
        if (ss) { ss.innerHTML = fmtSize(setup.size_mb); }
      }
      var body = document.getElementById("verBody");
      if (body) {
        var hh = data.history || [];
        if (hh.length === 0) {
          body.innerHTML = "<tr><td colspan='4' class='muted-p'>" +
            T("История пуста", "No history") + "</td></tr>";
        } else {
          var rows = "";
          for (var k = 0; k < hh.length; k++) {
            rows += "<tr><td>" + (hh[k].version || "") + "</td><td>" +
              (hh[k].date || "") + "</td><td>" + (hh[k].file || "") + "</td><td>" +
              (hh[k].size_mb ? hh[k].size_mb : "") + " " + T("МБ", "MB") + "</td></tr>";
          }
          body.innerHTML = rows;
        }
      }
  }

  fetch("downloads/index.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .then(paintDownloads)
    .catch(function () {
      var zh = document.getElementById("dlHashZip");
      if (zh) { zh.textContent = T("SHA-256 недоступен офлайн", "SHA-256 unavailable offline"); }
    });

  /* ── карусель скриншотов ── */
  (function () {
    var root = document.querySelector("[data-carousel]");
    if (!root) { return; }
    var room = document.getElementById("carRoom");
    var prev = root.querySelector("[data-car-prev]");
    var next = root.querySelector("[data-car-next]");
    var dotsWrap = root.querySelector("[data-car-dots]");
    var slides = Array.prototype.slice.call(root.querySelectorAll("[data-slide]"));
    if (slides.length === 0) { return; }
    var idx = 0;
    var dots = [];

    function paint() {
      room.style.transform = "translateX(-" + (idx * 100) + "%)";
      for (var i = 0; i < dots.length; i++) {
        dots[i].className = "car-dot" + (i === idx ? " on" : "");
      }
    }

    function go(n) {
      idx = (n + slides.length) % slides.length;
      paint();
    }

    for (var s = 0; s < slides.length; s++) {
      (function (si) {
        var d = document.createElement("button");
        d.className = "car-dot";
        d.setAttribute("aria-label", T("Скриншот ", "Screenshot ") + (si + 1));
        d.addEventListener("click", function () { go(si); });
        dotsWrap.appendChild(d);
        dots.push(d);
      })(s);
    }
    prev.addEventListener("click", function () { go(idx - 1); });
    next.addEventListener("click", function () { go(idx + 1); });
    paint();
  })();

  /* ── командная палитра (Ctrl+K) ── */
  var COMMANDS = [
    { label: "Скачать программу", label_en: "Download the app", g: "Ctrl+N", cat: "Загрузка", cat_en: "Download", href: "#download" },
    { label: "Скриншоты интерфейса", label_en: "Interface screenshots", g: "Ctrl+S", cat: "Навигация", cat_en: "Navigate", href: "#screens" },
    { label: "Возможности программы", label_en: "Program features", g: "Ctrl+F", cat: "Навигация", cat_en: "Navigate", href: "#features" },
    { label: "Краткий гайд", label_en: "Quick guide", g: "Ctrl+G", cat: "Навигация", cat_en: "Navigate", href: "#guide" },
    { label: "Поддержка", label_en: "Support", g: "Ctrl+H", cat: "Навигация", cat_en: "Navigate", href: "#support" },
    { label: "Живое демо-окно", label_en: "Live demo window", g: "Ctrl+D", cat: "Навигация", cat_en: "Navigate", href: "#demo" },
    { label: "Палитра команд — как в приложении", label_en: "Command palette — like in the app", g: "Ctrl+K", cat: "Фишка", cat_en: "Highlight", href: "#palette" }
  ];
  function cmdLabel(c) { return siteLang() === "en" ? (c.label_en || c.label) : c.label; }
  function cmdCat(c) { return siteLang() === "en" ? (c.cat_en || c.cat) : c.cat; }

  var overlay = document.getElementById("cmdOverlay");
  var cmdInput = document.getElementById("cmdInput");
  var cmdList = document.getElementById("cmdList");
  var paletteInput = document.getElementById("paletteSearch");
  var paletteResults = document.getElementById("paletteResults");
  var selIdx = -1;
  var resultCache = [];

  function scrollToHref(href) {
    var el = document.querySelector(href);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); }
  }

  function renderList(items, container, kind) {
    container.innerHTML = "";
    if (items.length === 0) {
      var empty = document.createElement("div");
      empty.className = "cmd-empty";
      empty.textContent = T("Ничего не найдено — попробуйте «Скачать» или «Календарь»",
        "Nothing found — try “Download” or “Calendar”");
      container.appendChild(empty);
      return;
    }
    selIdx = 0;
    for (var i = 0; i < items.length; i++) {
      (function (idx) {
        var it = document.createElement("div");
        it.className = "cmd-item" + (idx === 0 ? " sel" : "");
        it.innerHTML = "<span>" + cmdLabel(items[idx]) + "</span><span class='cat'>" +
          cmdCat(items[idx]) + "</span>";
        it.addEventListener("click", function () {
          scrollToHref(items[idx].href);
          closeCmd();
        });
        container.appendChild(it);
      })(i);
    }
    syncSel(kind);
  }

  function filterItems(q) {
    var out = [];
    var need = q ? q.toLowerCase() : "";
    for (var i = 0; i < COMMANDS.length; i++) {
      var c = COMMANDS[i];
      var hay = (c.label + " " + (c.label_en || "") + " " + c.cat + " " +
        (c.cat_en || "")).toLowerCase();
      if (!need || hay.indexOf(need) !== -1) {
        out.push(c);
      }
    }
    return out;
  }

  function syncSel(kind) {
    var items = (kind === "palette") ? paletteResults.querySelectorAll(".pp-item") :
      cmdList.querySelectorAll(".cmd-item");
    for (var i = 0; i < items.length; i++) {
      items[i].className = items[i].className.replace(" sel", "") +
        (i === selIdx ? " sel" : "");
    }
  }

  function moveSel(d, kind) {
    var items = (kind === "palette") ? paletteResults.querySelectorAll(".pp-item") :
      cmdList.querySelectorAll(".cmd-item");
    if (items.length === 0) { return; }
    selIdx += d;
    if (selIdx < 0) { selIdx = 0; }
    if (selIdx > items.length - 1) { selIdx = items.length - 1; }
    syncSel(kind);
    var cur = items[selIdx];
    if (cur && cur.scrollIntoView) { cur.scrollIntoView({ block: "nearest" }); }
  }

  function openCmd() {
    overlay.hidden = false;
    cmdInput.value = "";
    resultCache = COMMANDS;
    renderList(resultCache, cmdList, "cmd");
    setTimeout(function () { cmdInput.focus(); }, 10);
  }

  function closeCmd() {
    if (!overlay.hidden) { overlay.hidden = true; }
  }

  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K" || e.key === "л" || e.key === "Л")) {
      e.preventDefault();
      if (overlay.hidden) { openCmd(); } else { closeCmd(); }
      return;
    }
    if (!overlay.hidden) {
      if (e.key === "Escape") { e.preventDefault(); closeCmd(); }
      if (e.key === "ArrowDown") { e.preventDefault(); moveSel(1, "cmd"); }
      if (e.key === "ArrowUp") { e.preventDefault(); moveSel(-1, "cmd"); }
      if (e.key === "Enter") {
        e.preventDefault();
        var items = cmdList.querySelectorAll(".cmd-item");
        if (items[selIdx] && items[selIdx].click) { items[selIdx].click(); }
      }
    }
    if (e.key === "Escape") { closeCmd(); }
  });

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) { closeCmd(); }
  });

  cmdInput.addEventListener("input", function () {
    resultCache = filterItems(cmdInput.value);
    renderList(resultCache, cmdList, "cmd");
  });

  cmdList.addEventListener("mouseover", function (e) {
    var item = e.target.closest ? e.target.closest(".cmd-item") : null;
    if (!item) { return; }
    var items = cmdList.querySelectorAll(".cmd-item");
    for (var i = 0; i < items.length; i++) {
      if (items[i] === item) { selIdx = i; syncSel("cmd"); break; }
    }
  });

  /* ── врезка палитры-демо в секции ── */
  function renderPalettePreview(q) {
    var items = filterItems(q);
    paletteResults.innerHTML = "";
    if (items.length === 0) {
      var h = document.createElement("div");
      h.className = "pp-hint";
      h.textContent = T("Ничего не найдено — попробуйте «календарь» или «скачать»",
        "Nothing found — try “calendar” or “download”");
      paletteResults.appendChild(h);
      return;
    }
    selIdx = 0;
    for (var i = 0; i < items.length; i++) {
      (function (idx) {
        var it = document.createElement("div");
        it.className = "pp-item" + (idx === 0 ? " sel" : "");
        var g = items[idx].g || "";
        it.innerHTML = "<span>" + cmdLabel(items[idx]) + "</span>" +
          (g ? "<span class='g'>" + g + "</span>" : "");
        it.addEventListener("click", function () { scrollToHref(items[idx].href); });
        paletteResults.appendChild(it);
      })(i);
    }
    syncSel("palette");
  }

  if (paletteInput && paletteResults) {
    paletteInput.addEventListener("input", function () {
      renderPalettePreview(paletteInput.value);
    });
    paletteResults.addEventListener("mouseover", function (e) {
      var item = e.target.closest ? e.target.closest(".pp-item") : null;
      if (!item) { return; }
      var items = paletteResults.querySelectorAll(".pp-item");
      for (var i = 0; i < items.length; i++) {
        if (items[i] === item) { selIdx = i; syncSel("palette"); break; }
      }
    });
    renderPalettePreview("");
  }

  /* полезные числки в подписи малыми буквами */
  var pad = document.createElement("div");
  pad.id = "siteReady";
  pad.hidden = true;
  pad.textContent = "v2.3.0";
  document.body.appendChild(pad);

  /* ── RU/EN переключатель: data-en хранит английский текст ── */
  paintIcons();
  var langBtn = document.getElementById("langToggle");
  var curLang = "ru";
  function applyLang(l) {
    curLang = l;
    siteLangState = l;
    var els = document.querySelectorAll("[data-en]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (!el.getAttribute("data-ru")) {
        el.setAttribute("data-ru", el.innerHTML);
      }
      var ph = el.getAttribute("data-en-ph");
      if (ph) {
        if (!el.getAttribute("data-ru-ph")) {
          el.setAttribute("data-ru-ph", el.getAttribute("placeholder") || "");
        }
        el.setAttribute("placeholder", l === "en" ? ph : el.getAttribute("data-ru-ph"));
        continue;
      }
      el.innerHTML = l === "en" ? el.getAttribute("data-en") : el.getAttribute("data-ru");
    }
    document.documentElement.lang = l;
    if (langBtn) {
      langBtn.textContent = l === "en" ? "RU" : "EN";
      langBtn.classList.toggle("on", l === "en");
    }
    try { localStorage.setItem("suot_site_lang", l); } catch (_) {}
    // перерисовка динамического: календарь, палитры, загрузки, точки карусели
    DW = l === "en" ? DW_EN : DW_RU;
    MONTH = l === "en" ? MONTH_EN : MONTH_RU;
    try { renderCal(); } catch (_) {}
    try {
      if (paletteInput && paletteResults) {
        renderPalettePreview(paletteInput.value || "");
      }
    } catch (_) {}
    try { if (lastDlData) { paintDownloads(lastDlData); } } catch (_) {}
    try {
      var dots = document.querySelectorAll(".car-dot");
      for (var di = 0; di < dots.length; di++) {
        dots[di].setAttribute("aria-label", T("Скриншот ", "Screenshot ") + (di + 1));
      }
    } catch (_) {}
  }
  try {
    if (localStorage.getItem("suot_site_lang") === "en") { applyLang("en"); }
  } catch (_) {}
  if (langBtn) {
    langBtn.addEventListener("click", function () {
      applyLang(curLang === "en" ? "ru" : "en");
    });
  }
})();