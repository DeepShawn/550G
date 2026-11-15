@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo 未检测到 Python。请先安装 Python 3.10+，安装时勾选 Add Python to PATH。
 echo https://www.python.org/downloads/windows/
 pause
 exit /b 1
)
py -m pip install -r requirements.txt
if errorlevel 1 (echo 依赖安装失败，请检查网络后重试。& pause & exit /b 1)
py main.py
if errorlevel 1 pause
