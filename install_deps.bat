@echo off
chcp 65001 >nul
echo Установка зависимостей СУОТ Enterprise...
pip install --upgrade pip
pip install PyQt5 python-docx cryptography vosk openpyxl pyzbar qrcode opencv-python schedule python-telegram-bot pillow beautifulsoup4 sseclient-py pyinstaller
echo Готово!
pause
