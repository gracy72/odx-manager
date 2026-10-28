@echo off
rem =====================================================================
rem  odx.bat - uruchamianie ODX z linii polecen (bez GUI).
rem
rem  Uzycie:
rem     odx.bat "C:\Projekty\dzialka" [opcje ODX...]
rem     odx.bat "dzialka" --project-path "C:\Projekty" [opcje ODX...]
rem     odx.bat --help
rem
rem  Gdy pierwszy argument jest istniejacym katalogiem, skrypt sam
rem  rozbija go na nazwe zbioru + --project-path (tak jak wymaga run.py).
rem =====================================================================
setlocal EnableExtensions

call "%~dp0_find_odx.bat"
if not defined ODX_DIR goto :noodx
if "%~1"=="" goto :usage

set "PROJ=%~1"

rem katalog? -> zamien na "nazwa" + --project-path "rodzic"
if not exist "%PROJ%\" goto :passthrough

set "PABS="
set "PDIR="
set "PNAME="
for %%i in ("%PROJ%") do set "PABS=%%~fi"
for %%i in ("%PABS%\..") do set "PDIR=%%~fi"
for %%i in ("%PABS%") do set "PNAME=%%~nxi"
shift

echo [i] ODX    : %ODX_DIR%
echo [i] Projekt: %PNAME%  ^(%PDIR%^)
echo.
call "%ODX_DIR%\run.bat" "%PNAME%" --project-path "%PDIR%" %1 %2 %3 %4 %5 %6 %7 %8 %9
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%

:passthrough
call "%ODX_DIR%\run.bat" %*
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%

:noodx
echo.
echo [BLAD] Nie znaleziono instalacji ODX (katalogu z run.bat).
echo Ustaw zmienna srodowiskowa ODX_HOME, np.:
echo     set ODX_HOME=C:\Users\...\Portable\ODX
echo.
endlocal & exit /b 1

:usage
echo.
echo Uzycie: odx.bat "C:\Projekty\dzialka" [opcje ODX...]
echo.
echo Przyklady:
echo     odx.bat "C:\Projekty\dzialka" --fast-orthophoto
echo     odx.bat "C:\Projekty\dzialka" --dsm --dtm --max-concurrency 4
echo     odx.bat --help
echo.
echo Silnik ODX: %ODX_DIR%
endlocal & exit /b 1
