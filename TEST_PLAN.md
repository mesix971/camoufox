# Plan de test — Camoufox + Launcher

> Plan exhaustif dérivé du code. Chaque fonctionnalité est listée avec un cas
> nominal + 2-4 edge cases + un test de stress quand pertinent.
>
> Sections :
>   1. Vue d'ensemble
>   2. Tests par module Python
>   3. Tests par commande bridge
>   4. Tests UI Electron *(turn 2)*
>   5. Tests d'intégration *(turn 2)*
>   6. Tests de patches C++ *(turn 2)*
>   7. Différences avec l'upstream *(turn 2)*

---

## 1. Vue d'ensemble

| Composant | Surface de test |
|---|---|
| Modules Python | 8 packages (`fpgen`, `proxypool`, `captchapool`, `queuepool`, `taskqueue`, `creepjsscore`, `humanlike`, `actions`) — 270+ unit tests existants |
| Bridge Python | 46 commandes dans `launcher/bridge/commands.py` |
| UI Electron | 7 onglets : Dashboard, Profils, Proxies, Sessions, Tâches, Macros, Paramètres |
| Daemons | `scheduler`, `task_worker` (tâches récurrentes + queue executor) |
| Discord bridge | 1 process + N règles + parser regex |
| Patches C++ | 60+ patches Firefox dont 4 P4 + 3 drafts (canvas-noise, UA-CH, WebRTC ICE) |

---

## 2. Tests par module Python

### 2.1 `fpgen/`

**`generate(archetype, os, locale, firefox_version, name, tags, seed)`**
- ✅ Nominal : génère un Profile cohérent depuis un archétype connu.
- ⚠️ archetype inconnu → `KeyError`.
- ⚠️ `seed` identique → 2 appels produisent le même Profile.
- ⚠️ `os="linux"` + `archetype="windows-11-mainstream"` → conflit, doit raise.
- 🔥 Stress : générer 1000 profils, vérifier l'absence de collision d'IDs.

**`Profile.to_camoufox_config()`**
- ✅ Émet 53+ clés MaskConfig.
- ⚠️ Profile sans champs P4 → aucune clé `http2:*`/`tls:*`/`webgl:readback_noise:*` n'est émise.
- ⚠️ Profile avec `ua_data_brands=[]` → la clé n'est PAS émise (filtre falsy).

**`ProfileStore.save / load / list / delete / pick_least_recently_used`**
- ✅ Save puis load round-trip.
- ⚠️ Load d'un id inexistant → `KeyError`.
- ⚠️ Save avec un id contenant `/` ou `..` → path traversal (NON TESTÉ actuellement).
- 🔥 Stress : 10 000 profils, list() doit rester < 500 ms.

**`consistency.validate(profile)` (16 invariants R1-R16)**
- ✅ Profil cohérent → liste vide.
- ⚠️ UA Mac avec `cpu_cores` impair → R7 violation.
- ⚠️ Locale `de-DE` avec timezone `America/New_York` → R12 violation.

### 2.2 `proxypool/`

**`parse(line, label, tags)`**
- ✅ Format URL : `http://user:pass@host:port`.
- ✅ Format flat : `host:port:user:pass`.
- ✅ Format @-form : `user:pass@host:port`.
- ✅ Format no-auth : `host:port`.
- ⚠️ `ftp://x:y@h:p` → `ParseError` (scheme non supporté).
- ⚠️ `host:99999` → port out of range.
- ⚠️ Username iproyal `pkg-royal-country-AR-session-12345` → auto-détecté provider="iproyal".

**`HealthChecker.check(proxies)` (parallèle)**
- ✅ N proxies → résultats dans le même ordre.
- ⚠️ Timeout réseau → `ok=False`, error renseigné, status passe à FLAGGED après `dead_after` échecs.
- 🔥 Stress : 200 proxies en 10 workers → < 60 s.

**`iproyal.rotate_session(proxy, new_session_id, lifetime, country)`**
- ✅ Crée un nouveau Proxy avec session_id différent dans le password.
- ⚠️ Proxy non-iproyal → no-op ou raise (à vérifier).

**Stratégies `Fixed / RoundRobin / Random / LeastRecentlyUsed / StickyPerSite`**
- ✅ Chacune retourne un proxy parmi le pool.
- ⚠️ Pool vide → `NoHealthyProxy`.
- ⚠️ StickyPerSite avec TTL=0 → comportement de RoundRobin pur.

### 2.3 `captchapool/`

**`Solver.solve(challenge_type, **kwargs)` (stratégies first/fastest/round-robin)**
- ✅ first : tente provider 1, succès → renvoie token.
- ⚠️ first : provider 1 timeout → fallback sur provider 2.
- ⚠️ Tous les providers ont 0 fond → `CaptchaInsufficientFunds` propagé.
- ⚠️ Mauvaise clé API → `CaptchaInvalidKey` non-recoverable, on n'essaie pas le suivant pour cette erreur.

**`ProviderStore.save / load / list (api_key redacted)`**
- ✅ list() retourne `api_key="••••"+suffix` (jamais en clair).
- ⚠️ Provider name avec espaces → rejetée à save.

### 2.4 `queuepool/`

**`detect_queue(url, html=None)`**
- ✅ URL `*.queue-it.net` → `QueueKind.QUEUE_IT`.
- ⚠️ `nike.com` + body "We've got you in line" → `NIKE_SNKRS`.
- ⚠️ Body avec `__cf_chl_` → `CLOUDFLARE_WAITING`.
- ⚠️ URL inconnue + body neutre → `None`.

**`QueueMonitor.sync_monitor(page, on_change, on_front)`**
- ✅ Callback `on_change` appelé à chaque saut de position > 20 %.
- ✅ Callback `on_front` appelé une seule fois quand position ≤ threshold.
- ⚠️ Page raise sur `.content()` → boucle continue, swallow.

**`QueueItClient.poll(queue_url)`**
- ✅ Retourne `position` extraite via regex.
- ⚠️ HTML sans pattern connu → `position=None`, pas d'erreur.
- ⚠️ Redirect hors `.queue-it.net` → `position=0` (signale qu'on est passé).
- ⚠️ HTTP 503 → `error="HTTP 503"`.

### 2.5 `taskqueue/`

**`TaskQueue.enqueue / pop_due / reschedule`**
- ✅ enqueue puis pop_due immédiatement → la même task.
- ⚠️ scheduled_at futur → pop_due retourne `None`.
- ⚠️ 2 workers pop_due simultanément → un seul gagne (atomic via `os.link`).
- ⚠️ retry_policy.max_retries=3, 4e échec → `status=FAILED` définitif.
- 🔥 Stress : 1000 tasks en 10 workers, aucun double-claim.

### 2.6 `creepjsscore/`

**`Scorer.score(page, profile_id)`**
- ✅ Page renvoie scores valides → `passed=True` si ≥ seuils.
- ⚠️ `navigator.webdriver=true` → `passed=False` même avec scores OK.
- ⚠️ Timeout 60 s sur `wait_for_selector` → `error` rempli, `passed=False`.

### 2.7 `humanlike/`

**`Bezier.humanize / points / with_velocity`**
- ✅ Courbe va de start à end (overshoot=0).
- ⚠️ start == end → courbe dégénérée non-NaN.
- ⚠️ deviation=0 → ligne droite quasi.

**`cursor.move / click / drag`**
- ✅ click() → mouse.down + mouse.up appelés une fois.
- ⚠️ Selector inexistant → raise (pas swallow).
- ⚠️ Page sans `locator` → fallback sur `query_selector`.

**`typing.type_text(typo_rate)`**
- ✅ typo_rate=0 → exactement len(text) keyboard.type calls.
- ⚠️ typo_rate=1 → 2*len(text) types + len(text) Backspace.

### 2.8 `actions/`

**`run_script(page, script, humanlike_module)`**
- ✅ 17 types d'actions exécutés en séquence.
- ⚠️ Action inconnue → ActionResult avec `error`, on continue ou abort selon `on_error`.
- ⚠️ `repeat` imbriqué profond (>10 niveaux) → pas de protection actuelle (potentiellement stack overflow).
- ⚠️ `if` avec condition `selector_exists` mais selector vide → False par défaut.

**`Recorder.start / stop`**
- ✅ Click sur élément avec id → action `{type:"click", selector:"#id"}`.
- ⚠️ stop() avant start() → AttributeError si on n'a pas init la liste.
- ⚠️ Recorder qui tourne sur page navigué → re-injecte le listener (ou pas).

---

## 3. Tests par commande bridge (46 commandes)

### Profils
- `list-profiles`, `show-profile`, `new-profile`, `delete-profile`, `clone-profile`, `update-profile`, `export-profile`, `import-profile`, `list-archetypes`

### Proxies
- `list-proxies`, `show-proxy`, `add-proxy`, `import-proxies`, `delete-proxy`, `check-proxy`, `check-proxies-all`, `rotate-proxy-session`

### Sessions
- `list-sessions`, `launch-session`, `reopen-session`, `kill-session`, `kill-all-sessions`, `prune-sessions`, `session-log`, `batch-launch-session`, `session-metrics`

### Macros
- `list-macros`, `show-macro`, `save-macro`, `delete-macro`

### Tâches & worker
- `enqueue-task`, `list-tasks`, `delete-task`, `warmup-profile`, `warmup-batch`

### Cookie / Queue-it
- `export-profile-cookies`, `queueit-poll`, `queueit-parse-url`

### Settings & misc
- `set-webhook`, `get-webhook`, `test-webhook`, `ratelimit-stats`, `ratelimit-set`, `bind-profile-proxy`, `dashboard-summary`, `score-profile-creepjs`

**Format de test pour chaque commande** :
- ✅ Args minimum requis présents → 200 + JSON valide
- ⚠️ Args manquants → `KeyError` propre (pas un crash Python)
- ⚠️ Args malformés (string où int attendu) → `ValueError`
- ⚠️ Référence à un id inexistant → `KeyError` avec message clair
- 🔒 Permissions FS : écriture dans `~/.camoufox/` doit succeed même sans root

**Cas particuliers à tester en priorité** :

| Commande | Test critique |
|---|---|
| `launch-session` | toutes les options avancées (warmup, persistent, queue_monitor, auto_refresh, rate_limit, humanlike, run_macro, record_macro, auto_solve_captcha) émettent le bon argv |
| `batch-launch-session` | tile=true + grid="3x2" → fenêtres correctement positionnées |
| `reopen-session` | session morte → nouvelle session avec persistent=true et même profile_id |
| `import-profile` | rename=true → nouvel id généré, pas de collision |
| `export-profile-cookies` | session NON running → succès ; session running → conflit lock user_data_dir |
| `queueit-poll` | sans cookies → position=None gracefully |
| `score-profile-creepjs` | save_to_profile=true + passed → tag "creepjs-passed" ajouté |

---

## 4. Tests UI Electron

### 4.1 Dashboard
- ✅ Rafraîchit toutes les 3 s les compteurs profils/proxies/sessions.
- ✅ Panel **Système** affiche CPU%/RAM total, refresh 5 s.
- ⚠️ Aucune session running → "0 active" sans crash.
- ⚠️ psutil absent → bannière ambre "Installez psutil".

### 4.2 Profils
- ✅ "+ Nouveau profil" → modal avec presets archétypes.
- ✅ "Cloner" → confirme + duplique avec nouveau nom suffixé `-clone`.
- ✅ "Exporter" → télécharge JSON depuis le navigateur.
- ✅ "Importer" → modal textarea, parse JSON, reject=true par défaut.
- ✅ "Tester CreepJS" → lance session headless, badge ✓/✗ apparaît après ~30 s.
- ⚠️ Editer profile pendant qu'une session l'utilise → la session ne voit pas le changement (le profil est lu une fois au spawn).
- ⚠️ Tags vides après split par virgule → liste vide propre.

### 4.3 Proxies
- ✅ Import en lot avec 4 lignes iproyal de session différente → 4 saved (pas 1).
- ⚠️ Coller du texte non-proxy → `errors[]` détaillés par ligne.
- ⚠️ Check d'un proxy mort → status passe à "dead" après `dead_after` échecs.

### 4.4 Sessions
- ✅ Polling toutes les 2 s avec `metrics=true`.
- ✅ Bouton **Arrêter** sur running → SIGTERM puis SIGKILL après 5 s.
- ✅ Bouton **Réouvrir** sur stopped → nouvelle session persistent=true.
- ✅ "Logs" → modal qui tail toutes les 1.5 s.
- ⚠️ Session crashed (exit_code != 0) → status=crashed, logs préservés.
- ⚠️ Fermer manuellement la fenêtre Firefox → status passe à stopped en ~2-4 s.
- 🔥 Stress : lancer 16 sessions tile=4x4 → toutes positionnées, aucune superposée.

### 4.5 Tâches
- ✅ Compteurs par statut (QUEUED/RUNNING/SUCCESS/FAILED/RETRYING/CANCELLED) à jour toutes 3 s.
- ✅ "+ Nouvelle tâche" → modal compose action, scheduled_at en futur.
- ⚠️ Task supprimée pendant qu'elle est RUNNING → orphan ; le worker doit gracefully gérer ce cas.

### 4.6 Macros
- ✅ "+ Nouvelle macro" → JSON editor, valide via `ActionScript.validate()`.
- ✅ "Exécuter" → modal pick profile + URL, lance session avec `run_macro`.
- ✅ "Enregistrer" → modal name + profile, lance session avec `record_macro`.
- ⚠️ JSON malformé dans editor → toast erreur, modal reste ouvert.
- ⚠️ Macro inexistante dans run_macro → session_runner log error, n'exécute pas.

### 4.7 Paramètres
- ✅ Webhook URL save → vérifie ${url} échappé, masqué à display.
- ✅ "Tester" → POST sur webhook, toast success/échec.
- ✅ Rate limit per host → form ajoute, table list rafraîchit.
- ⚠️ URL non-https → reject à save.

---

## 5. Tests d'intégration

### 5.1 Session end-to-end
1. Créer profil `windows-11-mainstream`.
2. Ajouter proxy iproyal valide.
3. Bind proxy au profil.
4. Lancer session avec URL `https://bot.sannysoft.com` + warmup + persistent.
5. Vérifier : 2-3 sites mainstream visités avant la cible, page sannysoft tout vert, cookies persistés dans `~/.camoufox/launcher/user_data/<id>/`.
6. Fermer fenêtre → status `stopped` en ~4 s.
7. Cliquer **Réouvrir** → nouvelle session retrouve les cookies.

### 5.2 Discord bridge → launcher → session
1. Configurer `discord-bridge/config.json` avec une règle `content_regex` simple.
2. Lancer `npm start`.
3. Poster un message correspondant dans le channel cible.
4. Vérifier : `launcher-client.ts` appelle `python -m launcher.bridge launch-session`, session apparaît dans l'UI.

### 5.3 Task worker → spawn → finish
1. `enqueue-task` action `warmup` profile X duration 1 min.
2. Lancer `python -m launcher.bridge.task_worker`.
3. Vérifier : worker pop la task, lance la session, attend 1 min, kill, marque SUCCESS.
4. Status final : `tasks.list({status:"SUCCESS"})` retourne la task avec `result.duration_minutes=1`.

### 5.4 Cookie export → import dans Chrome
1. Profile persistent + session navigue sur ticketmaster.com → cookies générés.
2. Fermer la session.
3. `export-profile-cookies` → JSON + cookies.txt produits.
4. Import du `.txt` via extension **Cookie Editor** dans Chrome.
5. Visiter ticketmaster.com → user reconnu (logged in).

### 5.5 Tiling auto multi-écran
- ⚠️ Tester avec écran principal 1920×1080.
- ⚠️ Avec 2 moniteurs : positions sur écran principal seulement (limitation `screen.py`).

### 5.6 Scheduler daemon
1. Ajouter 5 proxies dont 2 morts.
2. Lancer `python -m launcher.bridge.scheduler`.
3. Attendre 10 min → vérifier que `proxy_health_check` a flagged les morts.
4. Faire crasher 3 sessions sur le même profil → `session_crash_watch` ajoute tag `frozen`.

---

## 6. Tests de patches C++

> Tous nécessitent un build Camoufox custom (CI ou local via WSL).
> Outils de vérification : [CreepJS](https://abrahamjuliot.github.io/creepjs/), [tls.peet.ws](https://tls.peet.ws), [browserleaks.com](https://browserleaks.com), [BotsLab](https://www.deviceandbrowserinfo.com/are_you_a_bot).

### 6.1 Patches existants vérifiés
| Patch | Test |
|---|---|
| `webgl-spoofing.patch` | CreepJS section WebGL → vendor/renderer match config |
| `audio-context-spoofing.patch` | tls.peet.ws audio fingerprint → match config |
| `font-hijacker.patch` | browserleaks.com/fonts → liste exacte du profil |
| `force-default-pointer.patch` | sannysoft "Pointer" test → "fine" en headless |
| `http2-settings-spoofing.patch` | tls.peet.ws → SETTINGS frame correspond |
| `tls-extensions-spoofing.patch` | tls.peet.ws → JA3 hash unique par profil |
| `tls-grease-disable.patch` | tls.peet.ws → ECH GREASE off ou on selon config |
| `creepjs-script-bypass.patch` | CreepJS bloqué quand hostname matche → score "Trust High" |

### 6.2 Patches drafts (3 nouveaux à valider)

**`canvas-webgl-pixel-noise.patch`** :
- ✅ `getImageData` → hash diffère entre 2 profils sur la même page.
- ✅ `getImageData` 2× sur même profil → même hash (stabilité).
- ✅ `toDataURL` → hash diffère entre 2 profils.
- ✅ `getImageData` et `toDataURL` sur même profil/frame → hash CORRELATED (consistance).
- ✅ `WebGL.readPixels` → bytes diffèrent entre 2 profils.
- ⚠️ amplitude=0 → no-op.
- ⚠️ enabled=false → byte-perfect identique au Firefox vanilla.

**`navigator-user-agent-data.patch`** :
- ✅ `navigator.userAgentData.brands` → match config.
- ✅ `navigator.userAgentData.getHighEntropyValues(["platformVersion"])` → resolve avec valeur config.
- ✅ Headers `Sec-CH-UA`, `Sec-CH-UA-Mobile`, `Sec-CH-UA-Platform` envoyés sur chaque requête.
- ⚠️ Pref `dom.navigator.useragent.userAgentData.enabled = true` doit être set dans camoufox.cfg.
- ⚠️ Hint non listé dans config → champ absent du retour (pas null).

**`webrtc-ice-candidate-order.patch`** :
- ✅ Avec `dropHostCandidates=true` → `RTCPeerConnection.onicecandidate` ne livre que srflx/relay.
- ✅ Avec `shuffle=true` + même seed → ordre identique entre 2 sessions du même profil.
- ✅ Avec `candidateOrder=["relay","srflx"]` → ordre exact respecté.
- ⚠️ ICE gathering jamais complete (ex: pas d'internet) → callback final pas appelé (pas de crash).

### 6.3 Procédure complète d'application
```bash
# 1. Cloner Firefox source via le workflow git
make git-fetch
make git-dir       # applique tous les patches

# 2. Identifier les .rej probables
grep -rn '.rej' camoufox-*-fork.*/

# 3. Pour chaque .rej → ouvrir le fichier source ciblé,
#    appliquer le hunk manuellement, supprimer le .rej.

# 4. Régénérer
cd camoufox-*-fork.*
git diff > ../patches/<nom>.patch

# 5. Build + test
make build && make run args="--url https://abrahamjuliot.github.io/creepjs/"
```

---

## 7. Différences avec l'upstream Camoufox

L'upstream est `daijro/camoufox` (forké via `coryking/camoufox` qui a fait l'upgrade Firefox 142). Le fork `mesix971/camoufox` ajoute une **suite d'outils Python + Electron** qui n'existe nulle part en upstream.

### 7.1 Nouveau dans le fork
| Composant | Localisation | Statut upstream |
|---|---|---|
| **fpgen** (générateur de profils) | `fpgen/` | ❌ absent |
| **proxypool** (gestion proxies) | `proxypool/` | ❌ absent |
| **captchapool** (CapSolver/2Captcha) | `captchapool/` | ❌ absent |
| **queuepool** (Queue-it API + détection) | `queuepool/` | ❌ absent |
| **taskqueue** (queue persistante) | `taskqueue/` | ❌ absent |
| **creepjsscore** (scoring auto) | `creepjsscore/` | ❌ absent |
| **humanlike** (Bezier cursor + typing) | `humanlike/` | ❌ absent |
| **actions** (DSL JSON + recorder) | `actions/` | ❌ absent |
| **launcher Electron** | `launcher/` | ❌ absent |
| **discord-bridge** | `discord-bridge/` | ❌ absent |
| **scheduler daemon** | `launcher/bridge/scheduler.py` | ❌ absent |
| **task_worker daemon** | `launcher/bridge/task_worker.py` | ❌ absent |

### 7.2 Patches C++ ajoutés vs upstream
| Patch | Upstream daijro | coryking | mesix971 |
|---|---|---|---|
| `http2-settings-spoofing.patch` | ❌ | ❌ | ✅ (P4) |
| `tls-extensions-spoofing.patch` | ❌ | ❌ | ✅ (P4) |
| `tls-grease-disable.patch` | ❌ | ❌ | ✅ (P4) |
| `creepjs-script-bypass.patch` | ❌ | ❌ | ✅ (P4) |
| `canvas-webgl-pixel-noise.patch` | ❌ | ❌ | ✅ (DRAFT) |
| `navigator-user-agent-data.patch` | ❌ | ❌ | ✅ (DRAFT) |
| `webrtc-ice-candidate-order.patch` | ❌ | ❌ | ✅ (DRAFT) |

### 7.3 Settings étendus
`settings/properties.json` contient **20 nouvelles clés** non présentes upstream :
- `canvas:pixel_noise:*` (4)
- `webgl:readback_noise:*` (3)
- `navigator:userAgentData:*` (10)
- `webrtc:ice:*` (4)
- (+) `http2:*`, `tls:*`, `creepjs:*` du P4

### 7.4 Build pipeline (différences)
| Aspect | Upstream | Fork |
|---|---|---|
| Triggers tag CI | tous tags | tags `launcher-v*` exclus du build Firefox |
| Workflows | `build.yml` | `build.yml` + `launcher-release.yml` |
| Targets matrix | linux/win/macos × x86_64/arm64/i686 | idem + Electron multi-OS |

### 7.5 README + documentation
- **README.md** est en français dans le fork (FR par défaut, EN dans `README.en.md`).
- Documentation interne ajoutée : `P4_PATCHES.md`, `TEST_PLAN.md` (ce fichier), `ISSUES_AUDIT.md`.

### 7.6 Plan d'exécution recommandé

| Phase | Durée | Inclut |
|---|---|---|
| **Smoke** | 5 min | tests `pytest fpgen/tests proxypool/tests` + `npm run typecheck` |
| **Unit** | 15 min | tous modules Python (270+ tests) + `node --test discord-bridge/tests` |
| **Integration** | 1 h | scenarios 5.1, 5.3, 5.4 (un seul navigateur réel) |
| **E2E UI** | 30 min | manuel — créer profil, lancer session, tiling, macros |
| **Patches C++** | 4 h | build local + tests CreepJS/peet.ws pour chaque P4 + 3 drafts |
