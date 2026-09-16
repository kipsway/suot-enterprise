@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === ОхранаТруда Про — первичная настройка ===

where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установите Python 3.10+ с python.org
    echo          и отметьте "Add python.exe to PATH".
    pause & exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo [ОШИБКА] Нужен Python 3.10 или новее.
    python --version
    pause & exit /b 1
)

if not exist .venv (
    echo Создаю виртуальное окружение .venv …
    python -m venv .venv || (pause & exit /b 1)
)

call .venv\Scripts\activate.bat

echo Устанавливаю зависимости …
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q || (pause & exit /b 1)

echo.
echo === Готово! Запускаю приложение ===
python desktop.py
pause
