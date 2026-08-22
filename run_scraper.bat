@echo off
cd /d C:\Users\ADMIN\exchange-rate-bot
call venv\Scripts\activate.bat
python scrape_exchange_rate.py >> log.txt 2>&1