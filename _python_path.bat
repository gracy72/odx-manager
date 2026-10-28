@echo off
rem ---------------------------------------------------------------------
rem  _python_path.bat - ustawia ODX_PY na interpreter Python 3 z Tkinterem
rem
rem  Uzycie:   call "%~dp0_python_path.bat" [gui|console]
rem              gui     -> pythonw.exe (bez okna konsoli)
rem              console -> python.exe
rem
rem  Kolejnosc (od najtanszej):
rem    1) zmienna ODX_GUI_PYTHON (jawne wskazanie uzytkownika)
rem    2) _python_cache.txt - sciezka zapamietana przy poprzednim starcie
rem    3) szybkie sondowanie typowych katalogow (czysty cmd, bez PowerShella)
rem    4) pelne wyszukiwanie przez _find_python.ps1 (tylko gdy 1-3 zawiodly)
rem
rem  Brak setlocal -> ODX_PY zostaje w sesji wywolujacego.
rem  Aby wymusic ponowne wykrywanie, usun plik _python_cache.txt.
rem ---------------------------------------------------------------------

set "ODX_PY="
set "_ODX_MODE=%~1"
if not defined _ODX_MODE set "_ODX_MODE=gui"
set "_ODX_CACHE=%~dp0_python_cache.txt"

rem --- 1) jawne wskazanie uzytkownika -----------------------------------
if defined ODX_GUI_PYTHON call :take "%ODX_GUI_PYTHON%"
if defined ODX_PY goto :pick

rem --- 2) pamiec podreczna ----------------------------------------------
if exist "%_ODX_CACHE%" for /f "usebackq delims=" %%i in ("%_ODX_CACHE%") do (
    if not defined ODX_PY call :take "%%i"
)
if defined ODX_PY goto :pick

rem --- 3) szybkie sondowanie bez uruchamiania PowerShella ---------------
call :probe "%LOCALAPPDATA%\Programs\Python"
call :probe "%ProgramFiles%"
call :probe "%ProgramFiles(x86)%"
call :probe "C:\"
if defined ODX_PY goto :pick

rem --- 4) pelne wyszukiwanie (PowerShell) - ostatnia szansa --------------
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_find_python.ps1" %_ODX_MODE%`) do (
    if not defined ODX_PY call :take "%%i"
)
if not defined ODX_PY goto :eof

:pick
rem dopasuj python.exe / pythonw.exe do trybu pracy
for %%i in ("%ODX_PY%") do (
    set "_ODX_PDIR=%%~dpi"
    set "_ODX_PLEAF=%%~nxi"
)
if /i "%_ODX_MODE%"=="gui" (
    if /i not "%_ODX_PLEAF%"=="pythonw.exe" (
        if exist "%_ODX_PDIR%pythonw.exe" set "ODX_PY=%_ODX_PDIR%pythonw.exe"
    )
) else (
    if /i not "%_ODX_PLEAF%"=="python.exe" (
        if exist "%_ODX_PDIR%python.exe" set "ODX_PY=%_ODX_PDIR%python.exe"
    )
)

rem zapamietaj wynik, zeby kolejne uruchomienia nie szukaly od nowa
echo %ODX_PY%>"%_ODX_CACHE%" 2>nul
goto :eof

rem --- pomocnicze -------------------------------------------------------
:probe
rem %~1 = katalog nadrzedny; sprawdza Python3* w srodku i sam katalog
if "%~1"=="" goto :eof
if not exist "%~1\" goto :eof
for /d %%d in ("%~1\Python3*") do call :take "%%~fd\pythonw.exe"
for /d %%d in ("%~1\Python3*") do call :take "%%~fd\python.exe"
call :take "%~1\pythonw.exe"
call :take "%~1\python.exe"
goto :eof

:take
rem %~1 = kandydat na sciezke interpretera; przyjmuje pierwszy sprawny
if defined ODX_PY goto :eof
if "%~1"=="" goto :eof
call :valid "%~1"
goto :eof

:valid
rem odrzuca atrape ze Sklepu MS i instalacje bez Tkintera
set "_ODX_T=%~1"
if not exist "%_ODX_T%" goto :eof
if not "%_ODX_T:\WindowsApps\=%"=="%_ODX_T%" goto :eof
for %%i in ("%_ODX_T%") do set "_ODX_TDIR=%%~dpi"
if not exist "%_ODX_TDIR%Lib\tkinter\__init__.py" goto :eof
set "ODX_PY=%_ODX_T%"
goto :eof
