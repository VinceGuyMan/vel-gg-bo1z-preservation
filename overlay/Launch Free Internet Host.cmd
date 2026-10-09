@echo off
rem Supply the exact official cloudflared2026.10.0 AMD64 executable with --cloudflared PATH. No download or install.
call "%~dp0Launch Game.cmd" --free-internet-host %*
exit /b %errorlevel%
