$port = 8080
Write-Host 'CGOI Ranking Server' -ForegroundColor Cyan
Write-Host http://localhost:$port -ForegroundColor Green
Write-Host 'Press Ctrl+C to stop' -ForegroundColor Yellow
Start-Process http://localhost:$port
python proxy_server.py
