@echo off
rem =====================================================================
rem  ODX Manager - uruchomienie GUI w oknie konsoli (widoczne komunikaty,
rem  przydatne gdy okno GUI nie startuje).
rem =====================================================================
setlocal
cd /d "%~dp0"
title ODX Manager - konsola

call "%~dp0_python_path.bat" console
if not defined ODX_PY goto :nopython

echo [i] Interpreter: %ODX_PY%
echo.
"%ODX_PY%" "%~dp0gui\odx_gui.py" %*
echo.
echo [i] GUI zakonczyl prace (kod %ERRORLEVEL%).
pause
exit /b 0

:nopython
echo.
echo [BLAD] Nie znaleziono Pythona 3 z modulem Tkinter.
echo Zainstaluj Python 3 (python.org, opcja "tcl/tk and IDLE") albo ustaw:
echo     set ODX_GUI_PYTHON=C:\sciezka\do\python.exe
echo.
pause
exit /b 1
