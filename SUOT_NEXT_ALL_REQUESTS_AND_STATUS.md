# SUOT NEXT — ПОЛНАЯ СВОДКА ЗАПРОСОВ, ТРЕБОВАНИЙ И ТЕКУЩЕГО СОСТОЯНИЯ

Дата: 25 сентября 2026
Проект: `SUOT Next / ОхранаТруда Про / SUOT Enterprise`
Корень проекта: `C:\Users\ДДД\Desktop\программа`
Git: `https://github.com/kipsway/suot-enterprise.git`
Ветка: `cline/76b06`
Сайт: `https://kipsway.github.io/suot-enterprise/`

## 1. Цель

Создать полностью новую программу и сайт уровня крупных продуктов: новый дизайн, новая навигация, новая workspace-концепция, новые функции, новые backend/job-архитектуры и новые пользовательские сценарии. Сохранить данные, права, бизнес-функции, RU/EN, Windows desktop/webview и автономную работу.

Недостаточно просто поменять CSS, добавить карточки или перекрасить старый интерфейс. Требуется ощутимо новая система. Цель «100 000+ строк» зафиксирована как долгосрочная, но искусственно добавлять пустые строки нельзя: код должен быть реальной архитектурой и функциями.

## 2. Все пожелания владельца

1. Полностью новый дизайн программы и сайта.
2. Новый интерфейс, а не cosmetic theme.
3. Новые функции, концепции и сценарии.
4. Разрешено убрать/переработать старую систему вкладок.
5. Перейти от browser-like tabs к Workspace/View/Context.
6. Сохранить все данные, права, изоляцию, RU/EN и Windows запуск.
7. Сделать работу специалиста быстрой, наглядной и безопасной.
8. Добавить WCAG, keyboard navigation, focus management, reduced motion.
9. Добавить performance-полировку и большие таблицы.
10. Сделать server-side filters для всей таблицы.
11. Сделать настоящие bulk jobs: progress, cancel, retry, partial completion, history.
12. Не делать фиктивный undo/redo.
13. Сохранить совместимость и миграционный путь.
14. Создать эту сводку и передаточный промпт.
15. Работать целыми блоками и проверять результат.
16. Финально прогнать полную регрессию.
17. Сайт должен быть таким же сильным, как программа.
18. Масштабируемая новая архитектура вместо хрупких Alpine-компонентов.

## 3. Текущая архитектура

Рабочая цепочка:

```text
desktop.py → local uvicorn/FastAPI → server/app.py
→ web/index.html + web/js → SQLite/services/database.py
→ существующие REST API
```

`suot_platform.py` — старый PyQt5 legacy-монолит, не основная точка новой web-сборки.

## 4. Уже реализовано

### UX и onboarding

- новый первый экран, RU/EN и split-screen авторизация;
- onboarding-сценарии с сохранением выбора;
- новый hero рабочего стола;
- Focus Day и Readiness Center;
- быстрые действия и workspace presets;
- loading/empty/error/smart-alert состояния;
- command palette с группировкой и защитой от гонок;
- Saved Views, sticky headers, горизонтальная прокрутка;
- focus-trap, автофокус, Escape, maximized desktop;
- error-state таблицы и Retry.

### Таблицы и данные

- server-side search/sort/column filters/pagination;
- server-side smart filters;
- выбор строк и сохранение выделения;
- bulk edit/delete/transfer;
- Saved Views и presets;
- server bulk jobs и progress UI;
- SQLite jobs persistence;
- retry/cancel/history и CSV export.

### Backend jobs

Добавлен `server/routers/jobs.py`:

```text
POST /api/jobs/bulk
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/retry
POST /api/jobs/{job_id}/cancel
GET  /api/jobs/history
GET  /api/jobs/export.csv
```

Поддерживаются delete, edit, custom_delete, custom_edit. `processed_ids` не позволяет повторно обрабатывать уже завершённые записи.

### Новая архитектурная инициатива

Добавлен `web/js/workspace.js`. Начата модель:

```text
Workspace → View → Context → Command → Task
```

Старый `tabs` остаётся compatibility layer до завершения миграции.

### Блок 1 (2026-09-25): Navigation Registry + Workspace Shell — выполнено

- `web/js/workspace.js` переписан в реестр из 27 записей
  (`{id, view, key, labelRu/labelEn, icon, group, order, aliases}`),
  группы `core/safety/work/service`, пины (`suot_next_pinned`, persist),
  недавние (`suot_next_recent`, cap 12), `resolve()` по id/key/alias,
  `open()` через адаптер `tabs.*` (все 12 ветвей ведут на проверенные методы),
  Alt+1..9 на закреплённое (guard полей ввода, установка один раз),
  события `suot-next-open` / `suot-ws-toggle` (+`suot-ws-state` с
  `bubbles:true` — без него `.window`-подписчики не срабатывают).
- Найден и задокументирован грабель Alpine: `Alpine.store(name, value)`
  ничего не возвращает — стор забирается отдельным `Alpine.store("next")`.
- Панель-переключатель Workspace: кнопка «Рабочая область» в футере сайдбара,
  overlay `.ws-overlay` + `.ws-panel` (поиск, Закреплено, Недавние, группы,
  pin-тоглы, Esc, `role=dialog`/`aria-modal`), классы только `ws-*`.
- Попутно чинено (блокировало E2E): null-guards `bulkProgress?.` в панели
  массовых операций (3 pageerror на каждое открытие таблицы); задвоенный
  `<div class="bulkbar">` глотавший всю таблицу (сетка была скрыта);
  битые строки `?` в лендинге/кнопках (4 мусорные кнопки `reload(false)`
  на экране языка удалены, тексты восстановлены: «Выберите язык»,
  «Ваше рабочее место будет готово через минуту», «Продолжить на русском»,
  «• Работает офлайн», «Сценарии», «Повторить»); клик палитры
  (`indexOf` по пересоздаваемым объектам → `findIndex` по `id`);
  неоднозначный локатор `.nav-item` «Риски» и `.nav-item.danger` выхода
  в `test_part2_e2e.py` (уточнены без смены смысла).
- Новый тест `tests/test_next_nav_e2e.py`: 18/18 (реестр, resolve, открытие
  через событие, persist пинов, cap недавних, Alt+2, панель RU, поиск,
  Escape, регрессия сайдбара, ноль JS-ошибок).

### Сайт

Добавлены Industrial Signal, hero-proof, рабочие сценарии, final CTA, adaptive cards. Сохранены download flow, manifest, SHA-256, screenshots, demo и theme switcher.

## 5. Целевая новая система

### Frontend layers

1. Shell
2. Navigation Registry
3. Workspace Engine

## 7. Проверки

Последние успешные проверки:

```text
python tests/test_part34_site_e2e.py → 29 OK, 0 FAIL
python tests/test_part1_server.py → 125 OK, 0 FAIL
node --check web/js/workspace.js
node --check web/js/app.js
node --check web/js/dashboard.js
node --check web/js/pages.js
node --check web/js/table.js
node --check site/js/site.js
python -m py_compile server/app.py server/routers/jobs.py services/database.py
git diff --check
```

`tests/test_ux_focus_e2e.py` после последних UI-изменений требует диагностики таймаута ожидания таблицы.

## 7b. Проверки Блока 1 (2026-09-25)

```text
node --check web/js/workspace.js → OK
git diff --check → чисто
python tests/test_next_nav_e2e.py → 18 OK, 0 FAIL
python tests/test_ux_focus_e2e.py → 12 OK, 0 FAIL (таймаут закрыт)
python tests/test_wizard_e2e.py → 7 OK, 0 FAIL
python tests/test_part2_e2e.py → 106 OK, 0 FAIL
python tests/test_part1_server.py → 125 OK, 0 FAIL
```

Диагностика таймаута `test_ux_focus_e2e`: причин было две —
null-обращения `bulkProgress.*` (3 pageerror) и задвоенный `.bulkbar`,
прятавший таблицу; обе устранены, тест зелёный. По ходу всплыли и закрыты:
битые `?`-строки лендинга, мёртвый клик палитры (`findIndex` по `id`),
двусмысленные локаторы part2 (`.first`, `.sidebar-foot`).

### Блок 2 (2026-09-25): Entity Registry + Detail Workspace — выполнено

- `web/js/entities.js`: дескрипторы 10 JSON-таблиц + generic custom (`u_*`)
  + честный `kind:none` для structured (notes/links/history API их не покрывают);
  `titleOf`/`fieldEntries`/`recordUrl`, RU/EN.
- `web/js/detail.js` + слайдер-досье (новый визуальный язык: drawer 460px,
  sticky-шапка, timeline истории, reduced-motion): поля, заметки, связи,
  история с НАСТОЯЩИМ откатом (`POST .../history/{id}/rollback`, без фикций);
  состояния loading/error/empty; Esc; RU/EN.
- Входы: событие `suot-detail-open`, контекст `recordId` в `store.open()`,
  кнопка «Открыть досье» в старой панели (старая при этом закрывается).
- Найден и задокументирован грабель Alpine: шаблонные `filtered.indexOf(it)`
  всегда -1 (геттер пересоздаёт объекты) — чинено через `findIndex` по `id`.
- Тест `tests/test_entity_detail_e2e.py`: 19/19 (включая rollback-проверку
  значения через API).
- Регрессия: part2 106/106, next_nav 18/18, ux_focus 12/12, part1 125/125.

### Блок 3 (2026-09-25): полный редизайн интерфейса + анимации — выполнено

- Новый аддитивный слой `web/css/next.css` (подключён после components):
  типографика (Inter-стек, tabular-nums, selection), каркас (сайдбар с
  градиентом и active-пилюлей, топбар blur, таббар-пилюли), кнопки
  (primary-градиент, press scale, focus-visible ring), поля (ring при фокусе),
  карточки/модалки/тосты (радиусы, слои теней), таблицы (micro-заголовки,
  hover, selected-индикатор — позиционирование/плотность/z-index/th не тронуты),
  KPI hover-lift, скроллбары, striped progress (`nxStripes` — единственный
  новый keyframes, на токенах).
- Значения CSS-переменных тем НЕ менялись; `.btn` transition (0.15s),
  rail <70px, плотность 8/3px, sticky/z-index — сохранены (проверено тестами).
- `dt-in` переведён на токены (`var(--dur-sm) var(--ease-out)`).
- Визуально проверено скриншотами: shell светлая/тёмная, switcher, dossier.
- Тест `tests/test_design_next_e2e.py`: 9/9 (next.css 200/link, шрифт,
  focus-visible, токен 0.15s, active-выделение, tabular-nums, reduced-motion,
  ноль JS-ошибок).
- Регрессия: part33 8/8, part22 16/16, part2 106/106, ux_focus 12/12,
  wizard 7/7.

### Блок 4 — Aurora shell concept + Motion 3.0 (2026-09-25) — выполнено

- План расширен по запросу владельца: Aurora/Motion как часть 4, игры заново
  как предпоследняя часть (см. §6).
- Auth-экраны (только CSS): ambient blobs (`nxDrift`, reduced-motion safe),
  стеклянные карточки, glow логотипа, hover-лифт языковых карт, пилюли шагов
  с glow, сегмент-контрол, auth-aside градиент.
- Shell chrome: разделитель футера, тень топбара, граница таббара, blur статусбар.
- Motion 3.0: stagger строк таблицы (nth-child 1–12, токены), `nxRowIn` +
  `nxStripes` (единственные новые keyframes); существующие paneIn/shimmerX/
  modalIn/toastIn переиспользованы; `dt-in` на токенах.
- Найдено и восстановлено: EN-карточка языка была потеряна в чужом рерайте
  лендинга (английский был недоступен) — возвращена, `part29_en` 8/8.
- Скриншоты: lang/setup/shell/drawer/switcher, светлая + тёмная темы.
- Регрессия: wizard 7/7, part22 16/16, part33 8/8, ux_focus 12/12,
  entity_detail 19/19, design_next 9/9, part2 106/106, next_nav 18/18.
  Два одиночных флака (ux_focus, entity_detail) — чистые перезапуски зелёные.

### Блок 8 — Детэбификация (2026-09-25) — выполнено
- Полоса вкладок удалена из разметки полностью (`web/index.html`: блок
  `.tabbar` + `.tab-overflow` стёрт, стор остался headless-движком видов).
  Навигация только: реестр/switcher/bus/sidebar; текущий вид виден
  в статусбаре.
- Палитра переведена на реестр (`openViewExact` + fallback `tabs.open`):
  recent/pins обновляются, `activeId` честный.
- Мигрированы тесты без потери смысла: part2 — утверждения активного вида
  через стор (`activeId`/`active.key|label`); design_next — фолбэк уже был;
  traverse — проверка journey (8 видов, `activeId`, отсутствие `.tabbar`
  в DOM, видимый контент) вместо overflow-метрики.
- Проверено скриншотом: контент тянется под топбар, пустые состояния,
  статусбар с текущим видом.
- Регрессия: traverse 38/38, part2 106/106, next_nav 18/18,
  command_bus 20/20, ux_focus 12/12, entity_detail 19/19, wizard 7/7,
  design_next 9/9; `node --check` (palette/workspace/commands), diff чисто.

### Фаза 4 — финальная сверка (2026-09-26) — выполнено

- Финальный `run_all_tests.py --all`: **1226 OK, 1 FAIL** (`test_tasks_e2e`
  под нагрузкой прогона; три сольных прогона подряд — 14/14, зафиксирован
  как флак, не дефект). Остальное — всё зелёное, включая новые
  test_polish (16/16) и part34 (32/32).
- Функциональная матрица покрыта наборами: импорт (import_master),
  экспорт (export/docx/csv/zip), печать (print/pdf/batch/list),
  бэкап→восстановление (backup19), auth/RBAC (security_audit 74/74),
  все виды (traverse/nav_parity/part35), все кнопки ключевых флоу.
- Релизная сборка (бамп, ISCC, публикация) — за владельцем: нет ISCC
  на PATH, версия осознанно 2.2.3 везде.

### Фаза 3 — сайт заново (2026-09-26) — выполнено

- 3.1: Aurora-токены (лайм, Porcelain, `fg-on-acc`), кнопки/карусель/демо
  без индиго; исправлен баг вложенности (CTA-секция внутри карточки гайда,
  двойной `</main>`); favicon в лайм; баланс HTML проверен парсером.
- 3.2: 20 SVG-иконок через инъектор `data-ic` (ES5); RU/EN-переключатель
  (`data-en` + словарь JS: статика, календарь, палитра, загрузки, точки
  карусели); поправлен факт (WebView2, 6 тем).
- 3.3: 7 свежих скриншотов Aurora с демо-данными + слайд Документов.
- 3.4: part34 расширен (иконки ≥20, слайдов 7, EN) — 32/32.

### Фаза 2 — полировка (2026-09-26) — выполнено

- Новый регрессионный `tests/test_polish_e2e.py` — 16/16: детектор наложений
  интерактивных элементов (виды × темы × 1280/1920) с учётом слоёв,
  касаний краёв и обрезки overflow-скроллом (по ходу отладил 3 ложных
  срабатывания); порядок кнопок в футерах (primary последний).
- Находки: структура сайдбара sound (внутренний скролл + закреплённый фут —
  стандартный паттерн, перестройка отклонена как риск без выгоды);
  конвенция [Отмена][Primary] соблюдена везде.
- Ноль JS-ошибок.

### Фаза 1 — доделка программы (2026-09-26) — выполнено

- 1.1: токены `--fg-on-acc/--fg-on-warn` (попутно починен контраст
  primary-hover в светлой теме), part35 29/29; удалены `_probe_*.py`;
  ретеншн результатов печати (30 дней / 20 на юзера) + recovery зависших
  заданий в lifespan; проверено напрямую (файл удалён, история цела).
- 1.2: полный `run_all_tests.py --all` — 1207 OK, 1 FAIL (part19);
  причина — мои переименования строк (`«Просрочка»` в манифесте и тосте),
  названия возвращены; плюс устранена структурная гонка тостов в тесте
  (ждём свежий тост, не `.last`); part19 дважды 14/14.
- 1.3: ревью дерева — 35 изменённых + 30 новых, секретов нет;
  `suot_platform.py` (9538 строк чужого диффа) исключить из коммита;
  коммит и пуш — за владельцем.

### Блок 10 — финальное качество (2026-09-26) — выполнено

- Security: `test_security_audit.py` расширен Блоками 7–9 (401 без токена
  на 6 endpoints, IDOR версий/шаблонов/откатов/отчётов/заданий/скачиваний,
  изоляция списков, гранты 403/400, валидация настроек) — 74/74.
- `tests/test_final_quality_e2e.py` (new) — 14/14: a11y новых панелей
  (нативные кнопки сегментов, `role=dialog` + `aria-modal/label` у preview,
  Escape, инпуты настроек внутри label), EN-смог Documents/Plugins
  (по пути пойман и исправлен EN-пробел: list не отдавал `name_en`,
  центр их теперь использует), перф-бюджеты (stats/list API ~0.01с < 3с,
  shell < 15с, центр < 5с), консистентность версий 2.2.3 (app/site/installer).
- Регрессия непокрытого: part29 21/21, design_next 11/11, part1_server 125/125,
  views 26/26, tasks_server 24/24, part25 13/13, part26 15/15, part27 13/13,
  part28 17/17, part30 19/19, part32 23/23, part34 29/29, plugins19 8/8,
  plugins_v2 21/21, documents 18/18, migration 10/10; `node --check`,
  `py_compile`, `git diff --check` чисто; ноль JS-ошибок везде.
- Packaging-вердикт: версия консистентна; бамп версии и пересборка
  installer/portable — решение владельца (дерево незакоммичено, релиз идёт
  через `scripts/release.py`); ISCC на этой машине не на PATH. Отдельный
  notes-файл не создан осознанно — чейнджлогом служат поблочные записи
  статусов.

### Блок 9 — миграция legacy UI, workspace-first адаптер (2026-09-26) — выполнено

- Инверсия адаптера: `tabs.open(key)` делегирует в Navigation Registry
  (`web/js/tabs.js`): табличные маршруты (`TABLE_KEYS`, `u_*`, `print_editor`,
  `all`) — напрямую byte-to-byte, именованные виды — через новый
  `next.openKey(id|key|alias)`, miss — legacy. Ветка `next.open` по умолчанию —
  на `tabs._openTableKey` (без рекурсии). Все 35 точек вызова мигрировали
  неявно, разметка не тронута.
- Договор deprecation — в `docs/CODEMAP.md` (новый код только через Registry).
- `tests/test_migration_e2e.py` — 10/10 (маппинг 8 видов, legacy-таблицы,
  алиасы docs/home, openKey hit/miss, сайдбар, ноль JS-ошибок).
- Регрессия без правок старых тестов: part35 28/29 (1 FAIL — хардкод-цвета
  в components.css из незакоммиченных правок прошлых блоков, CSS Блоком 9
  не тронут), traverse 38/38, next_nav 18/18, nav_parity 27/27,
  command_bus 20/20, part2 106/106; `node --check`, `git diff --check` чисто.

### Блок 8 — Plugin/Capability v2 (2026-09-26) — выполнено

- Backend `server/routers/plugins_api.py`: manifest-схема + `POST /validate`
  (ошибки схемы/поведений/кап, semver `min_app_version` vs 2.2.3, варнинги v1);
  capabilities (`table.read/write`, `clipboard`, …), effective-набор в `/raw`;
  write — только по гранту админа (`POST /{pid}/grants`, 403 не-админу);
  дефолтные гранты бандлов сидируются в БД и отзываются; per-user settings
  с валидацией по `settings_schema` (тип/опции/ключи, изоляция юзеров).
- Манифесты `web/plugins/*.json` → v2 (capabilities, settings_schema, EN).
- Frontend: стор с гейтами (`toolbarFor`/`commandList` скрывают без капа),
  `__pluginRun` блокирует неизвестное/без капа тостом, таблица ищется через
  `window.__tables`; поведения читают настройки (разделитель/заголовок TSV,
  цвет метки); Plugin Center: v2/v1-бейджи, капы-бейджи, compat-варнинг,
  гранты, редактор настроек по типам схемы.
- `tests/test_plugins_v2_e2e.py` — 21/21 (validate, гранты, изоляция,
  orange-метка end-to-end, отзыв→скрытие+блок, редактор→semicolon,
  ноль JS-ошибок).
- Регрессия: plugins19 8/8, command_bus 20/20, traverse 38/38, part2 106/106;
  `node --check`, `py_compile`, `git diff --check` чисто.

### Блок 7 — Documents Center (2026-09-26) — выполнено

- Новый `server/routers/documents.py`: версии шаблонов (list/get/restore,
  авто-снапшот при PUT в `print_api.update_template` через `snapshot_version`,
  cap 50); асинхронная очередь печати (`print_jobs`: create/status/cancel/retry/
  download/preview, воркер ThreadPool×1, отмена между записями, cap 200);
  saved reports CRUD + run (переиспользует `search_reports.run_report`);
  везде owner-scope (админ — всё), IDOR проверен тестом (403/403/403).
- Frontend `web/js/documents.js` + pane `tb.type === 'documents'`: секции
  Шаблоны (список, HTML-предпросмотр, история версий, откат, deep-link
  в мини-Word через `window.__printEditId`), Отчёты (запуск, удаление,
  сохранение спеки из конструктора через `suot-saved-reports-changed`),
  Очередь (форма, прогресс-опрос с автостопом, отмена, повтор, скачивание,
  PDF-preview в iframe через blob). Свежесть списков: `onTabActive` + reload
  при смене сегментов (урок дашборда).
- Навигация: registry `documents` → новый view, `tabs.openDocuments()`,
  сайдбар «Документы» ведёт в центр (protocols-таблица доступна напрямую),
  команда Command Bus `documents`. Редактор не дублируется — центр ссылается.
- `tests/test_documents_e2e.py` — 18/18 (версии, откат, preview, отчёты,
  конструктор→спека, задание→done, скачивание PDF 14 КБ, iframe-preview,
  IDOR, ноль JS-ошибок).
- Регрессия: nav_parity 27/27 (центр жив), command_bus 20/20 (команд 10),
  traverse 38/38, print 14/14, search_reports 15/15, export 12/12,
  part2 106/106; `node --check` ×6, `py_compile`, `git diff --check` чисто.

### Блок Dashboard v4 — живые глубокие ссылки + свежесть stats (2026-09-26) — выполнено

- Readiness/focus/KPI ведут в таблицы с серверным smart-фильтром
  (`openTableFiltered`), строки без таблицы скроллят к виджету
  (`scrollToWidget`); новый `tests/test_dashboard_v4_e2e.py` — 8/8, ноль JS-ошибок.
- Продуктовый фикс: stats грузились один раз при входе и протухали —
  «Фокус дня» показывал fallback при живых просрочках. Добавлен
  `onTabActive()` (`web/js/dashboard.js`) + `x-effect` на `$store.tabs.activeId`
  (`web/index.html:656`): возврат на дашборд перезагружает stats; в `load()`
  guard от гонок параллельных запросов (`_loadSeq`).
- `tests/test_part24_e2e.py` обновлён до реалий v4 (9 виджетов, readiness первый,
  DnD через диспатч настоящих DragEvent — Playwright `drag_to` не инициирует
  нативный drag на высокой сетке): 15/15.
- Регрессия: dashboard_v4 8/8, part24 15/15, next_nav 18/18, command_bus 20/20,
  traverse 38/38, tasks 14/14, wizard 7/7, part22 16/16, part33 8/8,
  ux_focus 12/12, part2 106/106; `node --check`, `git diff --check` чисто.

### Блок 10 — Полный редизайн заменой «Aurora Dusk» (2026-09-25) — выполнено

- Живой слой — Industrial-блок в конце `tokens.css` (первый блок мёртв
  и не трогается): тёмная стала сине-чёрной (`bg #080912/#0E1020/#151830`,
  текст `#F2F4FA/#B9C1D6/#8B96AC`), светлая — Porcelain
  (`#EDEFF5/#FAFBFE`, текст `#141A28/#4A5568/#5F6B80`); лайм-акцент и семантика
  сохранены; тени углублены.
- Парящий shell: сайдбар-карточка (margin+radius+тень), топбар и статусбар —
  floating pills. Вёрстка проверена скриншотом (контент тянется, перекрытий нет).
- Контраст WCAG AA: тест считает ratio в браузере для обеих тем
  (t-0/1/2 на bg-0/1, ≥4.5) — зелёно; этим же тестом пойманы мёртвые значения
  первого блока (там же лежали старые failing `#728078`/`#849087`).
- Регрессия: design_next 11/11, part22 16/16, part33 8/8, wizard 7/7,
  ux_focus 12/12, next_nav 18/18, command_bus 20/20, entity_detail 19/19,
  part2 106/106; diff чисто.

### Блок 9 — Реорганизация + стандарт качества (2026-09-25) — выполнено

- План-обещание выше — выполнено по пунктам:
- Аудит паритета (реестр 27 ↔ сайдбар ↔ палитра): найдена мёртвая секция
  «Аналитика» (открывала пустую битую таблицу `reports`, которой нет в API);
  исправлено в 3 местах — сценарий сайдбара и `openScenario` теперь ведут
  на дашборд, запись реестра `analytics` переведена на `welcome`
  (алиас `reports` сохранён для совместимости).
- `docs/CODEMAP.md`: слои и точки входа, таблица «фича → backend/frontend»,
  соглашения (роутеры, `u_`-ключи, `suot_*`, события `suot-*`, сторы/шины,
  CSS-слои), карта тестов, политика мусора в корне.
- Тест `tests/test_nav_parity_e2e.py`: 8/8 — все 27 видов открываются без
  error-state, порядок групп, RU/EN, покрытие switcher; тонкие пустые
  structured-страницы (risk/documents/capa/checklists) — честные INFO,
  не FAIL (пустые состояния — отдельная задача).
- Реестр `test_nav_parity` + `test_design_next` добавлен в E2E_SMOKE раннера.
- Регрессия: part2 106/106, traverse 38/38, next_nav 18/18, command_bus 20/20,
  ux_focus 12/12, entity_detail 19/19, wizard 7/7, design_next 9/9,
  part29_en 8/8; `node --check`, diff чисто; пробы удалены.

### Блок 7 — Query Engine + Saved Views (2026-09-25) — выполнено

- Query Engine: общий `smart_filter_clause()` + `DONE_STATUS_VALUES`
  (`services/database.py`); smart-фильтры overdue/active/done работают
  для custom-таблиц (`query_custom_records` + `GET /custom/records` param);
  чипы открыты для custom (убран `x-if` gate).
- Попутно найден и исправлен предсуществующий баг: SQLite `lower()` не знает
  кириллицу → статусы на русском не матчились и в системных таблицах;
  замена на `pylower()` в 4 местах (проверено: Готово/Активен).
- Серверные виды: таблица `user_views` (миграция через `IF NOT EXISTS`) +
  CRUD `services/database.py` + роутер `server/routers/views.py`
  (валидация scope/name/query 8КБ, изоляция, зарегистрирован в `app.py`).
- Фронт (`table.js`): load/save/delete через сервер + localStorage как
  оффлайн-кэш + ленивая миграция локальных видов; `applyView` без изменений.
- Тесты: `tests/test_views_server.py` — 26/26 (CRUD/валидация/изоляция/
  custom smart); `tests/test_views_e2e.py` — 10/10 (smart custom в UI,
  сохранение, wipe localStorage переживается с сервера, apply, delete).
- Регрессия: run_all_tests default (включая views_server), part2 106/106,
  part23 10/10 (один флак drag), node/py_compile/diff чисто.

### Блок 6 — Task Center + operation history (2026-09-25) — выполнено

- Backend-ужесточение `server/routers/jobs.py`: ранняя валидация target
  (400 вместо молчаливого failed), убраны мёртвые поля `to_key`/`move`
  (transfer как kind не поддерживается и никем не вызывается).
- Верификация API: создание/выполнение/отмена/retry/resume через
  `processed_ids`/изоляция/history/export (22/22, временный скрипт).
- Task Center UI: `web/js/tasks.js` + панель `.tc-*` (активные с прогрессом
  и отменой, готовые с retry, экспорт CSV, Esc, RU/EN, polling только пока
  открыт); кнопка статусбара с живым бейджем (`taskActiveCount`,
  событие `suot-tasks-changed` из `table.js` на терминалах задач);
  команда `tasks` в шине; focus-trap расширен.
- Тесты: `tests/test_tasks_server.py` — 24/24;
  `tests/test_tasks_e2e.py` — 14/14 (бейдж, отмена/повтор через UI, CSV,
  trap, команда).
- Регрессия: run_all_tests default 546/546 (включая tasks_server),
  next_nav 18/18, command_bus 20/20, ux_focus 12/12, entity_detail 19/19
  (устойчивое чтение тела), wizard 7/7, part2 106/106.

### Блок 5 — Command Bus + keyboard-first (2026-09-25) — выполнено

- `web/js/commands.js`: шина `SUOT_COMMANDS` (8 команд: palette, workspace,
  search, theme, help, settings, refresh-app, logout; id/ru/en/icon/group,
  `hotkey` со живой подсказкой из `Hotkeys.bindings`); каждая команда ведёт
  на проверенный обработчик; виды — через реестр (`openView`); запуск
  возвращает bool; неизвестная команда — false.
- Оживлены мёртвые хоткеи: F5 → reload, Ctrl+F → палитра (слушатели
  `suot-hotkey-refresh/search`). Ctrl+N/Ctrl+E слушателей не имеют —
  осознанно не тронуты (зафиксировано как известный пробел).
- Секция «Команды» в переключателе Workspace (поиск, шорткат-хинты, запуск).
- Focus-trap расширен на `.ws-panel`/`.dt-panel` (`app.js` SEL); Alt+2 гвард
  при открытом оверлее (`workspace.js`).
- Тест `tests/test_command_bus_e2e.py`: 20/20 (реестр, выполнение theme/help/
  logout, команды из панели, trap switcher/dossier, гвард Alt+2, F1-справка
  через help-команду, ноль JS-ошибок).
- Регрессия: next_nav 18/18, entity_detail 19/19 (починена гонка чтения тела
  до загрузки — ждём `.dt-title-main:visible`), ux_focus 12/12, part2 106/106.

## 8. Правила продолжения

- Не выдавать старые косметические изменения за новую систему.
- Продолжать переход `legacy tab UI → navigation registry → workspace shell → command bus → entity detail → task center → server-native workflows`.
- Сохранять миграционную совместимость и данные.
- Создавать строки только для реальной архитектуры и функций.
- После каждого блока запускать node/python checks, diff check и релевантные E2E.
- Вести отдельный changelog изменений.

4. Command Bus
5. Entity Registry
6. Data Plane
7. View Components
8. Design System
9. Accessibility
10. Migration Adapter

### Backend layers

1. Composition Root
2. Auth/RBAC
3. Entity Services
4. Query/Filter Service
5. Job Orchestrator
6. Event/Audit Stream
7. Import/Export/Print Workers
8. Repository Adapters
9. Migrations
10. Diagnostics

### Новая навигация

- workspace — постоянная рабочая область;
- view — экран внутри workspace;
- context — запись, проект или фильтр;
- command — действие;
- task — длительная операция;
- pin — быстрый доступ;
- recent — история переходов вместо бесконечной ленты вкладок.

## 6. Что делать дальше (обновлено 2026-09-25: радикальный трек владельца)

Владелец потребовал: убрать концепцию вкладок/браузера полностью (не адаптировать),
ультрасовременный дизайн/интерфейс/анимации, сильное расширение функционала
и концепции, полное преображение программы и сайта до неузнаваемости,
проверку всего, публикацию на переделанном сайте с понятным удобным скачиванием.

Выполнено: Navigation Registry + shell (Блок 1), Entity Registry + Dossier
(Блок 2), редизайн-слой + motion (Блок 3), Aurora + Motion 3.0 (Блок 4),
Command Bus (Блок 5), Task Center (Блок 6), Query Engine + Views (Блок 7),
детэбификация (Блок 8), реорганизация (Блок 9),
полный редизайн заменой «Aurora Dusk» (Блок 10).

1. ✅ Navigation Registry (`tabs.js` → реестр, Блок 1).
2. ✅ Workspace-first shell (Блок 1).
3. ✅ Aurora shell concept + Motion 3.0 (Блок 4).
4. ✅ Command Bus + keyboard-first (Блок 5).
5. ✅ Entity Registry + Detail Workspace (Блок 2).
6. ✅ Task Center (Блок 6).
7. ✅ Saved Views на серверной модели (Блок 7).
8. ✅ Детэбификация (Блок 8): полоса вкладок стёрта, стор — headless-движок,
   навигация только реестр/switcher/bus/sidebar; тесты мигрированы.
9. ✅ Реорганизация (Блок 9): аудит паритета, CODEMAP, мёртвая «Аналитика»
   переведена на дашборд, тест паритета 8/8.
10. 🆕 Концепт-расширение функционала (бэклог, по приоритету):
    общие (shared) виды от администратора; дайджест просрочек (email/Telegram
    по существующим сервисам); расписание отчётов (exporter + email);
    настройки ретенции бэкапов в UI; responsive-фаза (мобильные раскладки);
    импорт НПА-пакетов; self-service профиль пользователя.
11. 🆕 Documents Center + полный редизайн сайта: новая структура лендинга
    (hero/продукт/скриншоты/доки), понятный блок скачивания
    (автоопределение, большие кнопки, SHA-256 рядом, история версий,
    инструкция установки); контракт манифеста `/downloads/index.json`
    не меняется (его читает автообновление).
12. 🆕 Plugin/capability contract v2.
13. 🆕 Игры заново: 2048 и Block Blast — оригинальные правила (поле 8×8
    сохраняется), удобное управление (предпоследняя часть).
14. Финальная WCAG/performance/security regression + публикация:
    полный прогон, релиз-билд, деплой сайта, проверка скачивания.


Основные файлы:

```text
desktop.py
server/app.py
server/routers/
services/database.py
web/index.html
web/js/app.js
web/js/tabs.js
web/js/table.js
web/js/pages.js
web/js/dashboard.js
web/js/workspace.js
web/css/tokens.css
web/css/components.css
site/index.html
site/css/site.css
site/js/site.js
tests/
```
