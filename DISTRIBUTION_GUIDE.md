# Руководство по распространению программы СУОТ Enterprise

## О программе
- **Язык**: Python 3.10+
- **Графика**: PyQt5
- **База данных**: SQLite (один файл)
- **Код**: ~11 900 строк, ~530 КБ

---

## Способ 1: Сборка в один EXE‑файл (рекомендуется)

Самый простой способ для передачи пользователям.  
На выходе — один `.exe` файл, который работает на **чистой Windows** без установки Python.

### Что нужно сделать НА ВАШЕМ компьютере (один раз)

#### Шаг 1. Установить Python 3.10 или новее

1. Скачайте установщик: https://www.python.org/downloads/
2. Запустите `python-3.X.X-amd64.exe`
3. **ВАЖНО:** внизу окна поставьте галочку **"Add Python to PATH"**
4. Нажмите "Install Now"

Проверьте установку, открыв **командную строку (cmd.exe)** и выполнив:

```cmd
python --version
```

Должно показать: `Python 3.10.x` или выше.

#### Шаг 2. Установить необходимые библиотеки

В той же командной строке выполните:

```cmd
pip install PyQt5 requests pyinstaller
```

Если вы используете прокси или зеркало PyPI:

```cmd
pip install -i https://pypi.org/simple/ PyQt5 requests pyinstaller
```

#### Шаг 3. Перейти в папку с программой

```cmd
cd C:\Users\ВашеИмя\Desktop\program
```

Замените путь на тот, где лежит `suot_platform.py`.

#### Шаг 4. Собрать EXE

```cmd
pyinstaller --onefile --windowed --name "SUOT_Enterprise" suot_platform.py
```

**Параметры:**
- `--onefile` — собирает всё в один `.exe`
- `--windowed` — скрывает консоль (нет чёрного окна)
- `--name "SUOT_Enterprise"` — имя выходного файла
- `suot_platform.py` — ваш исходный код

#### Шаг 5. Найти готовый файл

Готовый `.exe` появится в папке:

```
dist\SUOT_Enterprise.exe
```

Размер файла: ~30–50 МБ (из-за встроенного Python + PyQt5).

#### Шаг 6. (Опционально) Добавить иконку

Если у вас есть файл `icon.ico`:

```cmd
pyinstaller --onefile --windowed --icon=icon.ico --name "SUOT_Enterprise" suot_platform.py
```

---

### Что делать, если сборка не удалась

**Ошибка `pyinstaller` не найдена:**
```cmd
pip install pyinstaller
```

**Ошибка `No module named PyQt5`:**
```cmd
pip install PyQt5
```

**Ошибка `requests` не найдена:**
```cmd
pip install requests
```

**Ошибка слишком длинного пути (Windows):**
Попробуйте переместить исходный файл ближе к корню диска, например:
```cmd
C:\build\suot_platform.py
```

**Предупреждение `lib not found` для `pywintypes` и т.п.:**
Обычно это некритично для работы программы. Игнорируйте.

---

### Как передать пользователю

Просто скопируйте файл `dist\SUOT_Enterprise.exe` на флешку, отправьте по почте или через облако (Яндекс.Диск, Google Drive, TG).

Пользователю ничего устанавливать **не нужно** — он просто запускает `.exe`.

База данных (`suot_data.db`) и папка `media/` создадутся автоматически при первом запуске.

---

### Как обновить программу

Если вы изменили код:

1. Удалите старую папку `build\` и `SUOT_Enterprise.spec` (если есть)
2. Повторите шаги 3–5 (сборка)
3. Разошлите новый `SUOT_Enterprise.exe` пользователям
4. Пользователь просто заменяет `.exe` — его база данных и настройки сохраняются

---

### Важные файлы программы

| Файл / Папка          | Назначение                                     |
|------------------------|------------------------------------------------|
| `SUOT_Enterprise.exe`  | Сама программа                                 |
| `suot_data.db`         | База данных (создаётся автоматически)          |
| `media/`               | Фото сотрудников / нарушений (создаётся автом.)|
| `backups/`             | Резервные копии БД (создаются автоматически)   |

---

## Способ 2: Portable-папка (без установки)

Собрать папку с программой и всеми зависимостями (без сжатия в один файл):

```cmd
pyinstaller --onedir --windowed --name "SUOT_Enterprise" suot_platform.py
```

После сборки в `dist/SUOT_Enterprise/` появится:
```
SUOT_Enterprise.exe
_base_module.pyd
...
```

Просто скопируйте всю папку `dist/SUOT_Enterprise/` пользователю.

**Плюс:** Запускается быстрее (не нужно распаковывать).
**Минус:** Нужно передавать папку, а не один файл.

---

## Способ 3: Запуск через Python (требуется установленный Python у пользователя)

Подходит, если пользователь готов установить Python самостоятельно.

### На компьютере пользователя

```cmd
:: 1. Установить Python 3.10+ (https://python.org)
:: 2. Установить библиотеки
pip install PyQt5 requests

:: 3. Запустить программу
python suot_platform.py
```

### Упрощённый запуск (start.bat)

Создайте файл `start.bat` рядом с `suot_platform.py`:

```batch
@echo off
title СУОТ Enterprise
python suot_platform.py
pause
```

Теперь пользователь может просто запускать `start.bat`.

---

## Способ 4: Inno Setup (установщик Windows)

Для профессионального распространения — создание `.exe` установщика.

### Шаг 1. Собрать portable-папку (см. Способ 2)

```cmd
pyinstaller --onedir --windowed --name "SUOT_Enterprise" suot_platform.py
```

### Шаг 2. Установить Inno Setup

Скачайте с https://jrsoftware.org/isdl.php и установите.

### Шаг 3. Создать скрипт `setup.iss`

```pascal
[Setup]
AppName=СУОТ Enterprise
AppVersion=1.0
DefaultDirName={pf}\SUOT_Enterprise
OutputDir=installer
OutputBaseFilename=SUOT_Enterprise_Setup
UninstallDisplayIcon={app}\SUOT_Enterprise.exe

[Files]
Source: "dist\SUOT_Enterprise\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\СУОТ Enterprise"; Filename: "{app}\SUOT_Enterprise.exe"
Name: "{commondesktop}\СУОТ Enterprise"; Filename: "{app}\SUOT_Enterprise.exe"

[Run]
Filename: "{app}\SUOT_Enterprise.exe"; Description: "Запустить СУОТ Enterprise"; Flags: postinstall nowait skipifsilent
```

### Шаг 4. Собрать установщик

Откройте `setup.iss` в Inno Setup и нажмите `Build → Compile`.

Готовый `SUOT_Enterprise_Setup.exe` появится в папке `installer/`.

---

## Перенос данных на другой компьютер

Если пользователь переходит на новый ПК со своей базой данных:

1. Скопируйте файл `suot_data.db` (вся база: сотрудники, нарушения, настройки, заметки, напоминания)
2. Скопируйте папку `media/` (фотографии, если есть)
3. Скопируйте программу (`SUOT_Enterprise.exe` или `suot_platform.py`)
4. Запустите программу — она автоматически подхватит существующую БД

---

## Разрешение проблем

| Проблема                              | Решение                                          |
|---------------------------------------|--------------------------------------------------|
| Антивирус удаляет `.exe`              | Добавьте файл в исключения антивируса            |
| "Отсутствует MSVCR140.dll"            | Установите "Microsoft Visual C++ Redistributable"|
| Программа не запускается, нет ошибок  | Запустите из cmd.exe и посмотрите сообщение      |
| База данных повреждена                | Удалите `suot_data.db` — создастся новая         |
