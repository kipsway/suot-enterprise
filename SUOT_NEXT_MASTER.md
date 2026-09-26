# SUOT NEXT — ПОДРОБНЫЙ MASTER-ДОКУМЕНТ ПРОЕКТА

## 1. Идентификация проекта

- Название: **SUOT Next / ОхранаТруда Про / SUOT Enterprise**.
- Назначение: локальная Windows-система управления охраной труда для специалиста, ответственного за СИЗ, обучение, проверки, документы, риски и мероприятия.
- Рабочая папка: `C:\Users\ДДД\Desktop\программа`.
- Git: `https://github.com/kipsway/suot-enterprise.git`.
- Текущая ветка: `cline/76b06`.
- Сайт: `https://kipsway.github.io/suot-enterprise/`.
- Языки: русский и английский.
- Режим: локальный, без обязательного облака.

## 2. Главная цель владельца

Создать не редизайн старого интерфейса, а новую систему уровня крупных продуктов: новая архитектура, навигация, workspace-first интерфейс, дизайн-система, сценарии, backend services, задачи, workflow и публичный сайт. Сохранить все данные, права, изоляцию, RU/EN, Windows/WebView2 и локальную работу.

Требование «более 100 000 новых строк» является долгосрочной целью. Искусственные пустые файлы и бессмысленное раздувание запрещены: строки должны поддерживать реальную функцию, контракт, тест, документацию или миграцию.

## 3. Все пожелания владельца

1. Полностью новую программу, а не cosmetic redesign.
2. Новый дизайн программы и сайта.
3. Новый интерфейс, функции, концепции и сценарии.
4. Разрешено убрать или переработать browser-like tabs.
5. Перейти к постоянным workspaces, views и contexts.
6. Сохранить все данные, RBAC, изоляцию, RU/EN и WebView2.
7. Создать server-side filters по всей таблице.
8. Создать настоящие массовые операции: progress, cancel, retry, partial completion, history.
9. Не имитировать undo/redo.
10. Создать Task Center, Command Bus, keyboard-first navigation.
11. Создать универсальный Detail Workspace и Documents Center.
12. Сделать WCAG, performance, accessibility.
13. Создать server-side Saved Views и workspace presets.
14. Сделать plugin/capability contract v2.
15. Работать крупными завершёнными блоками и запускать проверки.
16. Провести полную регрессию перед релизом.
17. Сайт должен отражать реальные функции программы.

## 4. Текущая архитектура

```text
Windows
  → desktop.py
  → local uvicorn
  → FastAPI server/app.py
  → server/routers/*
  → services/database.py
  → SQLite
  → web SPA (Alpine.js)
```

`desktop.py` — production desktop entry point. `main.py` и `suot_platform.py` относятся к старому Qt/legacy слою и не должны определять новую web-архитектуру.

Frontend пока SPA без сборщика: `web/index.html`, `web/js/*.js`, `web/css/*.css`, Alpine vendor. Backend composition root: `server/app.py`. Data layer: `services/database.py`.

## 5. Ключевые файлы

### Root

- `desktop.py` — desktop startup, server, WebView2.
- `main.py` — старый Qt entry.
- `suot_platform.py` — legacy PyQt5 монолит.
- `PROJECT_HANDOVER.md` — старый handover.
- `PROJECT_REBUILD_SUMMARY.md` — краткий rebuild plan.
- `SUOT_NEXT_ALL_REQUESTS_AND_STATUS.md` — сводка запросов.
- `SUOT_NEXT_HANDOFF_PROMPT.md` — передаточный prompt.
- `SUOT_NEXT_MASTER.md` — этот документ.

### Server

- `server/app.py` — FastAPI composition root/lifespan.
- `server/deps.py` — DB/current-user dependencies.
- `server/tokens.py` — token issue/verify.
- `server/routers/auth.py` — auth/session/language.
- `server/routers/data.py` — universal JSON CRUD.
- `server/routers/custom.py` — custom tables/records.
- `server/routers/structured.py` — checklists, CAPA, protocols, risks, textbook.
- `server/routers/jobs.py` — bulk jobs/history/retry/cancel.
- `server/routers/dashboard.py` — KPI/tasks/activity/calendar.
- `server/routers/records.py` — notes/links/history/rollback.
- `server/routers/import_api.py`, `export_api.py` — import/export.
- `server/routers/print_api.py`, `print_pdf.py` — print/PDF.
- `server/routers/search_reports.py` — search/reports.
- `server/routers/ai_api.py` — AI chat/insights/agent/threads.
- `server/routers/backup_api.py`, `settings_api.py`, `plugins_api.py` — system functions.
- `server/routers/union_api.py` — all-record registry.
- `server/routers/calendar_api.py`, `reminders_api.py`, `npa_api.py`, `diag.py` — supporting modules.

### Frontend

- `web/js/app.js` — root Alpine app/auth/startup/fatal/health.

## 6. Реализованные изменения

### UX и onboarding

- новый первый экран и Industrial Signal;
- RU/EN language gate;
- split-screen authorization;
- onboarding scenarios `today`, `inspection`, `documents`;
- сохранение `onboarding_scenario` в settings;
- новый hero рабочего стола;
- Focus Day;
- Readiness Center;
- quick actions;
- workspace presets;
- loading/empty/error/smart-alert states;
- command palette с группами;
- защита command palette от гонок поиска;
- Saved Views;
- sticky headers и горизонтальная прокрутка таблиц;
- угловая ячейка sticky header;
- focus-trap, autofocus, Escape;
- maximized desktop window;
- table error-state и Retry.

### Таблицы

- server-side query/search/sort/filter/page;
- `f_<column>` filters;
- `smart_filter=overdue|active|done`;
- client selection Set, сохраняемый при reload;
- bulk edit/delete/transfer;
- custom user columns;
- hidden columns;
- column order/drag;
- computed columns;
- comments;
- group display;
- card/table mode;
- history/notes/links/rollback;
- localSaved Views и presets;
- bulk progress/history UI.

### Bulk backend

`server/routers/jobs.py` реализует:

- `POST /api/jobs/bulk`;
- `GET /api/jobs/{job_id}`;
- `POST /api/jobs/{job_id}/retry`;
- `POST /api/jobs/{job_id}/cancel`;
- `GET /api/jobs/history`;
- `GET /api/jobs/export.csv`.

Поддерживаются `delete`, `edit`, `custom_delete`, `custom_edit`. SQLite `bulk_jobs` хранит ID, user, status, progress, result, error, timestamps и `processed_ids_json`. Retry обрабатывает только оставшиеся ID.

### Structured redesign

Обновлены рабочие пространства checklists, CAPA, protocols и risks: sticky toolbar, list/detail layout, card hierarchy, responsive behavior, chain modal и fill states.

### Public website

Добавлены Industrial Signal, hero proof, scenarios, final CTA, adaptive cards. Сохранены downloads manifest, SHA-256, screenshots, demo, carousel, theme, reduced motion and command palette.

## 7. Целевая архитектура SUOT Next Core v3

### Frontend

1. Shell — app frame, responsive layout, theme, accessibility.
2. Navigation Registry — routes/views/groups/aliases/capabilities.
3. Workspace Engine — layouts/widgets/drag-drop/saved state.
4. Command Bus — commands, shortcuts, palette, context actions.
5. Entity Registry — employees/PPE/risks/incidents/documents/tasks.
6. Data Plane — cache, abort, race protection, optimistic state.
7. View Components — dashboard/table/detail/forms/timeline/reports.
8. Design System — tokens/components/motion/accessibility.
9. Migration Adapter — old tabs/API contracts.

### Backend

## 8. Детальный план крупных блоков

### Блок 1 — Navigation Registry + Workspace Shell

- declarative registry вместо ручного списка;
- capability/role checks;
- route aliases;
- pinned/recent navigation;
- keyboard navigation;
- responsive rail/sidebar;
- compatibility adapter для legacy tabs;
- E2E навигации и keyboard.

### Блок 2 — Entity Registry + Detail Workspace

- единый registry сущностей;
- generic detail view;
- context-aware route;
- related records;
- notes/history/attachments;
- entity actions;
- universal create/edit/preview;
- server capability metadata.

### Блок 3 — Command Bus

- command id/capability/shortcut/handler;
- command palette integration;
- command groups и search;
- context commands;
- bulk commands;
- permission-aware execution;
- error boundary/telemetry.

### Блок 4 — Task Center

- все jobs в одном UI;
- progress/latency/result/error;
- cancel/retry;
- partial completion;
- audit/event timeline;
- server persistence/recovery;
- task history export.

### Блок 5 — Query Engine и Saved Views

- server-side filters для всей таблицы;
- stable pagination;
- cursor pagination where needed;
- saved views server-side;
- workspace presets server-side;
- import/export definitions;
- query validation/capability constraints.

### Блок 6 — Dashboard v4

- scenario workspaces;
- readiness;
- focus day;
- action queue;
- activity stream;
- calendar;
- widget layout editor;
- drill-down to source records.

### Блок 7 — Documents Center

- templates;
- protocols/checklists;
- reports;
- print jobs;
- batch print;
- PDF preview;
- document lifecycle and versions.

### Блок 8 — Plugin/Capability v2

- manifest schema;
- permissions/capabilities;
- backend-safe plugin boundary;
- UI extension points;
- plugin settings;
- version/migration checks.

### Блок 9 — Миграция старого UI

- workspace-first shell default;
- legacy tab route adapter;
- incremental view migration;
- deprecations;
- E2E compatibility;
- remove obsolete code only after replacement.

### Блок 10 — Final quality

- accessibility audit;
- performance profiling;
- security regression;
- RU/EN;
- packaging;
- installer/portable;
- full test suite;
- release notes.

## 9. Риски и ограничения

- Старые Alpine DOM contracts используются во многих модулях.
- Старый tab store вызывается из palette, reports, AI, reminders, setup и других views.
- `bulk_jobs` recovery сейчас выполняется в процессе приложения и должен быть проверен на длительных задачах.
- Background worker ограничен двумя threads; при росте нагрузки нужен отдельный worker service.
- Saved Views и workspace presets пока локальные и должны мигрировать на server.
- `smart_filter` пока реализован для основных status/date semantics; сложные domain rules требуется вынести в Query Engine.
- Старый PyQt5 монолит нельзя считать частью нового web runtime.
- UX E2E после последних UI изменений требует диагностики таймаута таблицы.

## 10. Проверки и регрессия

Базовые проверки:

```text
node --check web/js/app.js
node --check web/js/workspace.js
node --check web/js/table.js
node --check web/js/pages.js
node --check web/js/dashboard.js
node --check site/js/site.js
python -m py_compile server/app.py server/routers/jobs.py services/database.py
git diff --check
```

Серверные наборы:

```text
python tests/test_part1_server.py
python tests/test_part34_site_e2e.py
python scripts/run_all_tests.py --all
```

UX E2E:

```text
python tests/test_ux_focus_e2e.py
```

Ожидаемый текущий результат:

```text
test_part1_server.py: 125 OK, 0 FAIL
test_part34_site_e2e.py: 29 OK, 0 FAIL
```

UX E2E должен быть доведён до полного прохождения до release.

## 11. Критерии приёмки новой архитектуры

- новый shell открывается без browser tab dependency;
- workspace/view/context route работает;
- legacy `open(key)` не ломает существующие страницы;
- context открывает нужную запись/фильтр;
- commands проверяют permissions;
- tasks переживают reload/restart;
- массовые операции не повторяют processed IDs;
- все большие выборки выполняются server-side;
- Saved Views переживают reinstall/localStorage cleanup;
- нет фиктивных действий;
- все loading/empty/error/cancel/retry states явные;
- RU/EN покрывают новые views;
- сайт и программа используют одну design language;
- accessibility/security/performance tests зелёные.

## 12. Формат дальнейшей работы

Каждый следующий агент должен:

1. Прочитать этот master и handoff prompt.
2. Проверить git status и существующие изменения.
3. Выбрать один крупный блок.
4. Сохранить compatibility adapter.
5. Добавить реальные файлы, endpoints, tests и docs.
6. Запустить node/pycompile/diff checks и релевантные E2E.
7. Обновить этот master, `SUOT_NEXT_ALL_REQUESTS_AND_STATUS.md`, `PROJECT_REBUILD_SUMMARY.md`.
8. Не заявлять незавершённые функции как готовые.

Начинать следует с Block 1: Navigation Registry + Workspace Shell, затем Block 2, Block 3 и Task Center.


1. FastAPI Composition Root.
2. Auth/RBAC boundary.
3. Entity services.
4. Query/Filter service.
5. Job Orchestrator.
6. Event/Audit stream.
7. Import/Export/Print workers.
8. Repository adapters (SQLite/PostgreSQL).
9. Migration/versioning.
10. Diagnostics/health.

### Новая навигация

```text
workspace   постоянная рабочая область
view        конкретный экран
context     record/project/filter context
command     действие без отдельной вкладки
task        длительная server-side операция
pin         закреплённый переход
recent      история переходов
```

`web/js/workspace.js` уже создаёт registry и adapter к legacy tabs. Следующий этап — перевести UI и вызовы `Alpine.store("tabs").open(...)` на новый store с сохранением обратной совместимости.

- `web/js/api.js` — HTTP client/bearer token.
- `web/js/i18n.js` — RU/EN.
- `web/js/icons.js` — icon registry.
- `web/js/tabs.js` — legacy browser-tabs compatibility store.
- `web/js/workspace.js` — new navigation registry/workspace state.
- `web/js/table.js` — table engine, filters, views, bulk actions.
- `web/js/pages.js` — structured pages.
- `web/js/dashboard.js` — dashboard/readiness/focus/tasks/activity/calendar.
- `web/js/palette.js` — command palette.
- `web/js/reports.js`, `print_editor.js`, `import_wizard.js`, `export_dialog.js` — feature UI.
- `web/css/tokens.css`, `web/css/components.css` — app design system.

### Site

- `site/index.html` — public website.
- `site/css/site.css` — public design system.
- `site/js/site.js` — manifest/download/demo/theme/carousel/palette.
