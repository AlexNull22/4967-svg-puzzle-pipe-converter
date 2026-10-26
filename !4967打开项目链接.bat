@echo off
chcp 65001 >nul
setlocal
set "TASK4967_URL=https://www.upwork.com/jobs/Developer-Needed-Simple-Windows-Tool-Convert-SVG-Railway-Puzzles-into-Different-Artwork_~022112069732945377611/"
if exist "%ProgramFiles%\Mozilla Firefox\firefox.exe" (
    start "" "%ProgramFiles%\Mozilla Firefox\firefox.exe" "%TASK4967_URL%"
    exit /b 0
)
if exist "%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe" (
    start "" "%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe" "%TASK4967_URL%"
    exit /b 0
)
if exist "%LOCALAPPDATA%\Mozilla Firefox\firefox.exe" (
    start "" "%LOCALAPPDATA%\Mozilla Firefox\firefox.exe" "%TASK4967_URL%"
    exit /b 0
)
where firefox.exe >nul 2>nul
if errorlevel 1 (
    echo 未找到已安装的Firefox，请安装后重试。本脚本不会自动下载。
    exit /b 1
)
start "" firefox.exe "%TASK4967_URL%"
exit /b 0
