@echo off
rem ---------------------------------------------------------------------
rem  _find_odx.bat - ustawia zmienna ODX_DIR na katalog instalacji ODX
rem  (ten, ktory zawiera run.bat i run.py).
rem
rem  Uzycie:   call "%~dp0_find_odx.bat"
rem  Brak setlocal -> zmienna ODX_DIR zostaje w sesji wywolujacego.
rem  Kolejnosc: ODX_HOME -> katalog nadrzedny startera -> rejestr ->
rem             C:\ODX -> %ProgramFiles%\ODX -> %LOCALAPPDATA%\Programs\ODX
rem ---------------------------------------------------------------------

set "ODX_DIR="

if defined ODX_HOME call :take "%ODX_HOME%"
if defined ODX_DIR goto :eof

rem starter lezy w <ODX>\ODX-Starter-Windows - najczestszy uklad
for %%i in ("%~dp0..") do call :take "%%~fi"
if defined ODX_DIR goto :eof

rem instalator Inno Setup zapisuje InstallLocation
for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{443998BA-9F8F-4A69-9A96-0D8FBC8C6394}_is1" /v InstallLocation 2^>nul ^| findstr /i "InstallLocation"') do call :take "%%b"
if defined ODX_DIR goto :eof
for /f "tokens=2,*" %%a in ('reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\{443998BA-9F8F-4A69-9A96-0D8FBC8C6394}_is1" /v InstallLocation 2^>nul ^| findstr /i "InstallLocation"') do call :take "%%b"
if defined ODX_DIR goto :eof

if exist "C:\ODX\run.bat" call :take "C:\ODX"
if defined ODX_DIR goto :eof
if exist "%ProgramFiles%\ODX\run.bat" call :take "%ProgramFiles%\ODX"
if defined ODX_DIR goto :eof
if exist "%LOCALAPPDATA%\Programs\ODX\run.bat" call :take "%LOCALAPPDATA%\Programs\ODX"
goto :eof

:take
if not exist "%~1\run.bat" goto :eof
if not exist "%~1\run.py" goto :eof
for %%i in ("%~1") do set "ODX_DIR=%%~fi"
goto :eof
