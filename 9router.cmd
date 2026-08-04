@echo off
rem ============================================================
rem  9router.cmd — Windows wrapper for 9router-cli.sh
rem  Run from cmd or PowerShell (both work)
rem
rem  Usage:  9router up 3
rem          9router list
rem          9router keys
rem          9router down all
rem          ...
rem ============================================================
setlocal

rem --- this script's own directory ---
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

rem --- find Git Bash (used by Railway docs / general installs) ---
set "BASH="
if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH=%ProgramFiles%\Git\bin\bash.exe"
if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH=%ProgramFiles(x86)%\Git\bin\bash.exe"
if exist "%LocalAppData%\Programs\Git\bin\bash.exe" set "BASH=%LocalAppData%\Programs\Git\bin\bash.exe"

if not defined BASH (
  echo [!] Git Bash not found. Install Git for Windows: https://git-scm.com/download/win
  exit /b 1
)

rem --- make railway CLI available to the bash subprocess ---
set "PATH=%AppData%\Roaming\npm;%PATH%"

rem --- call the bash script, forwarding all args ---
"%BASH%" -c "cd \"%DIR%\" \&\& bash 9router-cli.sh \"$@\"" bash %*

endlocal
