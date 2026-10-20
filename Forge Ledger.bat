@echo off
rem Starts Daeva Forge Beta (live prices + CP tracker) and opens it in your browser.
rem Keep this window open: Combat Power is recorded every 30 minutes while it runs.
title Daeva Forge Beta
cd /d "%~dp0"
python serve.py
pause
