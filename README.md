# Camoufox + Launcher — Documentation complète 🦊

Navigateur anti-détection + suite d'outils pour l'automatisation furtive.

> 📘 Pour la documentation upstream en anglais, voir [README.en.md](README.en.md).

---

## Qu'est-ce que c'est ?

**Camoufox** est un fork de Firefox qui spoof le fingerprint au **niveau C++**, avant que le JavaScript puisse observer les valeurs réelles. Contrairement aux solutions à base d'injection JS (Puppeteer-Extra, Chrome extensions), les propriétés usurpées sont **indétectables** par inspection JavaScript.

À côté du navigateur, ce dépôt inclut une **suite complète** pour piloter Camoufox en production :

```
camoufox/                          # le navigateur Firefox patché (C++)
├── fpgen/                         # génération de profils cohérents
├── proxypool/                     # gestion/rotation de proxies
├── captchapool/                   # résolution CAPTCHA (CapSolver + 2Captcha)
├── queuepool/                     # détection de files d'attente (Queue-it/Akamai/...)
├── taskqueue/                     # queue de tâches persistante
├── launcher/                      # application Electron (UI + bridge Python)
│   ├── bridge/                    # commandes JSON-over-stdio
│   ├── src/                       # renderer React + main Electron
│   └── assets/leak-test.html      # page de diagnostic fingerprint
└── discord-bridge/                # daemon qui lance des sessions depuis Discord
```

---

## 🚀 Installation rapide

### 1. Prérequis

- **Python 3.11+** ([python.org](https://python.org/downloads) — cocher "Add to PATH" sur Windows)
- Installer Camoufox :
  ```bash
  pip install -U "camoufox[geoip]"
  python -m camoufox fetch
  ```

### 2. Launcher Electron (application graphique)

Télécharge le dernier installeur depuis [Releases](https://github.com/mesix971/camoufox/releases) :

| OS | Fichier |
|---|---|
| Windows | `Camoufox Launcher Setup X.Y.Z.exe` (installeur) ou `.exe` portable |
| Linux | `.AppImage` (portable) ou `.deb` (Debian/Ubuntu) |
| macOS | `.dmg` (installeur) ou `.zip` (archive) |

### 3. Premier lancement

1. Ouvre le launcher
2. Onglet **Profils** → **+ Nouveau profil** → choisis un archétype (ex: `windows-11-mainstream`)
3. Onglet **Sessions** → **+ Lancer** → choisis ton profil → URL cible → **Lancer**
4. Une fenêtre Camoufox s'ouvre avec le fingerprint spoofé

---

## 🧩 Modules

### fpgen — Générateur de profils

Construit des profils de fingerprint **statistiquement cohérents** à partir d'archétypes (Windows 11 mainstream, macOS 14 Retina, Linux Ubuntu dev…). Chaque profil contient 50+ champs liés entre eux : user-agent ↔ OS ↔ GPU ↔ résolution ↔ fonts ↔ timezone ↔ locale.

```python
import fpgen
p = fpgen.generate(archetype="windows-11-mainstream", locale="fr-FR")
config = fpgen.to_camoufox_config(p)  # dict prêt pour Camoufox
```

### proxypool — Pool de proxies

Parse, stocke et teste des proxies dans tous les formats usuels (URL, `host:port:user:pass`, `@-form`, iproyal avec rotation de session).

```python
import proxypool
p = proxypool.parse("proxies.panaio.com:8603:pkg-royal-country-AR-session-123:xxx")
proxypool.HealthChecker().check([p])  # test + geo-lookup
```

**Stratégies de rotation** : `Fixed`, `RoundRobin`, `Random` (pondéré), `LeastRecentlyUsed`, `StickyPerSite`.

### captchapool — Résolution de CAPTCHA

Interface unifiée pour **CapSolver** et **2Captcha**. Supporte reCAPTCHA v2/v3, hCaptcha, Turnstile.

```python
import captchapool
store = captchapool.ProviderStore("~/.camoufox/captchapool")
store.save("cap1", api_key="XXX", provider_type="capsolver", priority=10)
solver = store.build_solver(strategy="first")  # ou "fastest", "round-robin"
token = solver.solve("turnstile", site_key="0x4AAAAA...", url="https://example.com")
```

**Hook auto dans session_runner** : lance une session avec `--auto-solve-captcha` et elle détecte les captchas sur la page et les résout automatiquement.

### queuepool — Détection de files d'attente

Détecte 6 systèmes d'attente (Queue-it, Akamai, Fastly/Shopify, Nike SNKRS, Cloudflare waiting room, DataDome challenge) par URL + DOM. Le `QueueMonitor` poll la position et notifie via webhook quand tu es proche du front.

```python
import queuepool
state = queuepool.detect_queue(page.url, page.content())
if state and state.position and state.position < 10:
    # t'es bientôt passé
```

### taskqueue — Queue de tâches persistante

Queue sur disque, multi-worker safe (`os.link` atomic), avec retry policy et backoff exponentiel.

```python
import taskqueue as tq
q = tq.TaskQueue("~/.camoufox/launcher/tasks")
q.enqueue(
    action={"type": "launch-session", "profile_id": "abc", "url": "https://..."},
    scheduled_at=datetime.now() + timedelta(hours=1),
    tags=["drop-adidas"],
)
task = q.pop_due()  # atomique, pas de double-claim entre workers
```

### launcher — Application Electron

UI React + bridge Python. Onglets :

- **Tableau de bord** — métriques agrégées (profils par OS, proxies par statut, sessions running)
- **Profils** — CRUD, éditer, cloner, export/import JSON, tags colorés
- **Proxies** — CRUD, import en lot (auto-détecte iproyal/brightdata/smartproxy), health check, rotation session iproyal
- **Sessions** — lancer (options avancées), kill, logs temps réel, batch launch avec stratégie proxy (bound/round-robin/fixed)
- **Tâches** — queue de tâches programmées
- **Paramètres** — webhook Discord, limites de requêtes par hôte

### discord-bridge — Daemon Discord

Écoute un ou plusieurs channels Discord, matche les messages contre des règles, lance automatiquement des sessions Camoufox quand un drop/signal est détecté.

```json
{
  "discord": { "token": "${DISCORD_TOKEN}", "channels": ["123..."] },
  "rules": [
    {
      "name": "adidas-drop",
      "match": { "channel": "drops", "content_regex": "adidas.*(https?://\\S+)", "url_capture_group": 1 },
      "action": { "profile_strategy": "tag", "profile_tag": "adidas", "proxy_strategy": "bound" }
    }
  ]
}
```

---

## ⚙️ Options avancées des sessions

Dans l'UI (**+ Lancer** → "Options avancées") ou via le bridge :

| Option | Effet |
|---|---|
| **Préchauffage** | Visite 2-3 sites mainstream (Google, Reddit, Wikipedia…) avant la cible → WAFs voient un historique + des cookies tiers |
| **Session persistante** | `user_data_dir` par profil → cookies Cloudflare clearance survivent entre lancements |
| **Queue monitor** | Détecte les pages d'attente et notifie via webhook quand tu es proche du front |
| **Auto-refresh (s)** | Reload la page toutes les N±20 % secondes (pour les drops) |
| **Limite req/min** | Cap par hôte (partagé entre toutes les sessions via fichier) |
| **Auto-solve CAPTCHA** | Résout automatiquement Turnstile/reCAPTCHA/hCaptcha si des providers sont configurés |

---

## 🔔 Notifications Discord

Configure un webhook dans **Paramètres** ou via CLI :

```bash
python -m launcher.bridge set-webhook --url "https://discord.com/api/webhooks/..."
python -m launcher.bridge test-webhook
```

Le launcher notifie automatiquement :
- Session crashée → `error` (rouge)
- Front of queue atteint → `success` (vert)
- Webhook test → `info` (bleu)

---

## 🧪 Test de fuite de fingerprint

La page bundled `assets/leak-test.html` dump 40+ champs de fingerprint et affiche un score de cohérence (navigator, screen, WebGL, locale, audio, signaux bot, hash canvas). Utile avant d'aller sur une cible sensible pour vérifier que le profil tient.

Test externe recommandé : [creepjs](https://abrahamjuliot.github.io/creepjs/) — cible > 75 %.

---

## 🛠️ CLI — toutes les commandes bridge

```bash
# Profils
python -m launcher.bridge list-profiles [--tag X] [--os windows]
python -m launcher.bridge new-profile [--archetype ID] [--locale fr-FR] [--name N]
python -m launcher.bridge clone-profile --id <id> [--name N]
python -m launcher.bridge update-profile --id <id> --updates '{"user_agent": "..."}'
python -m launcher.bridge export-profile --id <id>
python -m launcher.bridge import-profile --profile '{...}' [--rename]
python -m launcher.bridge delete-profile --id <id>

# Proxies
python -m launcher.bridge list-proxies [--status active] [--country US]
python -m launcher.bridge add-proxy --line "http://user:pass@host:port"
python -m launcher.bridge import-proxies --text "..." [--tag group1]
python -m launcher.bridge check-proxies-all [--workers 10]
python -m launcher.bridge rotate-proxy-session --id <id> [--country AR]

# Sessions
python -m launcher.bridge launch-session --profile-id <id> [--proxy-id X] [--url Y] \
    [--warmup] [--auto-refresh 30] [--persistent] [--queue-monitor] [--rate-limit 20]
python -m launcher.bridge batch-launch-session --profile_ids '["a","b"]' --strategy bound
python -m launcher.bridge kill-session --id <id>
python -m launcher.bridge list-sessions
python -m launcher.bridge session-log --id <id> --lines 200

# Tâches (queue)
python -m launcher.bridge enqueue-task --action '{"type":"launch-session",...}' [--delay_seconds 3600]
python -m launcher.bridge list-tasks [--status QUEUED]
python -m launcher.bridge delete-task --id <id>

# Paramètres
python -m launcher.bridge set-webhook --url "https://discord.com/api/..."
python -m launcher.bridge test-webhook [--content "message"]
python -m launcher.bridge ratelimit-set --host ticketmaster.com --max_per_minute 10
python -m launcher.bridge ratelimit-stats

# Divers
python -m launcher.bridge dashboard-summary
python -m launcher.bridge list-archetypes
```

---

## 🏗️ Architecture

```
┌─────────────────────────┐
│  Electron renderer      │  React + Zustand + Tailwind
│  (UI française)         │
└────────┬────────────────┘
         │ IPC (window.api.*)
┌────────▼────────────────┐
│  Electron main process  │  Node.js
│  bridge.ts / ipc.ts     │
└────────┬────────────────┘
         │ spawn python3
┌────────▼────────────────┐
│  launcher.bridge        │  JSON stdin/stdout
│  (Python command disp.) │
└────────┬────────────────┘
         │
         ├──► fpgen          (profile gen)
         ├──► proxypool      (proxy pool)
         ├──► captchapool    (captcha solving)
         ├──► queuepool      (queue detection)
         ├──► taskqueue      (persistent tasks)
         │
         ▼
┌─────────────────────────┐
│  session_runner.py      │  subprocess détaché
│  (1 session = 1 process)│
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  camoufox.sync_api      │
│  (Playwright patched)   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Camoufox browser       │  Firefox 142 avec patches C++
└─────────────────────────┘
```

---

## 🧪 Tests

```bash
cd /home/user/camoufox
python -m pytest fpgen/tests proxypool/tests captchapool/tests queuepool/tests taskqueue/tests launcher/bridge/tests
```

Couverture actuelle :
- fpgen : 103 tests
- proxypool : ~40 tests
- captchapool : 43 tests
- queuepool : 39 tests
- taskqueue : 27 tests
- launcher/bridge : 20+ tests
- **Total : ~270+ tests**

---

## 🔧 Développement

### Dev mode launcher

```bash
cd launcher
npm install
npm run dev   # lance Electron avec hot reload
```

### Créer une release

1. Push ton commit sur `main` ou une branche
2. GitHub → Releases → Draft new release
3. Tag : `launcher-v0.X.Y`
4. Publish → CI build automatiquement les installeurs (~10 min)
5. Installeurs téléchargeables dans la page Release

---

## 🐛 Dépannage Windows

### `ModuleNotFoundError: camoufox`
Le launcher utilise un Python différent de celui où tu as installé camoufox.
```powershell
setx CAMOUFOX_PYTHON python
# ferme + relance le launcher
```

### Sessions qui se mettent en "stopped" immédiatement
Bug corrigé depuis v0.1.5. Si tu es sur plus ancien, mets à jour.

### `python3` ouvre le Microsoft Store
Normal — `python3.exe` sur Windows est un stub. Le launcher utilise `py -3` depuis v0.1.5.

---

## 🗺️ Roadmap

### ✅ Déjà implémenté
- Fingerprint C++ via `fpgen` (archétypes, 50+ champs cohérents, preset Firefox, 103 tests)
- Pool de proxies `proxypool` avec parseurs multi-format + rotation (5 stratégies)
- Captcha solving `captchapool` (CapSolver + 2Captcha, 4 types de challenges, 43 tests)
- Queue detection `queuepool` (Queue-it, Akamai, Fastly/Shopify, SNKRS, Cloudflare, DataDome, 39 tests)
- Task queue persistante `taskqueue` avec retry + backoff + multi-worker safe (27 tests)
- **CreepJS auto-scoring** `creepjsscore` — lance un profil sur creepjs.com, scrape FP + Trust score, rejette si < seuil (16 tests)
- **Humanlike cursor + typing** `humanlike` — courbes de Bézier avec overshoot, délais réalistes, typos optionnels (29 tests)
- **Action DSL + macro recorder** `actions` — 17 types d'actions (goto/wait_for/click/fill/type/if/repeat/…), recorder via JS shim (61 tests)
- **Canvas/WebGL pixel noise** — patch C++ P4 draft (`patches/canvas-webgl-pixel-noise.patch`), prêt à appliquer et régénérer depuis l'arbre Firefox
- **Métriques live** — `launcher/bridge/metrics.py` utilise psutil (lazy) pour CPU%/RAM/IO par PID de session, incluant les enfants
- Webhook Discord (notifications colorées par niveau)
- Warmup sessions (2-3 sites innocents avant la cible)
- Auto-refresh avec jitter ±20 %
- Rate limiting par hôte (partagé entre sessions)
- Cookie/storage persistence via `user_data_dir`
- Retry exponentiel avec jitter
- Discord bridge daemon (listen + match + launch)
- Leak test page bundled (40+ champs de fingerprint + score)
- UI française complète (Electron + React)
- Windows Job Object breakaway (sessions survivent)
- `_pid_alive` via ctypes (reliable status tracking)
- Installeurs multi-OS (AppImage, deb, exe, dmg, zip)

### 🟢 UI complète
- **CreepJS** : bouton "Tester CreepJS" sur chaque profil + badge coloré (vert ✓ passed / rouge ✗ failed) avec scores FP/Trust
- **Humanlike** : checkbox "Humanlike (souris + frappe réaliste)" dans Options avancées
- **Macros** : onglet dédié avec édition JSON, lancement (+ profil + URL), enregistrement via session, suppression
- **Métriques live** : colonnes CPU % + RAM dans Sessions (rafraîchies toutes les 2 s), panel "Système" dans Dashboard (CPU + RAM totaux) rafraîchi toutes les 5 s, bannière ambre si psutil manquant

### ⚠️ Partiellement — nécessite travail externe

- **Canvas/WebGL pixel noise** : le patch `patches/canvas-webgl-pixel-noise.patch` est draft. Il faut l'appliquer sur un arbre Firefox 142, fixer les numéros de ligne qui auront fuzz, et regénérer via `git diff` pour produire une version finale. Sans accès au source Firefox dans cet environnement, les numéros de ligne restent approximatifs.

### ✅ Scheduler daemon — fait

Implémenté dans `launcher/bridge/scheduler.py` — lance avec :
```bash
python -m launcher.bridge.scheduler
```

3 jobs récurrents :
- **`proxy_health_check`** (toutes les 10 min) : `check-proxies-all` + webhook si > 50 % du pool meurt
- **`session_crash_watch`** (toutes les 60 s) : si un profil crashe 3+ fois en < 1 h → tag `frozen` + webhook
- **`ratelimit_escalation`** (toutes les 60 s) : si un hôte est à > 90 % de son cap pendant 5 min → webhook

État persistant dans `~/.camoufox/launcher/scheduler.json`. Tu peux le lancer en systemd service ou cron `@reboot` pour qu'il tourne en permanence.

---

## 📄 Licence

MIT — comme Camoufox upstream.

## 🙏 Crédits

- [@daijro](https://github.com/daijro) — créateur original de Camoufox
- [@coryking](https://github.com/coryking) — upgrade Firefox 142
- Tous les contributeurs du dépôt
