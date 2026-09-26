# CODEMAP — где что лежит в SUOT Neo (срез 2026-09-25)

53 тестовых набора (`tests/test_*.py`), 33 JS-модуля (`web/js`),
36 Python-файлов `server/`, 23 `services/`, 38 `modules/` (Qt legacy),
12 `app_core/`, 13 `scripts/`, 39 `widgets/`.

## Слои и точки входа

| Слой | Путь | Вход |
|---|---|---|
| Desktop-обёртка | `desktop.py` | `python desktop.py` / exe |
| HTTP API | `server/app.py` | `uvicorn server.app:app` |
| SPA | `web/index.html` + `web/js/*.js` | `/` того же origin |
| Данные | `services/database.py` + `app_core/db_interface.py` | — |
| Сборка | `suot_neo.spec` → `scripts/build_exe.py` → `make_portable.py` → ISCC `installer/suot_neo.iss` → `scripts/publish_site.py` | `scripts/release.py` |
| Legacy Qt (frozen) | `suot_platform.py`, `main.py`, `modules/`, часть `services/` и `app_core/` | не запускать |

## Фича → файлы (прямой поиск)

| Фича | Backend | Frontend |
|---|---|---|
| Auth/сессии/пароли | `server/routers/auth.py`, `server/tokens.py`, `server/deps.py`, `services/security.py`, `setup_api.py` (recover) | `setup_wizard.js`, `app.js` (submitAuth/validate) |
| Таблицы CRUD/фильтры/сортировка | `server/routers/data.py`, `ucols.py`, `services/database.py` (query_*) | `web/js/table.js`, `web/index.html` (грид ~1143+) |
| Свои таблицы | `server/routers/custom.py` | `table.js` (isCustom-ветки) |
| Заметки/связи/история/rollback | `server/routers/records.py` | `table.js` (openPanel), `detail.js` (досье) |
| Печать/PDF | `server/routers/print_api.py`, `print_pdf.py` | `print_editor.js`, `batch_print.js` |
| Импорт/экспорт | `import_api.py`, `export_api.py`, `exporter_api.py` | `import_wizard.js`, `export_dialog.js` |
| Бэкапы | `server/routers/backup_api.py` | `part19.js` (backupCenter) |
| Jobs/Task Center | `server/routers/jobs.py` | `web/js/tasks.js`, `table.js` (runServerJob) |
| Виды таблиц | `server/routers/views.py` | `table.js` (loadViews/saveView) |
| AI-чат/агент | `server/routers/ai_api.py` | `ai_chat.js` |
| Дашборд | `dashboard.py`, `dash3_api.py` | `dashboard.js` |
| Календарь/НПА/инструменты | `calendar_api.py`, `npa_api.py`, `tools_api.py` | `calendar_page.js`, `npa_page.js`, `tools.js` |
| Диагностика | `server/routers/diag.py` | `diag_page.js` |
| Навигация нового слоя | — | `workspace.js` (реестр), `tabs.js` (движок видов), `switcher` в `index.html` |
| Команды | — | `commands.js` (шина), `palette.js` (палитра) |
| Сущности/досье | — | `entities.js`, `detail.js` |
| Настройки/темы/хоткеи | `settings_api.py` | `settings_center.js` |
| Журнал/пользователи/обновления | `help_api.py` | `part18.js` (helpCenter, usersAdmin) |
| Сайт/лендинг | `site/` (index.html, css/site.css, js/site.js, downloads/) | — |
| Установщик | `installer/suot_neo.iss` (Inno Setup 6) | — |

## Соглашения об именовании (как есть в коде)

- Роутеры: `server/routers/<домен>.py`, префикс `/api/<домен>`.
- Таблицы БД: системные JSON — `employees…companies` (константа `JSON_TABLES`);
  свои — ключ `u_` + 10 hex; записи — `data_json` + `user_id` (0 — общие).
- Ключи localStorage: `suot_*` (`suot_token`, `suot_views_<key>`,
  `suot_next_pinned/recent`, `suot_tabs`, `suot_start`, `suot_theme`…).
- События (CustomEvent, bubbles): `suot-*` (`suot-next-open`, `suot-detail-open`,
  `suot-tasks-open/changed`, `suot-palette-open`, `suot-logout`, `suot-toggle-theme`…).
- Сторы Alpine: `tabs` (движок видов), `next` (реестр), `user`, `brand`,
  `version`, `plugins`, `custom`; шины: `SUOT_COMMANDS`, `SUOT_ENTITIES`.
- CSS: `tokens.css` (переменные/темы/motion), `components.css` (компоненты),
  `next.css` (аддитивный редизайн; префиксы `ws-`, `dt-`, `tc-`, `nx-*`).
- Тесты: `tests/test_<домен|partN>[_server|_e2e].py`, запуск `python tests/<файл>.py`,
  всё сразу — `python scripts/run_all_tests.py [--e2e|--all]`.
- Навигация (Блок 9, workspace-first): новый код открывает виды только через
  `next.open(id)` / `next.openKey(id|key|alias)` / `openViewExact(...)` или
  событие `suot-next-open`. `tabs.open(key)` — legacy-адаптер: табличные
  маршруты (`TABLE_KEYS`, `u_*`, `print_editor`, `all`) идут напрямую,
  именованные виды — через Registry, miss — legacy. Прямые `tabs.openX()`
  остаются валидными (совместимость E2E), но в новом коде не использовать.

## Мусор в корне (не коммитить, можно удалять)

`_dbg*.py`, `_mini*.py`, `_probe*.py`, `_tb*.py`, `_tmp_check.py`, `_xdcheck.py`,
`_hdiff.py`, `_i_diff.py`, `_i_pg2.py`, `_p23_js.py`, `_panecheck.py`,
`_bisect.py`, `_cmp_tbody.py`, `_cmt*.py`, `_diff_out.txt`, `test_import.py`,
`debug.log`, `*.db*`, `ux_tmp.log` — отладочные скрипты прошлых сессий,
покрыты `.gitignore`. Исключения (НЕ мусор): `_probe_parity.py` удалён;
проверяй `git status` перед удалением.
