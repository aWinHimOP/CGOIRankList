@echo off
chcp 65001 >nul
echo === CGOI 排行榜 - 本地服务器 ===
echo 地址: http://localhost:8080
echo 按 Ctrl+C 停止服务器
echo.
start http://localhost:8080
python proxy_server.py
