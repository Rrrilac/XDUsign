@echo off
chcp 65001 > nul 2>&1
setlocal enabledelayedexpansion

set "script_path=%~dp0"

set "node_path=%script_path%node.js"
set "ffmpeg_path=%script_path%ffmpeg\bin"

set "new_path=!PATH!;%node_path%;%ffmpeg_path%"

setx PATH "!new_path!"

endlocal

echo.
pause