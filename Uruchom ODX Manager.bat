@echo off
rem =====================================================================
rem  ODX Manager - uruchomienie GUI (bez okna konsoli)
rem  Interpreter Pythona jest wykrywany raz i zapamietywany w
rem  _python_cache.txt (kolejne starty nie uruchamiaja PowerShella).
rem  Mozna go wskazac recznie:  set ODX_GUI_PYTHON=C:\sciezka\python.exe
rem  Wlasne flagi Pythona:      set ODX_PY_FLAGS=-X utf8
rem =====================================================================
setlocal
cd /d "%~dp0"
title ODX Manager

call "%~dp0_python_path.bat" gui
if not defined ODX_PY goto :nopython

rem -E -s: pomija sitecustomize/filtry user-site (na tej maszynie .pth
rem z pip_system_certs dokladal ~0,7 s do startu kazdego Pythona).
rem GUI korzysta wylacznie z biblioteki standardowej, wiec to bezpieczne.
if not defined ODX_PY_FLAGS set "ODX_PY_FLAGS=-E -s"

start "" "%ODX_PY%" %ODX_PY_FLAGS% "%~dp0gui\odx_gui.py" %*
exit /b 0

:nopython
echo.
echo [BLAD] Nie znaleziono Pythona 3 z modulem Tkinter.
echo.
echo Zainstaluj Python 3 ze strony python.org (opcja "tcl/tk and IDLE"),
echo albo wskaz istniejacy interpreter:
echo.
echo     set ODX_GUI_PYTHON=C:\sciezka\do\python.exe
echo.
echo i uruchom ten plik ponownie. Diagnostyka: test_srodowiska.bat
echo.
pause
exit /b 1
