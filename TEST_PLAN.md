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

*(suite dans le prochain turn — sections 4 à 7)*
