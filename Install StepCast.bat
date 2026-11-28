@echo off
REM ============================================================================
REM  Install StepCast  -  double-click this file once.
REM  Installs what StepCast needs (Python, ffmpeg, a few Python libraries)
REM  and puts a StepCast icon on your desktop and in the Start menu.
REM
REM  StepCast 1.0 - Dr Sivakumar Manickam <skumar@staff.odc.edu.om>, Oman Dental College
REM  Developed with the help of Claude (Anthropic) as an AI coding assistant.
REM ============================================================================
setlocal EnableExtensions EnableDelayedExpansion
title Installing StepCast
cd /d "%~dp0"
color 0F
echo.
echo   ==========================================================
echo     StepCast - installation
echo     This takes 2-5 minutes. Please keep this window open.
echo   ==========================================================
echo.

REM ---------------------------------------------------------------- 1. Python
echo [1/4] Checking for Python...
set "PY="
call :findpython
if not defined PY (
    echo       Python is not installed. Installing it now ^(this can take a few minutes^)...
    where winget >nul 2>nul
    if errorlevel 1 goto :nowinget_python
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
    call :findpython
)
if not defined PY goto :nopython
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo       Your Python is too old. StepCast needs Python 3.10 or newer.
    goto :nopython
)
echo       OK  ^(%PY%^)

REM ---------------------------------------------------------------- 2. libraries
echo.
echo [2/4] Installing StepCast's libraries...
"%PY%" -m pip install --disable-pip-version-check --quiet --upgrade pip >nul 2>nul
"%PY%" -m pip install --disable-pip-version-check --quiet -r "app\requirements.txt"
if errorlevel 1 (
    echo.
    echo   !! The libraries could not be installed. Check your internet connection
    echo      and run "Install StepCast.bat" again.
    goto :fail
)
echo       OK

REM ---------------------------------------------------------------- 3. ffmpeg
echo.
echo [3/4] Checking for ffmpeg ^(records and converts the video^)...
call :checkffmpeg
if errorlevel 1 (
    echo       ffmpeg is not installed. Installing it now...
    where winget >nul 2>nul
    if errorlevel 1 goto :nowinget_ffmpeg
    winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements --silent
    call :checkffmpeg
    if errorlevel 1 goto :nowinget_ffmpeg
)
echo       OK

REM ---------------------------------------------------------------- 4. shortcuts
echo.
echo [4/4] Adding StepCast to your desktop and Start menu...
for /f "delims=" %%i in ('call "%PY%" -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%i"
if not exist "%PYW%" set "PYW=%PY%"
> "app\python_path.txt" echo %PYW%
set "HOME=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  $s = $w.CreateShortcut((Join-Path $dir 'StepCast.lnk'));" ^
  "  $s.TargetPath = $env:PYW;" ^
  "  $s.Arguments = [char]34 + (Join-Path $env:HOME 'app\record.py') + [char]34;" ^
  "  $s.WorkingDirectory = $env:HOME;" ^
  "  $s.IconLocation = (Join-Path $env:HOME 'app\logo.ico');" ^
  "  $s.Description = 'StepCast - interactive screen lessons';" ^
  "  $s.Save() }" >nul 2>nul
if errorlevel 1 (
    echo       Could not add the shortcuts - you can still start StepCast with "Start StepCast.bat".
) else (
    echo       OK
)

echo.
echo   ==========================================================
echo     StepCast is ready.
echo     Start it from the StepCast icon on your desktop,
echo     or double-click "Start StepCast.bat" in this folder.
echo   ==========================================================
echo.
choice /c YN /m "  Start StepCast now"
if errorlevel 2 goto :eof
start "" "%PYW%" "%~dp0app\record.py"
goto :eof

REM ============================================================================ helpers
:findpython
set "PY="
for %%v in (313 312 311 310) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
    if not defined PY if exist "%ProgramFiles%\Python%%v\python.exe" set "PY=%ProgramFiles%\Python%%v\python.exe"
)
if not defined PY (
    for /f "delims=" %%p in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%p"
)
if not defined PY (
    for /f "delims=" %%p in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%p"
)
exit /b 0

:checkffmpeg
"%PY%" -c "import sys; sys.path.insert(0, 'app'); import paths; sys.exit(0 if paths.find_tool('ffmpeg') and paths.find_tool('ffprobe') else 1)"
exit /b %errorlevel%

:nowinget_python
echo.
echo   !! Python could not be installed automatically.
echo      1. Go to https://www.python.org/downloads/windows/ and run the latest Python 3 installer.
echo         On the first screen tick "Add python.exe to PATH", click "Customize installation",
echo         then tick "Install Python for all users" ^(needs administrator rights^).
echo      2. Then double-click "Install StepCast.bat" again. See README.md, "Install", for details.
goto :fail

:nopython
echo.
echo   !! Python was not found.
echo      1. Go to https://www.python.org/downloads/windows/ and run the latest Python 3 installer.
echo         On the first screen tick "Add python.exe to PATH", click "Customize installation",
echo         then tick "Install Python for all users" ^(needs administrator rights^).
echo      2. Then double-click "Install StepCast.bat" again. See README.md, "Install", for details.
goto :fail

:nowinget_ffmpeg
echo.
echo   !! ffmpeg could not be installed automatically.
echo      1. Download "ffmpeg-release-essentials.zip" from https://www.gyan.dev/ffmpeg/builds/
echo      2. Unzip it, rename the folder to "ffmpeg" and move it to C:\ so that
echo         C:\ffmpeg\bin\ffmpeg.exe exists ^(needs administrator rights^).
echo         Or copy ffmpeg.exe and ffprobe.exe from its "bin" folder into:
echo         %~dp0app\tools\
echo      3. Then double-click "Install StepCast.bat" again. See README.md, "Install", for details.
if not exist "app\tools" mkdir "app\tools"
goto :fail

:fail
echo.
pause
exit /b 1
