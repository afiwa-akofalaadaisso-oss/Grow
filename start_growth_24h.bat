@echo off
TITLE GROWTH SAAS — GARDIEN 24H/24 & 7J/7
color 0A

echo =======================================================================
echo          GROWTH FINTECH SENEGAL — COPILOTE COMPTABLE SYSCOHADA
echo                    GARDIEN DU SERVEUR 24H/24
echo =======================================================================
echo.
echo Ce script maintient Growth en marche permanente 24h/24.
echo Si le serveur ou le tunnel coupe, il redémarre automatiquement en 3 sec.
echo.

:: Empêcher la mise en veille automatique pendant l'exécution
powercfg /change standby-timeout-ac 0 >nul 2>&1

:BOUCLE_PERMANENTE
cls
echo [%DATE% %TIME%] Verification et demarrage des services Growth...
echo.

:: 1. Lancement de Ngrok en arriere-plan si non actif
tasklist /FI "IMAGENAME eq ngrok.exe" 2>NUL | find /I /N "ngrok.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo [TUNNEL] Lancement du tunnel securise Ngrok...
    start /B ngrok http 8000 --url=https://rascal-legible-unsheathe.ngrok-free.dev >nul 2>&1
    timeout /t 2 /nobreak >nul
) else (
    echo [TUNNEL] Tunnel Ngrok deja actif sur https://rascal-legible-unsheathe.ngrok-free.dev
)

:: 2. Demarrage du serveur Uvicorn avec surveillance continue
echo [SERVEUR] Demarrage du serveur Growth sur http://127.0.0.1:8000 ...
echo [SAAS] Mode 24h/24 actif. Appuyez sur CTRL+C pour quitter.
echo -----------------------------------------------------------------------

python -m uvicorn chat_grow.main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo [ATTENTION] Le serveur Growth s'est arrete !
echo [AUTO-HEALING] Redemarrage automatique dans 3 secondes...
timeout /t 3 /nobreak >nul
goto BOUCLE_PERMANENTE

