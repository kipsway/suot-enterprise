/* ═══ ОхранаТруда Про — сайт-лендинг: JS (esprima-safe, без ?. / ??) ═══ */

(function () {
  "use strict";

  var DW = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  var MONTH = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
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

  /* ── данные сборки: версия, размеры, хэши, история (downloads/index.json) ── */
  function fmtSize(mb) {
    return mb ? ("· " + (String(mb).replace(".", ",")) + "&nbsp;МБ") : "";
  }

  fetch("downloads/index.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var ver = data.version || "2.2.1";
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
        if (sn) { sn.innerHTML = "Мастер установки, ярлыки, удаление через «Программы и компоненты»."; }
        if (ss) { ss.innerHTML = fmtSize(setup.size_mb); }
      }
      var body = document.getElementById("verBody");
      if (body) {
        var hh = data.history || [];
        if (hh.length === 0) {
          body.innerHTML = "<tr><td colspan='4' class='muted-p'>История пуста</td></tr>";
        } else {
          var rows = "";
          for (var k = 0; k < hh.length; k++) {
            rows += "<tr><td>" + (hh[k].version || "") + "</td><td>" +
              (hh[k].date || "") + "</td><td>" + (hh[k].file || "") + "</td><td>" +
              (hh[k].size_mb ? hh[k].size_mb : "") + " МБ</td></tr>";
          }
          body.innerHTML = rows;
        }
      }
    })
    .catch(function () {
      var zh = document.getElementById("dlHashZip");
      if (zh) { zh.textContent = "SHA-256 недоступен офлайн"; }
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
        d.setAttribute("aria-label", "Скриншот " + (si + 1));
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
    { label: "Скачать программу", g: "Ctrl+N", cat: "Загрузка", href: "#download" },
    { label: "Скриншоты интерфейса", g: "Ctrl+S", cat: "Навигация", href: "#screens" },
    { label: "Возможности программы", g: "Ctrl+F", cat: "Навигация", href: "#features" },
    { label: "Краткий гайд", g: "Ctrl+G", cat: "Навигация", href: "#guide" },
    { label: "Поддержка", g: "Ctrl+H", cat: "Навигация", href: "#support" },
    { label: "Живое демо-окно", g: "Ctrl+D", cat: "Навигация", href: "#demo" },
    { label: "Палитра команд — как в приложении", g: "Ctrl+K", cat: "Фишка", href: "#palette" }
  ];

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
      empty.textContent = "Ничего не найдено — попробуйте «Скачать» или «Календарь»";
      container.appendChild(empty);
      return;
    }
    selIdx = 0;
    for (var i = 0; i < items.length; i++) {
      (function (idx) {
        var it = document.createElement("div");
        it.className = "cmd-item" + (idx === 0 ? " sel" : "");
        it.innerHTML = "<span>" + items[idx].label + "</span><span class='cat'>" +
          items[idx].cat + "</span>";
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
      if (!need || c.label.toLowerCase().indexOf(need) !== -1 ||
          c.cat.toLowerCase().indexOf(need) !== -1) {
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
      h.textContent = "Ничего не найдено — попробуйте «календарь» или «скачать»";
      paletteResults.appendChild(h);
      return;
    }
    selIdx = 0;
    for (var i = 0; i < items.length; i++) {
      (function (idx) {
        var it = document.createElement("div");
        it.className = "pp-item" + (idx === 0 ? " sel" : "");
        var g = items[idx].g || "";
        it.innerHTML = "<span>" + items[idx].label + "</span>" +
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
  pad.textContent = "v2.2.1";
  document.body.appendChild(pad);
})();