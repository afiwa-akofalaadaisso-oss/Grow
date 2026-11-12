# Script de commit et push automatique Grow MVP
param (
    [string]$Message = "chore: mise a jour automatique du code Grow"
)

git add .
git commit -m $Message
git push origin main

