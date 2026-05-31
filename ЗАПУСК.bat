@echo off
chcp 65001 > nul
echo.
echo  SMM-команда Дмитрия Сучкова
echo  ================================
echo  Запускаю агентов...
echo.

cd /d "%~dp0"

pip install -r requirements.txt -q

streamlit run app.py

pause
