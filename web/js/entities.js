/* SUOT Next — Entity Registry (Блок 2).
   Декларативные дескрипторы сущностей поверх существующих REST-контрактов.
   JSON-таблицы: полный detail (поля + заметки + связи + история/rollback).
   Custom-таблицы (u_*): только поля (notes/links/history API их не покрывает).
   Structured (capa/protocols/...) и tasks: detail 'none' — отдельные эндпоинты
   записей отсутствуют; заведено как follow-up, НЕ заглушка. */
(function () {
  "use strict";

  const JSON_ENTITIES = [
    { key: "employees", icon: "users",
      ru: "Сотрудник", en: "Employee",
      titleCandidates: ["ФИО", "full_name", "name", "Название"] },
    { key: "violations", icon: "alert",
      ru: "Нарушение", en: "Violation",
      titleCandidates: ["Описание", "Название", "title", "name"] },
    { key: "incidents", icon: "inbox",
      ru: "Происшествие", en: "Incident",
      titleCandidates: ["Описание", "Название", "title", "name"] },
    { key: "ppe", icon: "hardhat",
      ru: "СИЗ", en: "PPE item",
      titleCandidates: ["Наименование", "Название", "name", "title"] },
    { key: "ppe_inspections", icon: "clipboard",
      ru: "Осмотр СИЗ", en: "PPE inspection",
      titleCandidates: ["Наименование", "Название", "name", "title"] },
    { key: "training", icon: "checkAll",
      ru: "Обучение", en: "Training",
      titleCandidates: ["Программа", "Название", "name", "title"] },
    { key: "permits", icon: "command",
      ru: "Допуск", en: "Permit",
      titleCandidates: ["Название", "Номер", "name", "title"] },
    { key: "work_orders", icon: "refresh",
      ru: "Наряд", en: "Work order",
      titleCandidates: ["Название", "Номер", "name", "title"] },
    { key: "companies", icon: "home",
      ru: "Компания", en: "Company",
      titleCandidates: ["Фирма", "Название", "name", "short_name"] },
    { key: "custom_ledger", icon: "database",
      ru: "Запись учёта", en: "Ledger entry",
      titleCandidates: ["Название", "name", "title"] },
  ];

  function lang() {
    try { return (window.I18N && I18N.lang) || "ru"; }
    catch (_) { return "ru"; }
  }

  function descriptor(tableOrKey) {
    if (!tableOrKey) return null;
    const k = String(tableOrKey);
    const found = JSON_ENTITIES.find((e) => e.key === k);
    if (found) {
      return { kind: "json", key: k, icon: found.icon,
        ru: found.ru, en: found.en,
        titleCandidates: found.titleCandidates.slice(),
        notes: true, links: true, history: true };
    }
    if (k.startsWith("u_")) {
      return { kind: "custom", key: k, icon: "database",
        ru: "Запись", en: "Record", titleCandidates: [],
        notes: false, links: false, history: false };
    }
    /* Structured и прочие: дескриптор-заглушка с явным флагом,
       чтобы UI честно прятал недоступные вкладки. */
    return { kind: "none", key: k, icon: "layers",
      ru: "Запись", en: "Record", titleCandidates: [],
      notes: false, links: false, history: false };
  }

  function labelOf(desc, L) {
    if (!desc) return "";
    const langNow = L || lang();
    return langNow === "en" ? (desc.en || desc.ru) : (desc.ru || desc.en);
  }

  function titleOf(desc, data) {
    const dj = (data && data.data) || data || {};
    for (const c of (desc && desc.titleCandidates) || []) {
      const v = dj[c];
      if (v !== undefined && v !== null && String(v).trim() !== "") {
        return String(v).trim();
      }
    }
    for (const k of Object.keys(dj)) {
      if (k.startsWith("_")) continue;
      const v = dj[k];
      if (typeof v === "string" && v.trim() !== "") return v.trim();
    }
    return "";
  }

  function fieldEntries(data) {
    const dj = (data && data.data) || data || {};
    return Object.keys(dj)
      .filter((k) => !k.startsWith("_"))
      .map((k) => ({ name: k, value: dj[k] }));
  }

  function recordUrl(desc, rid) {
    if (!desc || !rid) return "";
    if (desc.kind === "json") return "/data/" + desc.key + "/" + rid;
    if (desc.kind === "custom") return "/custom/record/" + desc.key + "/" + rid;
    return "";
  }

  window.SUOT_ENTITIES = {
    JSON_KEYS: JSON_ENTITIES.map((e) => e.key),
    descriptor, labelOf, titleOf, fieldEntries, recordUrl, lang,
  };
})();
