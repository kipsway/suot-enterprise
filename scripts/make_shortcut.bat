@echo off
chcp 65001 >nul
setlocal
set NAME=ОхранаТруда Про
set EXE=%~dp0SUOT_Neo.exe
if not exist "%EXE%" set EXE=%~dp0..\SUOT_Neo\SUOT_Neo.exe
if not exist "%EXE%" (
    echo [!] SUOT_Neo.exe не найден рядом со скриптом.
    pause & exit /b 1
)

echo Создаю ярлыки «%NAME%»…

powershell -NoProfile -Command ^
 "$ws = New-Object -ComObject WScript.Shell;" ^
 "$lnk = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\%NAME%.lnk');" ^
 "$lnk.TargetPath = '%EXE%'; $lnk.WorkingDirectory = (Split-Path '%EXE%');" ^
 "$lnk.IconLocation = '%EXE%,0'; $lnk.Description = 'ОхранаТруда Про — система управления охраной труда';" ^
 "$lnk.Save();" ^
 "$sm = [Environment]::GetFolderPath('StartMenu') + '\Programs';" ^
 "New-Item -ItemType Directory -Force -Path ($sm + '\ОхранаТруда Про') | Out-Null;" ^
 "$l2 = $ws.CreateShortcut($sm + '\ОхранаТруда Про\%NAME%.lnk');" ^
 "$l2.TargetPath = '%EXE%'; $l2.WorkingDirectory = (Split-Path '%EXE%');" ^
 "$l2.IconLocation = '%EXE%,0'; $l2.Save();"

echo Готово: ярлык на рабочем столе и в меню «Пуск → ОхранаТруда Про».
pause
