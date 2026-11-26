@echo off
REM ============================================================================
REM  Start StepCast  (or use the StepCast icon on your desktop)
REM  StepCast 1.0 - Dr Sivakumar Manickam <skumar@staff.odc.edu.om>, Oman Dental College
REM  Developed with the help of Claude (Anthropic) as an AI coding assistant.
REM ============================================================================
cd /d "%~dp0"
if not exist "app\python_path.txt" (
    echo StepCast is not installed yet.
    echo Please double-click "Install StepCast.bat" first.
    echo.
    pause
    exit /b 1
)
set /p PYW=<"app\python_path.txt"
if not exist "%PYW%" (
    echo Python was not found. Please double-click "Install StepCast.bat" again.
    echo.
    pause
    exit /b 1
)
start "" "%PYW%" "%~dp0app\record.py"
