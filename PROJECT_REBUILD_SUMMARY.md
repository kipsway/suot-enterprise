# SUOT NEXT — Rebuild Summary

Дата: 2026-09-25
Статус: новая архитектура в процессе перехода
Корень: `C:\Users\ДДД\Desktop\программа`

## 1. Запрос владельца

Создать не косметический редизайн, а полностью новую программу уровня крупных продуктов:

- новая дизайн-система и визуальный язык;
- новая навигационная и workspace-концепция;
- новые пользовательские сценарии;
- новые функции и сущности;
- новая backend/job-архитектура;
- новый публичный сайт;
- RU/EN;
- сохранение бизнес-данных, прав и совместимости;
- масштабируемая архитектура, а не набор хрупких Alpine-компонентов;
- большой объём новой функциональности и отдельная сводка выполненного.

Требование «более 100 000 новых строк» зафиксировано как долгосрочная цель программы, но не будет представлено как уже выполненное: искусственное добавление пустых строк не является архитектурой.

## 2. Уже реализовано в текущем дереве

### Блок 1 (2026-09-25): Navigation Registry + Workspace Shell

- реестр `Alpine.store("next")`: 27 записей, группы `core/safety/work/service`,
  RU/EN-подписи, алиасы, порядок;
- пины с persist (`suot_next_pinned`), недавние с cap 12 (`suot_next_recent`);
- `open()` — только через проверенные `tabs.*`-методы + событие настроек;
  событие `suot-next-open`; Alt+1..9 на закреплённое;
- панель-переключатель Workspace (поиск, пины, недавние, группы, Esc, ARIA);
- тест `tests/test_next_nav_e2e.py` — 18/18;
- устранены блокеры: `bulkProgress?.`-гарды, задвоенный `.bulkbar`,
  битые `?`-строки и мусорные кнопки лендинга, клик палитры
  (`findIndex` по `id`), локаторы part2.

### Блок 2 (2026-09-25): Entity Registry + Detail Workspace

- `web/js/entities.js`: 10 JSON-сущностей + generic custom + `kind:none`
  для structured (честно, без заглушек);
- слайдер-досье в новом визуальном языке (drawer, sticky-шапка, timeline,
  reduced-motion): поля/заметки/связи/история + настоящий rollback;
- входы: `suot-detail-open`, контекст `recordId` реестра, кнопка
  «Открыть досье» в старой панели;
- тест `tests/test_entity_detail_e2e.py` — 19/19 (rollback проверен через API).

### Блок 3 (2026-09-25): редизайн интерфейса + анимации

- `web/css/next.css`: полный визуальный слой (типографика, каркас, кнопки,
  поля, карточки, таблицы, KPI, скроллбары, striped progress, focus-visible);
  переменные тем и запретные проперти не тронуты;
- скриншоты shell (светлая/тёмная), switcher, dossier — визуально подтверждено;
- тест `tests/test_design_next_e2e.py` — 9/9;
- регрессия: part33 8/8, part22 16/16, part2 106/106, ux_focus 12/12,
  wizard 7/7.

### Блок 4 — Aurora shell concept + Motion 3.0 (2026-09-25)

- Auth-экраны только через CSS: ambient blobs (`nxDrift`, reduced-motion safe),
  стеклянные карточки, glow логотипа, hover-лифт языковых карт, пилюли шагов,
  сегмент-контрол, градиент auth-aside.
- Shell chrome: разделитель футера, тень топбара, граница таббара, blur статусбар.
- Motion 3.0: stagger строк таблицы, `nxRowIn` + `nxStripes` (токены);
  paneIn/shimmerX/modalIn/toastIn переиспользованы.
- Восстановлена потерянная EN-карточка языка (английский был недоступен),
  `part29_en` 8/8.
- Скриншоты: lang/setup/shell/drawer/switcher, светлая + тёмная темы.
- Регрессия: wizard 7/7, part22 16/16, part33 8/8, ux_focus 12/12,
  entity_detail 19/19, design_next 9/9, part2 106/106, next_nav 18/18.

### Блок 5 — Command Bus + keyboard-first (2026-09-25)

- `web/js/commands.js`: реестр 8 команд (RU/EN, шорткат-хинты, `run()`→bool);
  виды через Navigation Registry; оживлены F5 (reload) и Ctrl+F (палитра);
  Ctrl+N/Ctrl+E без слушателей — не тронуты (известный пробел).
- Секция «Команды» в переключателе; focus-trap на switcher/dossier;
  Alt+2 гвард при модалке.
- Тест `tests/test_command_bus_e2e.py` — 20/20.

### Блок 6 — Task Center + operation history (2026-09-25)

- `jobs.py`: ранняя валидация target (400), убраны мёртвые `to_key`/`move`.
- Центр задач (`.tc-*`, бейдж в статусбаре, retry/cancel/export, RU/EN),
  событие `suot-tasks-changed`, команда `tasks`, focus-trap.
- Тесты: `test_tasks_server` — 24/24, `test_tasks_e2e` — 14/14.

### Блок 9 — Реорганизация + стандарт качества (2026-09-25)

- Аудит паритета: мёртвая «Аналитика» (`reports` без API) переведена
  на дашборд в 3 местах (сценарий, реестр, `openScenario`).
- `docs/CODEMAP.md`: слои, фича→файлы, соглашения, карта тестов, мусор.
- Тест `test_nav_parity_e2e` — 8/8 (27 видов живы; тонкие structured — INFO).

### Блок 10 — Полный редизайн заменой «Aurora Dusk» (2026-09-25)

- Живой слой — Industrial-блок `tokens.css`: тёмная сине-чёрная
  (`bg #080912/#0E1020`, текст `#F2F4FA/#B9C1D6/#8B96AC`), светлая Porcelain,
  лайм-акцент и семантика сохранены, тени углублены.
- Парящий shell (сайдбар-карточка, топбар/статусбар-пилюли) — проверен скриншотом.
- Контраст WCAG AA в обеих темах — тест считает ratio (зелёно).
- Регрессия: design_next 11/11, part22 16/16, part33 8/8, wizard 7/7,
  ux_focus 12/12, next_nav 18/18, command_bus 20/20, entity_detail 19/19,
  part2 106/106.

### Блок 10 — финальное качество (2026-09-26)

- Security audit 74/74 (включая IDOR Блоков 7–9); новый
  `test_final_quality_e2e.py` — 14/14 (a11y, EN, перф-бюджеты, версии 2.2.3).
- Широкая регрессия непокрытого — всё зелёное (part29, design_next,
  part1_server 125, views/tasks, part25–28, part30, part32, part34,
  plugins/doc/migration). Packaging: бамп и сборка — за владельцем.

### Блок 9 — миграция legacy UI (2026-09-26)

- `tabs.open` — адаптер поверх Registry (таблицы напрямую, виды через
  `next.openKey`); договор в CODEMAP; тест `test_migration_e2e.py` — 10/10.
- Регрессия: part35 28/29 (CSS-FAIL прошлых блоков), traverse 38/38,
  next_nav 18/18, nav_parity 27/27, command_bus 20/20, part2 106/106.

### Блок 8 — Plugin/Capability v2 (2026-09-26)

- Manifest v2 + validate endpoint, capabilities с грантами админа,
  per-user settings с валидацией; поведения параметризуются (TSV, цвет метки);
  гейты в тулбаре/палитре/запуске; Plugin Center UI. Тест — 21/21.
- Регрессия: plugins19 8/8, command_bus 20/20, traverse 38/38, part2 106/106.

### Блок 7 — Documents Center (2026-09-26)

- Backend: версии шаблонов с авто-снапшотом, асинхронная очередь печати
  (прогресс/отмена/повтор/скачивание/preview), saved reports CRUD + run;
  owner-scope везде. Новый `tests/test_documents_e2e.py` — 18/18.
- Frontend: центр с тремя секциями, deep-link в мини-Word, сохранение спеки
  из конструктора, PDF-preview в iframe; registry + команда `documents`.
- Регрессия: nav_parity 27/27, command_bus 20/20, traverse 38/38,
  print 14/14, search_reports 15/15, export 12/12, part2 106/106.

### Блок Dashboard v4 — живые глубокие ссылки + свежесть stats (2026-09-26)

- Readiness/focus/KPI → таблицы с серверным smart-фильтром; новый
  `tests/test_dashboard_v4_e2e.py` — 8/8, ноль JS-ошибок.
- Фикс протухших stats: `onTabActive()` + `x-effect` на стор вкладок, guard
  гонок в `load()`; `test_part24_e2e.py` обновлён до v4 — 15/15.
- Регрессия: next_nav 18/18, command_bus 20/20, traverse 38/38, tasks 14/14,
  wizard 7/7, part22 16/16, part33 8/8, ux_focus 12/12, part2 106/106.

### Блок 7 — Query Engine + Saved Views (2026-09-25)

- Smart-фильтры для custom-таблиц (бэк + чипы в UI); фикс `lower`→`pylower`
  для кириллических статусов (касался и системных таблиц).
- Серверные виды (`user_views` + `/api/views` CRUD + изоляция);
  фронт: сервер-источник, localStorage-кэш, ленивая миграция.
- Тесты: `test_views_server` — 26/26, `test_views_e2e` — 10/10
  (переживание wipe localStorage доказано).

### Backend и данные

- сохранены существующие API и изоляция данных;
- добавлена SQLite persistence для массовых операций (`bulk_jobs`);
- добавлены server-side jobs: `queued`, `running`, `completed`, `failed`, `cancelled`;
- добавлены polling, cancel и retry;
- сохраняются `processed_ids`, поэтому retry не повторяет уже обработанные записи;
- добавлена история jobs и экспорт CSV;
- добавлена миграция старой таблицы jobs;
- smart filters перенесены в серверную выборку;
- Saved Views сохраняют smart filter.

### UX и рабочее место

- новый hero рабочего стола SUOT Next;
- сценарии «сегодня / проверка / документы»;
- readiness center и focus day;
- workspace presets;
- loading/empty/error/smart-alert состояния;
- новый command palette;
- sticky table headers и горизонтальная прокрутка;
- saved views, bulk selection, bulk edit/delete, transfer;
- server bulk progress panel;
- operation history panel;
- structured workspace redesign для чек-листов, CAPA, протоколов, рисков;
- split-screen authorization и onboarding.

### Сайт

- новый hero-proof блок;
- сценарии «Проверить готовность / Закрыть рабочий день / Подготовить документы»;
- новый final CTA;
- Industrial Signal visual layer;
- адаптивные scenario cards;
- сохранены download flow, manifest, SHA-256, screenshots, demo и theme switcher.

## 3. Целевая архитектура SUOT Next Core v3

### Frontend layers

1. **Shell** — окно, responsive layout, theme, accessibility, telemetry boundary.
2. **Navigation Registry** — декларативные routes/views, capability checks, order, aliases.
3. **Workspace Engine** — layout per scenario, widgets, saved layouts, drag/drop.
4. **Command Bus** — actions, keyboard commands, palette, batch commands.
5. **Entity Registry** — единое описание сотрудников, СИЗ, рисков, документов и задач.
6. **Data Plane** — server state, cache, abort/race protection, optimistic mutations.
7. **View Components** — dashboard, tables, detail panels, forms, timelines, reports.
8. **Design System** — tokens, components, motion, accessibility, responsive rules.
9. **Migration Adapter** — старые tab-store/API contracts постепенно заменяются новым ядром.

### Backend layers

1. FastAPI composition root;
2. auth/RBAC boundary;
3. entity services;
4. query/filter service;
5. job orchestration;
6. audit/event stream;
7. import/export/print workers;
8. SQLite/PostgreSQL repository adapters;
9. migration/versioning;
10. health/diagnostics boundary.

## 4. Новая концепция вкладок

Текущие browser-like tabs остаются временным compatibility layer. Целевая модель:

- **Workspace** — постоянная рабочая область;
- **View** — конкретный экран внутри workspace;
- **Context** — текущая запись/проект/фильтр;
- **Command** — действие, открываемое без отдельной вкладки;
- **Task** — долгоживущая операция с progress/retry/cancel;
- **Pin** — закреплённый быстрый доступ;
- **Recent** — недавние переходы, а не бесконечная панель вкладок.

Переход будет обратно совместимым: старые `open(table)` вызовы продолжат работать через adapter, но новые представления будут создаваться как `{workspace, view, context}`.

## 5. План новых крупных блоков (обновлено 2026-09-25: радикальный трек)

1. Navigation Registry и Workspace Shell. (выполнено, Блок 1)
2. Entity Registry и универсальный Detail Workspace. (выполнено, Блок 2)
3. Редизайн-слой + motion-конвенции. (выполнено, Блок 3)
4. Aurora shell concept + Motion 3.0. (выполнено, Блок 4)
5. Command Bus и keyboard-first navigation. (выполнено, Блок 5)
6. Task Center с jobs, retry, history и audit. (выполнено, Блок 6)
7. Query Engine для всей таблицы и Saved Views. (выполнено, Блок 7)
8. Детэбификация: удалить полосу вкладок полностью; навигация только
   реестр/switcher/bus/sidebar; стор — headless-движок видов. (выполнено:
   таббар стёрт, палитра через реестр, тесты мигрированы)
9. Реорганизация + стандарт качества. (выполнено, Блок 9)
10. Полный редизайн заменой «Aurora Dusk». (выполнено, Блок 10)
11. Dashboard v4: scenarios, readiness, focus, activity.
12. Document Center: templates, reports, print workflows + полный редизайн сайта
    (понятный блок скачивания, SHA рядом, история версий, инструкция).
13. Plugin contract v2 и capability registry.
14. Концепт-расширение (бэклог): shared-виды, дайджест просрочек,
    расписание отчётов, ретенция бэкапов в UI, responsive-фаза.
15. Игры заново (предпоследняя часть): 2048 и Block Blast с оригинальными
    правилами, поле 8×8 сохраняется, удобное управление.
16. Миграция старого UI на новый Shell.
17. Финальная WCAG/performance/security regression + публикация + релиз.

## 6. Критерии готовности новой системы

- пользователь может завершить проверку готовности из одного workspace;
- любой task открывается из контекста, без потери состояния;
- массовые операции имеют progress/cancel/retry/history;
- server-side filters работают по всей таблице;
- новая навигация не ломает старые routes;
- все состояния имеют loading/empty/error/retry;
- RU/EN меняют все новые подписи;
- нет фиктивных undo/redo;
- security tests и migration tests проходят;
- сайт и программа используют одну визуальную концепцию.
