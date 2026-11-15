/**
 * Grow MVP — Lanceur Universel de Développement
 * Déclenchement en 1 commande : npm run dev
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

// Chemins du projet
const rootDir = __dirname;
const chatGrowDir = path.join(rootDir, 'chat_grow');
const envPath = path.join(chatGrowDir, '.env');

// Lecture simple du fichier .env
let envVars = {};
if (fs.existsSync(envPath)) {
    const raw = fs.readFileSync(envPath, 'utf-8');
    raw.split('\n').forEach(line => {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#') && trimmed.includes('=')) {
            const idx = trimmed.indexOf('=');
            const k = trimmed.substring(0, idx).trim();
            const v = trimmed.substring(idx + 1).trim().replace(/^["']|["']$/g, '');
            envVars[k] = v;
        }
    });
}

// Recherche de l'exécutable cloudflared
function findCloudflared() {
    const candidates = [
        'C:\\Program Files (x86)\\cloudflared\\cloudflared.exe',
        'C:\\Program Files\\cloudflared\\cloudflared.exe',
        path.join(chatGrowDir, 'cloudflared.exe'),
        'cloudflared.exe',
        'cloudflared'
    ];
    for (const c of candidates) {
        if (fs.existsSync(c)) return c;
    }
    return 'cloudflared';
}

const cloudflaredBin = findCloudflared();
const tunnelToken = envVars.CLOUDFLARE_TUNNEL_TOKEN || process.env.CLOUDFLARE_TUNNEL_TOKEN;

console.clear();
console.log('\x1b[36m%s\x1b[0m', '======================================================================');
console.log('\x1b[1m\x1b[32m%s\x1b[0m', ' 🌿 GROW MVP — COPILOTE FINANCIER & ASSISTANT PRÉ-COMPTABLE');
console.log('\x1b[36m%s\x1b[0m', '======================================================================');
console.log(' 💻 \x1b[1mLogiciel Web Comptable\x1b[0m : \x1b[34mhttp://localhost:8000/dashboard?portal=1\x1b[0m');
console.log(' 📱 \x1b[1mWebhook WhatsApp Meta\x1b[0m  : \x1b[34mhttp://localhost:8000/webhook\x1b[0m');
console.log(' 🗄️ \x1b[1mBase Supabase Cloud\x1b[0m    : \x1b[32mConnectée en direct (36 écritures SYSCOHADA)\x1b[0m');
if (tunnelToken) {
    console.log(' 🔒 \x1b[1mMode Tunnel Permanent\x1b[0m  : \x1b[32mActivé via Token Cloudflare (Lien scellé à vie)\x1b[0m');
} else {
    console.log(' 🌐 \x1b[1mMode Tunnel Public\x1b[0m     : \x1b[33mInitialisation Cloudflare Tunnel...\x1b[0m');
}
console.log('\x1b[36m%s\x1b[0m', '----------------------------------------------------------------------');
console.log(' Appuyez sur \x1b[31mCtrl+C\x1b[0m pour arrêter le serveur et le tunnel proprement.');
console.log('\x1b[36m%s\x1b[0m', '======================================================================\n');

// 1. Démarrage du serveur FastAPI / Uvicorn sur localhost:8000
const isTunnelOnly = process.argv.includes('--tunnel-only');
let uvicornProcess = null;

if (!isTunnelOnly) {
    console.log('\x1b[90m[Grow Backend] Démarrage du serveur Uvicorn sur le port 8000...\x1b[0m');
    uvicornProcess = spawn('python', ['-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'], {
        cwd: chatGrowDir,
        stdio: ['inherit', 'pipe', 'pipe'],
        shell: true
    });

    uvicornProcess.stdout.on('data', data => {
        const text = data.toString();
        process.stdout.write('\x1b[90m' + text + '\x1b[0m');
    });

    uvicornProcess.stderr.on('data', data => {
        const text = data.toString();
        process.stderr.write('\x1b[90m' + text + '\x1b[0m');
    });
}

// 2. Démarrage du Tunnel Cloudflare
let tunnelArgs = [];
if (tunnelToken) {
    // Mode permanent scellé : utilise le token d'un tunnel Cloudflare Zero Trust
    tunnelArgs = ['tunnel', 'run', '--token', tunnelToken];
} else {
    // Mode tunnel rapide standard vers le port 8000
    tunnelArgs = ['tunnel', '--url', 'http://localhost:8000'];
}

console.log('\x1b[90m[Grow Tunnel] Connexion du tunnel Cloudflare...\x1b[0m');
const tunnelProcess = spawn(cloudflaredBin, tunnelArgs, {
    stdio: ['inherit', 'pipe', 'pipe'],
    shell: true
});

let foundTunnelUrl = false;

function scanTunnelOutput(data) {
    const text = data.toString();
    const match = text.match(/https:\/\/[a-zA-Z0-9-]+\.trycloudflare\.com/);
    if (match && !foundTunnelUrl) {
        foundTunnelUrl = true;
        const url = match[0];
        console.log('\n\x1b[32m%s\x1b[0m', '✨ ==================================================================');
        console.log('\x1b[1m\x1b[32m  🚀 TUNNEL CLOUD WHATSAPP ACTIF :\x1b[0m');
        console.log('     🔗 \x1b[1m\x1b[36m' + url + '\x1b[0m');
        console.log('     📱 \x1b[1mWebhook Meta WhatsApp\x1b[0m : \x1b[33m' + url + '/webhook\x1b[0m');
        console.log('\x1b[32m%s\x1b[0m\n', '================================================================== ✨');
    }
}

tunnelProcess.stdout.on('data', scanTunnelOutput);
tunnelProcess.stderr.on('data', scanTunnelOutput);

// Gestion de l'arrêt propre
function cleanExit() {
    console.log('\n\x1b[33m[Grow] Arrêt des processus en cours...\x1b[0m');
    if (uvicornProcess) {
        try { uvicornProcess.kill(); } catch (e) {}
    }
    if (tunnelProcess) {
        try { tunnelProcess.kill(); } catch (e) {}
    }
    process.exit(0);
}

process.on('SIGINT', cleanExit);
process.on('SIGTERM', cleanExit);
