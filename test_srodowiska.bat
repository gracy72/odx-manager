@echo off
rem =====================================================================
rem  test_srodowiska.bat - diagnostyka startera ODX
rem  Sprawdza: Python + Tkinter, wykrycie ODX, dzialanie run.bat --version
rem =====================================================================
setlocal
cd /d "%~dp0"
title ODX - test srodowiska

echo ================================================================
echo  1. Python 3 z Tkinterem
echo ================================================================
call "%~dp0_python_path.bat" console
if not defined ODX_PY (
    echo [BLAD] Nie znaleziono Pythona 3 z Tkinterem.
    echo        Zainstaluj Python 3 z python.org ^(opcja "tcl/tk and IDLE"^)
    echo        albo ustaw: set ODX_GUI_PYTHON=C:\sciezka\python.exe
) else (
    echo [OK] Interpreter: %ODX_PY%
    "%ODX_PY%" -c "import sys, tkinter; print('     wersja Pythona:', sys.version.split()[0]); print('     Tkinter Tk   :', tkinter.TkVersion)"
)

echo.
echo ================================================================
echo  2. Instalacja ODX
echo ================================================================
call "%~dp0_find_odx.bat"
if not defined ODX_DIR (
    echo [BLAD] Nie znaleziono katalogu ODX z run.bat.
    echo        Ustaw: set ODX_HOME=C:\sciezka\do\ODX
    goto :koniec
)
echo [OK] Katalog ODX: %ODX_DIR%
for /f "usebackq delims=" %%v in ("%ODX_DIR%\VERSION") do echo      Wersja    : %%v

echo.
echo ================================================================
echo  3. Uruchomienie silnika (run.bat --version)
echo ================================================================
call "%ODX_DIR%\run.bat" --version
if errorlevel 1 (
    echo [BLAD] run.bat --version zakonczyl sie kodem bledu.
) else (
    echo [OK] Silnik odpowiada.
)

echo.
echo ================================================================
echo  4. Konfiguracja GUI
echo ================================================================
echo      Plik konfiguracji: %APPDATA%\odx-gui\config.json
if exist "%APPDATA%\odx-gui\config.json" (echo      [OK] istnieje) else (echo      [--] jeszcze nie utworzony - powstanie po pierwszym starcie GUI)

:koniec
echo.
pause
endlocal
