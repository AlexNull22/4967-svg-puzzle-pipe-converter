@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "%~dp04967_新转换结果" (
    echo 输出位置4967_新转换结果已存在，拒绝覆盖。请保留结果并改用新的输出目录。
    exit /b 1
)
set "TASK4967_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%TASK4967_PYTHON%" goto TASK4967_TRY_PY
"%TASK4967_PYTHON%" -X utf8 -B -c "import sys,xml.etree.ElementTree,json,hashlib,html; assert sys.version_info[:2]==(3,12)" >nul 2>nul
if errorlevel 1 goto TASK4967_TRY_PY
"%TASK4967_PYTHON%" -X utf8 -B "%~dp04967_转换引擎.py" --input "%~dp04967_原题.svg" "%~dp04967_答案.svg" --output "%~dp04967_新转换结果"
set "TASK4967_EXIT=%ERRORLEVEL%"
goto TASK4967_DONE

:TASK4967_TRY_PY
where py.exe >nul 2>nul
if errorlevel 1 goto TASK4967_MISSING
py -3.12 -X utf8 -B -c "import sys,xml.etree.ElementTree,json,hashlib,html; assert sys.version_info[:2]==(3,12)" >nul 2>nul
if errorlevel 1 goto TASK4967_MISSING
py -3.12 -X utf8 -B "%~dp04967_转换引擎.py" --input "%~dp04967_原题.svg" "%~dp04967_答案.svg" --output "%~dp04967_新转换结果"
set "TASK4967_EXIT=%ERRORLEVEL%"
goto TASK4967_DONE

:TASK4967_MISSING
echo 未找到含所需标准库的已安装Python 3.12，请按4967_依赖说明.txt准备环境。
echo 本脚本不会下载或安装软件，不需要账号或云SDK。
exit /b 1

:TASK4967_DONE
if not "%TASK4967_EXIT%"=="0" echo 转换未完成，请查看上方错误；原始SVG不会被本脚本覆盖。
exit /b %TASK4967_EXIT%
