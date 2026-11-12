# Script de maintien automatique du tunnel fixe Grow Dakar
$Subdomain = "grow-assistant-dakar"
$Port = 8000

while ($true) {
    Write-Host "[Tunnel Fixe] Lancement du tunnel https://${Subdomain}.loca.lt ..."
    lt --port $Port --subdomain $Subdomain --local-host 127.0.0.1
    Write-Host "[Tunnel Fixe] Connexion terminee. Reconnexion automatique dans 2 secondes..."
    Start-Sleep -Seconds 2
}
