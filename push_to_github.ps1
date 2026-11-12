# Script de synchronisation automatique vers GitHub
Write-Host "Poussée des modifications vers GitHub (https://github.com/adaissoakofala-maker/Grow)..." -ForegroundColor Cyan
git add -A
git commit -m "Mise a jour continue Grow" -ErrorAction SilentlyContinue
git push -u origin main
Write-Host "Code synchronise avec succes sur GitHub !" -ForegroundColor Green
