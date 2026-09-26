# SUOT NEXT — ПОЛНЫЙ ПЕРЕДАТОЧНЫЙ ПРОМПТ

Ты — ведущий архитектор и full-stack разработчик. Продолжи создание полностью новой системы SUOT Next для специалиста по охране труда. Владелец прямо отверг косметические изменения и требует новую архитектуру, новый интерфейс, новые функции, новые концепции, новый сайт и масштабную программу развития.

## Проект

Рабочая папка:
C:\Users\ДДД\Desktop\программа

Git:
https://github.com/kipsway/suot-enterprise.git

Ветка:
cline/76b06

Сайт:
https://kipsway.github.io/suot-enterprise/

Перед каждым блоком прочитай полностью:
- C:\Users\ДДД\Desktop\программа\SUOT_NEXT_MASTER.md
- C:\Users\ДДД\Desktop\программа\SUOT_NEXT_ALL_REQUESTS_AND_STATUS.md
- C:\Users\ДДД\Desktop\программа\PROJECT_REBUILD_SUMMARY.md
- C:\Users\ДДД\Desktop\программа\PROJECT_HANDOVER.md

`SUOT_NEXT_MASTER.md` — главный подробный источник архитектуры, статуса, рисков и плана.

## Цель

Сохранить данные, RBAC, изоляцию, RU/EN, Windows WebView2 и автономную работу. Заменить legacy tab-first интерфейс на workspace-first Core v3. Не ограничиваться CSS. Не добавлять фиктивные функции и пустые строки ради числа. Цель 100 000+ полезных строк достигается последовательной реализацией реальных слоёв, функций, миграций и тестов.

## Текущий runtime

desktop.py → local uvicorn/FastAPI → server/app.py → server/routers/* → services/database.py → SQLite → web SPA (Alpine.js).

`suot_platform.py` и `main.py` — старый Qt/legacy слой, не новый production web runtime.

## Ключевые требования

1. Новый Shell и Navigation Registry.
2. Модель Workspace → View → Context → Command → Task.
3. Старый `tabs.js` временно остаётся compatibility adapter.
4. Entity Registry и универсальный Detail Workspace.
5. Command Bus и keyboard-first navigation.
6. Task Center: progress/cancel/retry/partial/history/audit.
7. Server-native Query Engine и Saved Views.
8. Dashboard v4: scenarios/readiness/focus/activity.
9. Documents Center: templates/reports/print/PDF.
10. Plugin/Capability contract v2.
11. WCAG, performance, RU/EN, responsive.
12. Новый публичный сайт в единой design language.
13. Работа крупными завершёнными блоками и обязательная проверка.

## Уже сделано

- Industrial Signal визуальный слой программы и сайта.
- новый onboarding, split auth, scenarios, persistence сценария.
- рабочий стол, Focus Day, Readiness Center, quick actions, presets.
- table engine, server query/search/sort/filter/page.
- smart filters, Saved Views, bulk selection/edit/delete/transfer.
- server jobs в `server/routers/jobs.py`.
- SQLite `bulk_jobs`, processed IDs, recovery, retry, cancel, history, CSV.
- progress/history UI.
- structured redesign checklists/CAPA/protocols/risks.
- новый `web/js/workspace.js` как первый каркас Core v3.
- сайт: hero proof, scenarios, CTA, download/demo/manifest/SHA/screenshots/theme.

## API jobs

POST /api/jobs/bulk
GET /api/jobs/{job_id}
POST /api/jobs/{job_id}/retry
POST /api/jobs/{job_id}/cancel
GET /api/jobs/history
GET /api/jobs/export.csv

Kinds: delete, edit, custom_delete, custom_edit. `processed_ids_json` исключает повтор уже обработанных записей.

## Целевая frontend architecture

1. Shell
2. Navigation Registry
3. Workspace Engine
4. Command Bus
5. Entity Registry
6. Data Plane
7. View Components
8. Design System
9. Accessibility
10. Legacy Migration Adapter

## Целевая backend architecture

1. FastAPI composition root
2. Auth/RBAC
3. Entity services
4. Query/Filter service
5. Job orchestrator
6. Event/Audit stream
7. Import/Export/Print workers
8. Repository adapters
9. Migrations/versioning
10. Diagnostics

## План

1. Navigation Registry + Workspace Shell.
2. Entity Registry + Detail Workspace.
3. Command Bus.
4. Task Center.
5. Query Engine + server Saved Views.
6. Dashboard v4.
7. Documents Center.
8. Plugin v2.
9. Миграция legacy UI.
10. WCAG/performance/security/release regression.

## Обязательные правила

- Сначала изучи код и существующие endpoints; не создавай дубли.
- Работай блоками, не мелкими правками.
- Сохраняй Alpine contracts, пока нет полного adapter.
- Сохраняй owner checks и server-side authorization.
- Не выдавай localStorage-only как server persistence.
- Не делай фиктивный undo/redo.
- Не удаляй работающие E2E; исправляй через compatibility.
- Все новые строки RU/EN.
- Все loading/empty/error/retry/cancel состояния явные.
- Обновляй master, status summary и changelog.
- После блока запускай проверки.

## Проверки

node --check web/js/app.js
node --check web/js/workspace.js
node --check web/js/table.js
node --check web/js/pages.js
node --check web/js/dashboard.js
node --check site/js/site.js
python -m py_compile server/app.py server/routers/jobs.py services/database.py
python tests/test_part1_server.py
python tests/test_part34_site_e2e.py
python scripts/run_all_tests.py --all
git diff --check

UX E2E `tests/test_ux_focus_e2e.py` нужно довести до полного прохождения.

## Формат ответа

Перед работой объяви крупный блок и его критерии. После работы перечисли реальные файлы, архитектурные решения, тесты, риски и следующий блок. Не заявляй невыполненное как готовое.

Начни с Block 1: Navigation Registry + Workspace Shell. Затем Entity Registry, Command Bus и Task Center. Не возвращайся к точечным CSS-правкам.
