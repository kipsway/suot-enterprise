/* SUOT Neo — инлайн SVG-иконки (стиль Lucide, stroke 1.8) */
(function () {
  function svg(inner, vb = "0 0 24 24") {
    return `<svg viewBox="${vb}" fill="none" stroke="currentColor" ` +
           `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">` +
           inner + `</svg>`;
  }
  const S = (d) => `<path d="${d}"/>`;

  window.ICONS = {
    logo: svg(
      `<path d="M12 2 L20 6 V11 C20 16.5 16.6 20.4 12 22 C7.4 20.4 4 16.5 4 11 V6 Z"/>` +
      `<path d="M9 12 L11.2 14.2 L15.5 9.5" stroke-width="2"/>`),
    home: svg(S("M3 10.5 12 3l9 7.5") + S("M5 9.5V21h14V9.5")),
    dashboard: svg(
      `<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/>` +
      `<rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/>` +
      `<rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/>` +
      `<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>`),
    users: svg(
      S("M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2") +
      `<circle cx="9.5" cy="7" r="4"/>` +
      S("M22 21v-2a4 4 0 0 0-3-3.87") + S("M15.5 3.13a4 4 0 0 1 0 7.75")),
    alert: svg(
      S("M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z") +
      S("M12 9v4") + S("M12 17h.01")),
    hardhat: svg(
      S("M2 18a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1z") +
      S("M4 15v-3a8 8 0 0 1 16 0v3") + S("M10 4V2.5A1.5 1.5 0 0 1 11.5 1h1A1.5 1.5 0 0 1 14 2.5V4")),
    clipboard: svg(
      `<rect x="5" y="4" width="14" height="18" rx="2"/>` +
      S("M9 4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1H9z") +
      S("M9 11l1.7 1.7L15 9") + S("M9 16.5h6")),
    calendar: svg(
      `<rect x="3" y="5" width="18" height="16" rx="2"/>` +
      S("M16 3v4M8 3v4M3 10h18")),
    chart: svg(
      S("M3 3v18h18") + S("M8 17V9") + S("M13 17V5") + S("M18 17v-7")),
    settings: svg(
      `<circle cx="12" cy="12" r="3"/>` +
      S("M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z")),
    search: svg(`<circle cx="11" cy="11" r="7"/>` + S("m21 21-4.3-4.3")),
    plus: svg(S("M12 5v14M5 12h14"), "0 0 24 24"),
    logout: svg(
      S("M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4") +
      S("M16 17l5-5-5-5") + S("M21 12H9")),
    sun: svg(
      `<circle cx="12" cy="12" r="4"/>` +
      S("M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4")),
    moon: svg(S("M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z")),
    chevronUp: svg(`<polyline points="18 15 12 9 6 15"/>`),
    chevronDown: svg(`<polyline points="6 9 12 15 18 9"/>`),
    filter: svg(S("M22 3H2l8 9.5V19l4 2v-8.5z")),
    pencil: svg(
      S("M17 3a2.83 2.83 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5z")),
    trash: svg(
      `<polyline points="3 6 5 6 21 6"/>` +
      S("M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2") +
      S("M10 11v6M14 11v6")),
    download: svg(
      S("M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4") +
      S("m7 10 5 5 5-5") + S("M12 15V3")),
    database: svg(
      `<ellipse cx="12" cy="5" rx="9" ry="3"/>` +
      S("M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5") +
      S("M3 12c0 1.66 4 3 9 3s9-1.34 9-3")),
    eye: svg(
      S("M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z") +
      `<circle cx="12" cy="12" r="3"/>`),
    eyeOff: svg(
      S("M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94") +
      S("M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19") +
      S("M14.12 14.12a3 3 0 1 1-4.24-4.24") + S("M1 1l22 22")),
    command: svg(
      S("M18 3a3 3 0 0 0-3 3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 0 0-3-3z")),
    refresh: svg(
      S("M23 4v6h-6") + S("M20.49 15a9 9 0 1 1-2.13-9.36L23 10")),
    inbox: svg(
      `<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>` +
      S("M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z")),
    checkAll: svg(`<polyline points="9 11 12 14 22 4"/>` +
                  `<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>`),
    image: svg(
      `<rect x="3" y="3" width="18" height="18" rx="2"/>` +
      `<circle cx="8.5" cy="8.5" r="1.5"/>` +
      `<polyline points="21 15 16 10 5 21"/>`),
    upload: svg(
      S("M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4") +
      S("m17 8-5-5-5 5") + S("M12 3v12")),
    bookmark: svg(S("M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z")),
    fileText: svg(
      S("M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z") +
      `<polyline points="14 2 14 8 20 8"/>` +
      S("M16 13H8M16 17H8M10 9H8")),
    linkIc: svg(
      S("M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71") +
      S("M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71")),
    clock: svg(`<circle cx="12" cy="12" r="10"/>` +
               `<polyline points="12 6 12 12 16 14"/>`),
    rows: svg(
      `<rect x="3" y="4" width="18" height="5" rx="1"/>` +
      `<rect x="3" y="12" width="18" height="8" rx="1"/>`),
    layers: svg(
      `<polygon points="12 2 2 7 12 12 22 7 12 2"/>` +
      `<polyline points="2 17 12 22 22 17"/>` +
      `<polyline points="2 12 12 17 22 12"/>`),
    copyIc: svg(
      `<rect x="9" y="9" width="13" height="13" rx="2"/>` +
      S("M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1")),
    undoIc: svg(
      `<polyline points="1 4 1 10 7 10"/>` +
      S("M3.51 15a9 9 0 1 0 2.13-9.36L1 10")),
    tagIc: svg(
      S("M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z") +
      `<line x1="7" y1="7" x2="7.01" y2="7"/>`),
    star: svg(
      `<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>`),
    external: svg(
      S("M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6") +
      S("M15 3h6v6") + S("M10 14 21 3")),
    tools: svg(
      `<path d="M14.7 6.3a4.5 4.5 0 0 0 5.4 5.4L22 13.4V14a8 8 0 0 1-12 7l-5.7 2.1a1 1 0 0 1-1.3-1.3L5 16.4a8 8 0 0 1 7-11.6h.6l1.7 1.5z"/>`),
    pin: svg(S("M12 17v5") + S("M9 10.8V5a3 3 0 0 1 6 0v5.8l2 2V14H7v-1.2z") +
             S("M5 14h14")),
    pulse: svg(
      S("M22 12h-4l-3 9L9 3l-3 9H2")),
    grid: svg(
      `<rect x="3" y="3" width="7.5" height="7.5" rx="1.2"/>` +
      `<rect x="13.5" y="3" width="7.5" height="7.5" rx="1.2"/>` +
      `<rect x="3" y="13.5" width="7.5" height="7.5" rx="1.2"/>` +
      `<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.2"/>`),
    blocks: svg(
      `<rect x="3" y="9" width="6" height="6" rx="1"/>` +
      `<rect x="9" y="3" width="6" height="6" rx="1"/>` +
      `<rect x="15" y="9" width="6" height="6" rx="1"/>` +
      `<rect x="9" y="15" width="6" height="6" rx="1"/>`),
  };
})();
