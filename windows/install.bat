@echo off
setlocal EnableDelayedExpansion
rem kauz-tools-csgo installer/updater: rerun after unzipping a new version. Usage: install.bat [path\to\game\csgo\cfg]
set "REL=steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg"
set "SRC=%~dp0cfg"
set "CFG=%~1"
if defined CFG goto check

for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Valve\Steam" /v SteamPath 2^>nul') do set "STEAM=%%b"
if not defined STEAM goto ask
set "STEAM=!STEAM:/=\!"
if exist "!STEAM!\!REL!" set "CFG=!STEAM!\!REL!" & goto check
rem other Steam libraries: lines like   "path"   "D:\\SteamLibrary"
for /f tokens^=4^ delims^=^" %%p in ('findstr /c:"\"path\"" "!STEAM!\steamapps\libraryfolders.vdf" 2^>nul') do (
    set "LIB=%%p"
    set "LIB=!LIB:\\=\!"
    if exist "!LIB!\!REL!" set "CFG=!LIB!\!REL!"
)

:check
if defined CFG if exist "!CFG!\" goto install
:ask
set "CFG="
set /p "CFG=CS2 cfg folder not found. Paste the path to ...\game\csgo\cfg: "
goto check

:install
if exist "!CFG!\kt" rmdir /s /q "!CFG!\kt"
xcopy /e /i /q "%SRC%\kt" "!CFG!\kt" >nul
for %%f in ("%SRC%\gamemode_*_server.cfg") do (
    if not exist "!CFG!\%%~nxf" (
        copy /y "%%f" "!CFG!\%%~nxf" >nul
    ) else (
        findstr /x /c:"kt_onload" "!CFG!\%%~nxf" >nul || (echo.>>"!CFG!\%%~nxf" & echo kt_onload>>"!CFG!\%%~nxf")
    )
)
findstr /x /c:"exec kt/init" "!CFG!\autoexec.cfg" >nul 2>&1 || (echo.>>"!CFG!\autoexec.cfg" & echo exec kt/init>>"!CFG!\autoexec.cfg")

echo kauz-tools installed to !CFG!
echo If not done yet: Steam ^> CS2 ^> Properties ^> General ^> Launch Options: +exec autoexec
pause
