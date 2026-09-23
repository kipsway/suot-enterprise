@echo off
chcp 65001 >nul
echo СУОТ Enterprise — Git Push
echo ===========================
set /p msg="Commit message: "
git add -A
git commit -m "%msg%"
git push
echo Готово!
pause
