# ISSUES_AUDIT.md — Audit complet du toolkit Camoufox

> Audit ligne-par-ligne du code ajouté au fork (`launcher/`, `additions/camoucfg/`, `patches/`, modules Python `fpgen/`, `proxypool/`, `captchapool/`, `queuepool/`, `taskqueue/`, `creepjsscore/`, `humanlike/`, `actions/`).
>
> Convention de gravité :
> - 🔴 **Critique** — corruption de données, crash, faille exploitable
> - 🟠 **Majeur** — comportement incorrect dans un cas réaliste, fuite, blocage
> - 🟡 **Mineur** — code sale, duplication, maintenabilité
>
> Découpage : ce fichier est écrit en plusieurs passes (3a → 3c → 4). Cette première passe couvre **§1 Bugs critiques**.

---

## §1. Bugs critiques (🔴)

### 1.1 — Lancement concurrent sur le même `user_data_dir` → corruption du profil Firefox

**Fichier** : `launcher/bridge/cookie_export.py:140-180`
**Sévérité** : 🔴 Critique

**Symptôme** :
`cookie_export.py` relance Camoufox en mode `launch_persistent_context(user_data_dir=...)` pour récupérer les cookies d'une session. Or, si la session correspondante est encore vivante (process Firefox actif sur le même profil), Firefox détecte le `parent.lock` / `lock` et :
- Sur Linux/macOS : abort immédiat, exception `BrowserType.launchPersistentContext: Browser closed unexpectedly`.
- Sur Windows : Firefox ouvre quand même le profil en parallèle dans certains cas (lockfile lockup-only-on-creation), corrompant `places.sqlite`, `cookies.sqlite`, `prefs.js`.

**Reproduction** :
```python
# session_runner lance Firefox sur ./profiles/abc/
# Pendant ce temps, l'utilisateur clique "Exporter cookies" dans l'UI
# → cookie_export.py:154 lance un second Firefox sur ./profiles/abc/
```

**Correction recommandée** :
1. Ajouter un guard dans `commands.py` côté `cmd_export_cookies` : refuser si `state == "running"` pour la session.
2. Documenter que l'export ne fonctionne qu'après `stop` propre.
3. Alternative : exporter via le protocole Juggler tant que la session est active (pas de second process).

---

### 1.2 — Webhook bloquant freeze le `session_runner`

**Fichier** : `launcher/bridge/webhook.py:81`
**Sévérité** : 🔴 Critique (en pratique)

**Symptôme** :
`webhook.notify()` fait un `requests.post(url, json=payload, timeout=5)` synchrone. Il est appelé depuis :
- `session_runner.py` (boucle principale, événements `session.started`, `session.crashed`, `task.done`)
- `task_worker.py` (idem)
- `scheduler.py` (warmup)

Si Discord/Slack lag ou que le DNS du webhook est lent, le thread principal du runner se bloque jusqu'à 5 s **par événement**. Avec 50 sessions et un événement par session, le tiling/heartbeat décroche pendant 250 s cumulées.

**Pire** : si l'URL renvoie un 429 (rate limit Discord), `requests` ne backoff pas — chaque appel reperd 5 s.

**Correction recommandée** :
- Découpler : `webhook.notify_async(payload)` qui pousse dans une `queue.Queue` consommée par un thread daemon unique.
- Backoff exponentiel sur 429/5xx avec drop si la queue dépasse 1 000 entrées.
- Timeout réduit à 2 s.

---

### 1.3 — `os.kill` sans vérification de réutilisation de PID

**Fichier** : `launcher/bridge/sessions.py:75,278,289`
**Sévérité** : 🔴 Critique sur Linux long-running

**Symptôme** :
`SessionManager._reconcile()` lit le PID stocké dans `session.json`, puis fait `os.kill(pid, 0)` pour vérifier la liveness, et `os.kill(pid, signal.SIGTERM)` pour stopper. Aucune validation que `pid` est toujours **notre** Firefox.

Sur Linux, le PID space est de 32 768 par défaut. Sur un host qui tourne depuis 2 semaines avec beaucoup de spawn/exit, le PID est réutilisé. `_reconcile` relancé après reboot peut tuer un process arbitraire (sshd, systemd-user, chrome de l'utilisateur).

**Correction recommandée** :
- Stocker `start_time` (epoch + jiffies depuis `/proc/<pid>/stat` champ 22) en plus du PID.
- Avant `kill`, comparer `start_time` lu maintenant vs stocké.
- Sur Windows, comparer `GetProcessTimes` (CreationTime).

---

### 1.4 — `subprocess.Popen` sans `close_fds=True` sur POSIX

**Fichier** : `launcher/bridge/sessions.py:255`
**Sévérité** : 🔴 Critique (sécurité)

**Symptôme** :
`Popen([camoufox_bin, ...], env=env)` n'ajoute pas `close_fds=True`. Python 3.7+ a `close_fds=True` par défaut, mais si du code amont a injecté des fd via `pass_fds`, ils fuiteraient. Plus inquiétant : sur Windows, `creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB` est posé, mais `close_fds` interagit mal avec `stdin/stdout/stderr=DEVNULL` non passés explicitement → l'enfant peut hériter des handles console du launcher Electron.

**Correction recommandée** :
- Forcer `stdin=subprocess.DEVNULL, stdout=PIPE, stderr=PIPE, close_fds=True`.
- Récupérer `stdout/stderr` dans un thread reader pour éviter le deadlock pipe-full.

---

### 1.5 — Lecture de `session.json` sans verrou pendant écriture concurrente

**Fichier** : `launcher/bridge/sessions.py:128,129` (write) + multiples lectures `_load_state`
**Sévérité** : 🔴 Critique sur Windows

**Symptôme** :
L'écriture utilise `tmp + os.replace` (atomique sur POSIX, atomique sur Windows depuis Python 3.3 si destination existe — mais **pas** si la destination est ouverte en lecture par un autre process). `commands.py` lit `session.json` à chaque commande HTTP. Si l'UI poll `list_sessions` à 1 Hz pendant que `session_runner` écrit, on peut frapper un `PermissionError: [WinError 5]`.

**Correction recommandée** :
- Wrapper `_safe_read_json(path, retries=5, backoff=0.05)` qui retry sur `PermissionError`.
- Documenter dans `sessions.py` que `os.replace` n'est atomique vis-à-vis du lecteur que sur POSIX.

---

### 1.6 — `cookie_export.py` injecte `page.evaluate` non sanitisé

**Fichier** : `launcher/bridge/cookie_export.py:80,83`
**Sévérité** : 🔴 Critique (XSS auto-infligé peu probable, mais surface étendue)

**Symptôme** :
```python
val = page.evaluate(f"() => localStorage.getItem({json.dumps(key)})")
```
`json.dumps(key)` échappe correctement, donc pas d'injection JS via `key`. **Mais** `page.evaluate()` exécute dans le contexte de la page courante : si le site visité a un MITM JS qui surcharge `localStorage.getItem`, on récupère du faux contenu. Pas un bug d'intégrité de Camoufox, mais l'export peut être empoisonné par une page hostile.

**Correction recommandée** :
- Utiliser `context.storage_state()` de Playwright qui passe par CDP/Juggler, pas par `evaluate`.
- Sinon, exécuter dans un `page.context.new_page()` vide qui share le storage origin (impossible en cross-origin → accepter la limite).

---

### 1.7 — Patches C++ draft non testés sur build complet

**Fichiers** :
- `patches/draft-canvas-pixel-noise.patch`
- `patches/draft-navigator-userAgentData.patch`
- `patches/draft-webrtc-ice-order.patch`

**Sévérité** : 🔴 Critique tant qu'ils sont appliqués

**Symptôme** :
Les 3 patches ajoutés à la dernière session sont préfixés `draft-` car aucun build complet n'a été exécuté pour vérifier :
1. Qu'ils s'appliquent sans `FAILED hunk`.
2. Qu'ils compilent (le patch canvas touche `gfx/2d/DrawTargetSkia.cpp`, sensible aux templates).
3. Qu'ils ne cassent pas les tests CreepJS (introduire trop de bruit canvas → score qui baisse).

**Correction recommandée** :
- Ne PAS inclure dans `patches/` tant que `make dir && make build` ne passe pas.
- Déplacer dans `patches/_drafts/` (préfixe ignoré par `make dir` si on patche le Makefile).
- Documenter dans `FIREFOX_142_UPGRADE_NOTES.md` qu'ils sont en attente.

---

## §2. Race conditions et concurrence (🟠)

### 2.1 — `taskqueue.pop_due` repose sur `os.link` cross-fs

**Fichier** : `taskqueue/queue.py:172,182`
**Sévérité** : 🟠 Majeur

**Symptôme** :
La revendication atomique d'une tâche utilise `os.link(src, claim_path)` puis `os.unlink(src)`. Si la queue (`./tasks/pending/*.json`) est sur un volume différent du dossier de claim (ex. tmpfs vs disk monté `/data`), `os.link` échoue avec `OSError: [Errno 18] Invalid cross-device link`. Conséquence : le worker abandonne, la tâche reste indéfiniment en `pending`.

**Cas réel** : sous Docker, `/tmp` est tmpfs et `/data` est un volume host ⇒ casse silencieuse.

**Correction recommandée** :
- Détecter au démarrage si `os.link` fonctionne (créer puis supprimer un fichier de test).
- Fallback `fcntl.flock` (POSIX) ou `msvcrt.locking` (Windows) sur le fichier directement.
- À défaut : `os.rename` (atomique mais pas exclusif) + double check de présence.

---

### 2.2 — Trois variables `_STOP` distinctes et homonymes

**Fichiers** :
- `launcher/bridge/scheduler.py:66`
- `launcher/bridge/session_runner.py:147`
- `launcher/bridge/task_worker.py:40`

**Sévérité** : 🟠 Majeur (piège de maintenance)

**Symptôme** :
Chaque module définit son propre `_STOP = threading.Event()` au niveau module. Le signal handler `commands.cmd_shutdown` doit se rappeler de set les **trois** indépendamment. Lors d'un futur ajout (`warmup_worker.py`, etc.), on oubliera fatalement le quatrième.

**Correction recommandée** :
- Centraliser dans `launcher/bridge/lifecycle.py` :
  ```python
  STOP = threading.Event()
  ```
- Importer depuis tous les modules. Un seul point d'arrêt global.

---

### 2.3 — `SessionManager._reconcile` vs `session_runner._mark_running`

**Fichiers** :
- `launcher/bridge/sessions.py:128-129` (`SessionManager._save`)
- `launcher/bridge/session_runner.py:_mark_running` (write `state="running"`)

**Sévérité** : 🟠 Majeur

**Symptôme** :
Les deux écrivent dans `session.json` via tmp+replace. Pas de fcntl/lock. Sur POSIX, `os.replace` est atomique mais **last-write-wins** : si `_reconcile` lit `state="starting"`, met à jour à `state="dead"` (croit le PID mort) pendant que le runner écrit `state="running"`, on peut perdre l'écriture.

Scénario concret :
1. T=0: runner démarre, écrit `starting` puis spawn Firefox.
2. T=50ms: `_reconcile` (UI poll) lit `starting`, voit pas de PID, marque `dead` → écrit.
3. T=80ms: runner écrit `running` avec PID → écrase.
4. T=100ms: `_reconcile` revient, lit `running` → OK, mais entre 50 et 80ms l'UI a affiché "dead" pendant un cycle.

**Correction recommandée** :
- Verrou `threading.RLock` partagé via `SessionManager`.
- Toute écriture de `session.json` passe par `manager.update(sid, **fields)` qui acquiert le lock.

---

### 2.4 — `humanlike/cursor.py` `_last_pos` non thread-safe

**Fichier** : `humanlike/cursor.py:30,37,41,173`
**Sévérité** : 🟠 Majeur en multi-page concurrent

**Symptôme** :
`_last_pos: dict[int, tuple[float, float]] = {}` au niveau module, indexé par `id(page)`. Aucun `Lock`. Si l'utilisateur lance 2 actions concurrentes sur 2 pages distinctes (légitime), Python protège le `dict.__setitem__` via le GIL — OK. **Mais** si deux mouvements concurrents sur la **même** page (rare mais possible si l'action DSL fait un `repeat` parallèle) lisent puis écrivent, on a une lecture stale.

Plus grave : `id(page)` peut être réutilisé après garbage collection ⇒ deux pages successives partagent la position du curseur. L'humanlike démarre alors d'une position non valide pour la nouvelle page.

**Correction recommandée** :
- Stocker la position dans `page.__cursor_last_pos__` (attribut de l'objet page Playwright, garbage-collecté avec lui).
- Sinon, `weakref.WeakKeyDictionary()`.

---

### 2.5 — Signal handler vs `Popen.wait()`

**Fichier** : `launcher/bridge/session_runner.py:waitpid loop`
**Sévérité** : 🟠 Majeur sur POSIX

**Symptôme** :
La boucle de surveillance fait `proc.poll()` à chaque tick (~2 s). Si l'utilisateur envoie `SIGINT` au launcher Electron, le signal se propage au session_runner qui interrompt `time.sleep` mais `proc.poll()` continue de retourner `None` (Firefox n'a pas reçu le signal car `CREATE_NEW_PROCESS_GROUP` sur Windows et `start_new_session=True` sur POSIX).

Résultat : à l'arrêt du launcher, Firefox reste vivant en orphelin.

**Correction recommandée** :
- Au shutdown global, itérer `manager.list()` et envoyer `SIGTERM` à chaque PID, puis attendre 5 s avec backoff, puis `SIGKILL`.
- Documenter que les sessions survivent volontairement au crash du launcher (feature) mais pas au shutdown propre.

---

### 2.6 — `cookie_export` et `webhook` partagent `requests.Session()` ?

**Fichiers** :
- `launcher/bridge/cookie_export.py:154`
- `launcher/bridge/webhook.py:81`

**Sévérité** : 🟡 Mineur (potentiel)

**Symptôme** :
Chaque module crée un `requests.post(...)` sans Session partagée. Pas de pool de connexions ⇒ TLS handshake refait à chaque appel. Pas une race condition stricto sensu, mais sous charge (50 webhooks/sec), TIME_WAIT sockets s'accumulent.

**Correction recommandée** :
- `_HTTP = requests.Session()` au niveau module avec `HTTPAdapter(pool_connections=10, pool_maxsize=20)`.

---

### 2.7 — `scheduler.py` warmup et `task_worker.py` peuvent lancer la même session deux fois

**Fichiers** :
- `launcher/bridge/scheduler.py` (start_session pour warmup)
- `launcher/bridge/task_worker.py` (start_session pour run)

**Sévérité** : 🟠 Majeur

**Symptôme** :
Si une tâche est planifiée à T+1h et qu'un warmup est aussi planifié à T+1h±epsilon pour la même `session_id`, les deux workers peuvent appeler `manager.start(sid)` simultanément. `SessionManager.start` vérifie `state != "running"` puis spawn — pas atomique. Les deux peuvent passer le check et lancer 2 Firefox sur le même profil → cf. §1.1.

**Correction recommandée** :
- `manager.start(sid)` doit acquérir un lock per-session (`self._locks[sid]`) avant le check d'état.
- Refuser explicitement si `state in ("starting", "running")`.

---

## §3. Edge cases non gérés (🟠/🟡)

### 3.1 — Profil sans `prefs.js` après crash
**Fichier** : `launcher/bridge/sessions.py` (init profile)
**Sévérité** : 🟠 Majeur

Si Firefox crashe pendant l'écriture de `prefs.js`, on retrouve un fichier de 0 octet. Au prochain `start`, Firefox réinitialise toutes les prefs (locale par défaut, fingerprint perdu). Le runner ne détecte pas — il croit que le profil est sain.

**Correction** : checksum/taille minimale sur `prefs.js` au démarrage. Si invalide → restauration depuis `prefs.js.bak` (Firefox en crée un automatiquement).

---

### 3.2 — Proxy avec mot de passe contenant `@` ou `:`
**Fichier** : `proxypool/parser.py`
**Sévérité** : 🟠 Majeur

Format `user:pass@host:port` non échappé. Un mot de passe contenant `@` (`P@ssw0rd`) casse le split. Pas de URL-decode.

**Correction** : parser via `urllib.parse.urlsplit("http://" + raw)` qui gère correctement les credentials.

---

### 3.3 — `proxypool` round-robin sans persistance
**Fichier** : `proxypool/store.py`
**Sévérité** : 🟡 Mineur

L'index courant est en mémoire. Au restart, on revient à 0 → premier proxy hammeré. Avec 1 000 sessions et 10 proxies, le proxy #0 prend 100 sessions au boot.

**Correction** : persister le pointeur dans `state.json`, ou utiliser un hash modulo `session_id`.

---

### 3.4 — `fpgen.profile` ne valide pas la cohérence OS/UA
**Fichier** : `fpgen/profile.py:147`
**Sévérité** : 🟠 Majeur (fingerprint detectable)

Rien n'empêche de générer `os="windows"` + `userAgent="Mozilla/5.0 (Macintosh; ...)"`. Les sites de fingerprinting (FpJS) recoupent et flag.

**Correction** : `__post_init__` qui vérifie cohérence (OS dans UA, plateforme JS, fonts par OS, timezone par geo IP du proxy).

---

### 3.5 — `humanlike.cursor` mouvement hors viewport
**Fichier** : `humanlike/cursor.py:173`
**Sévérité** : 🟡 Mineur

La courbe de Bézier peut sortir du viewport (control points trop éloignés). Playwright clamp silencieusement, mais le flot de coordonnées devient suspicieux (positions hors écran).

**Correction** : clamp les control points dans `[0, viewport_width-1] × [0, viewport_height-1]`.

---

### 3.6 — `actions.repeat` sans limite de profondeur
**Fichier** : `actions/runner.py`
**Sévérité** : 🟠 Majeur (DoS auto-infligé)

Une action `repeat` imbriquée sans condition de sortie boucle infiniment. Aucun max_iterations global.

**Correction** : `MAX_ACTIONS_PER_RUN = 10_000`, lever exception passé ce seuil.

---

### 3.7 — `creepjsscore` parser fragile aux changements de DOM
**Fichier** : `creepjsscore/scorer.py`
**Sévérité** : 🟡 Mineur

Le scoring extrait via `page.locator("#fingerprint")` ou similaire. Si CreepJS change son CSS-id, retour `None` silencieux → score=0 réputé "fail" alors que c'est un bug du scraper.

**Correction** : lever `CreepJSParseError` au lieu de retourner `None`. Logger le HTML brut pour diagnostic.

---

### 3.8 — `taskqueue` tâche sans `id`
**Fichier** : `taskqueue/queue.py`
**Sévérité** : 🟡 Mineur

`push(task)` n'exige pas que `task["id"]` soit unique. Deux push avec le même id → un seul fichier. Silencieux.

**Correction** : si `id` existe, `raise DuplicateTaskError`. Ou auto-uuid si manquant.

---

### 3.9 — `queuepool` (Queue-it) sans gestion du captcha
**Fichier** : `launcher/bridge/queueit_client.py`
**Sévérité** : 🟠 Majeur

Si Queue-it présente un captcha pendant le wait (cas connu sur Nike SNKRS), le client poll JSON ignore le challenge HTML et boucle sur 200 OK avec body inattendu.

**Correction** : détecter `Content-Type: text/html` ou `redirect_url` pointant vers `/challenge`, basculer en mode browser (lancer une page Camoufox sur l'URL captcha).

---

### 3.10 — `auto_tile` avec écran portrait
**Fichier** : `launcher/bridge/tiling.py`
**Sévérité** : 🟡 Mineur

La grille assume `screen_width > screen_height`. Sur un moniteur portrait (1080×1920), le calcul `cols = ceil(sqrt(n))` produit des tuiles très larges et basses.

**Correction** : `cols, rows = tile_grid(n, aspect=screen_width/screen_height)` qui adapte au ratio.

---

### 3.11 — `cookie_export` cookies HTTPOnly invisibles côté JS
**Fichier** : `launcher/bridge/cookie_export.py:80`
**Sévérité** : 🟠 Majeur

`page.evaluate("document.cookie")` rate les HTTPOnly. Pour un site comme Cloudflare (`__cf_bm`, `cf_clearance` souvent HTTPOnly), l'export est incomplet → la session restaurée échoue.

**Correction** : utiliser `context.cookies()` (Playwright API native, voit HTTPOnly).

---

## §4. Fuites de ressources (🟠)

### 4.1 — `humanlike/cursor.py` `_last_pos` jamais purgé
**Fichier** : `humanlike/cursor.py:30`
**Sévérité** : 🟠 Majeur (fuite mémoire long-running)

`_last_pos: dict[int, tuple]` accumule une entrée par `id(page)` ouverte. Aucun cleanup à la fermeture de la page. Sur un worker qui ouvre 10 000 pages/jour, le dict grossit indéfiniment.

**Correction** : `weakref.WeakKeyDictionary` (purge auto quand page collectée). Cf. §2.4.

---

### 4.2 — `Popen` sans `wait()` pour les processus terminés
**Fichier** : `launcher/bridge/sessions.py:255` + boucle de monitoring
**Sévérité** : 🟠 Majeur sur Linux

Quand Firefox exit, le runner détecte via `proc.poll()` mais ne fait pas `proc.wait()`. Le process reste **zombie** jusqu'au shutdown du runner. Avec 50 sessions/jour, on accumule 50 zombies dans `ps -ef | grep <defunct>`.

**Correction** : appeler `proc.wait(timeout=1)` après détection de exit, ou wrapper dans `subprocess.run` géré.

---

### 4.3 — `page.context` non fermé après `cookie_export`
**Fichier** : `launcher/bridge/cookie_export.py:140-180`
**Sévérité** : 🟠 Majeur

Le `try`/`finally` n'a pas de `context.close()` explicite — uniquement `playwright.stop()`. Si une exception remonte avant `playwright.stop()`, Firefox reste actif.

**Correction** : `with sync_playwright() as p:` + `with p.firefox.launch_persistent_context(...) as ctx:`.

---

### 4.4 — `requests.post` sans `Session` → fuite de sockets TIME_WAIT
**Fichiers** :
- `launcher/bridge/webhook.py:81`
- `launcher/bridge/cookie_export.py:154`
- `launcher/bridge/queueit_client.py`

**Sévérité** : 🟡 Mineur

Cf. §2.6. À fort débit, on peut épuiser les ports éphémères (Linux par défaut 32 768–60 999, soit ~28k ports). Sur 60s, 5/s × 60 = 300 sockets — OK. Mais à 50/s sustained, on touche le mur en ~10 min.

**Correction** : `requests.Session()` partagée par module.

---

### 4.5 — Logs JSONL non rotés
**Fichier** : `launcher/bridge/logger.py` (à confirmer)
**Sévérité** : 🟠 Majeur

`session.log` et `runner.log` sont append-only sans rotation. Une session qui tourne 1 mois génère plusieurs Go.

**Correction** : `RotatingFileHandler(maxBytes=10MB, backupCount=5)`.

---

### 4.6 — `tiling.py` SetWindowPos sans GetLastError
**Fichier** : `launcher/bridge/tiling.py`
**Sévérité** : 🟡 Mineur

Si `SetWindowPos` échoue (HWND fermé entre énumération et call), pas de log. Le tiling silencieusement skip une fenêtre.

**Correction** : log warning si retour 0, `GetLastError()` pour diagnostic.

---

### 4.7 — `taskqueue` claim files orphelins après crash
**Fichier** : `taskqueue/queue.py:172,182`
**Sévérité** : 🟠 Majeur

Si le worker crash entre `os.link(claim)` et le traitement, le fichier reste dans `./tasks/claimed/` indéfiniment. Tâche perdue.

**Correction** : sweeper périodique : claims plus vieux que `task_timeout` (ex. 1h) → relâchés vers `pending/`.

---

### 4.8 — Threads daemon sans join
**Fichiers** : `scheduler.py`, `task_worker.py`, `session_runner.py`

**Sévérité** : 🟡 Mineur

Threads démarrés en `daemon=True` sans `join()` au shutdown. Sur kill propre, les écritures en cours de `session.json` peuvent être tronquées.

**Correction** : registry global de threads, `for t in threads: t.join(timeout=5)` au shutdown.

---

## §5. Dead code et duplication (🟡)

### 5.1 — `from dataclasses import asdict as _asdict` dupliqué 5 fois
**Fichier** : `launcher/bridge/commands.py:99,139,669,774,841`
**Sévérité** : 🟡 Mineur

Le même import inline est répété dans 5 handlers distincts. Vestige de copy-paste.

**Correction** : un unique `from dataclasses import asdict` en tête de module.

---

### 5.2 — `commands.py` à 903 lignes — god module
**Fichier** : `launcher/bridge/commands.py`
**Sévérité** : 🟡 Mineur (dette technique)

46 commandes HTTP dans un seul fichier. Mélange routing, validation, business logic. Difficile à tester unitairement.

**Correction** : découper par domaine :
- `commands/sessions.py`
- `commands/tasks.py`
- `commands/proxies.py`
- `commands/captchas.py`
- `commands/cookies.py`
- `commands/__init__.py` qui agrège la table de routing.

---

### 5.3 — `Profile` dataclass à ~70 champs
**Fichier** : `fpgen/profile.py:147`
**Sévérité** : 🟡 Mineur

Un seul dataclass mélange : navigator, screen, WebGL, audio, fonts, geo, locale, battery, voices. Toute modif d'un sous-domaine recompile tout.

**Correction** : décomposer en sous-dataclasses :
```python
@dataclass
class NavigatorProfile: ...
@dataclass
class ScreenProfile: ...
@dataclass
class WebGLProfile: ...
@dataclass
class Profile:
    navigator: NavigatorProfile
    screen: ScreenProfile
    webgl: WebGLProfile
    ...
```

---

### 5.4 — `humanlike/cursor.py` fonctions dupliquées dans `actions/runner.py`
**Sévérité** : 🟡 Mineur

`actions/runner.py` réimplémente une version simplifiée du mouvement Bezier au lieu d'importer `humanlike.move()`. Maintenance double.

**Correction** : `actions/runner.py` importe `from humanlike import move, type_text, click`.

---

### 5.5 — Constantes magiques répétées
**Fichiers** : multiples
**Sévérité** : 🟡 Mineur

- `5` (timeout webhook) en dur dans `webhook.py`
- `2.0` (poll interval) en dur dans `session_runner.py`, `task_worker.py`, `scheduler.py`
- `os.path.join("./profiles", sid)` duppliqué partout

**Correction** : `launcher/bridge/config.py` avec constantes nommées + lecture depuis `~/.camoufox/config.json`.

---

### 5.6 — `actions` types `if`/`repeat` ne valident pas leurs payloads
**Fichier** : `actions/runner.py`
**Sévérité** : 🟡 Mineur

Le DSL accepte `{"type": "if", "condition": "...", "then": [...]}` sans schema validation. Une faute de frappe silently no-op.

**Correction** : utiliser `pydantic` ou schema JSON pour valider à `parse_action()`.

---

### 5.7 — Imports non utilisés
**Fichiers** : à scanner avec `ruff check --select F401`
**Sévérité** : 🟡 Mineur

Probable accumulation après les multiples refactors de session.

**Correction** : `ruff check --fix` en pre-commit.

---

## §6. Sécurité (🔴/🟠)

### 6.1 — Bridge HTTP sans auth bind sur `127.0.0.1` ?
**Fichier** : `launcher/bridge/server.py`
**Sévérité** : 🔴 Critique si bind 0.0.0.0

À vérifier : si `server.py` bind `0.0.0.0` au lieu de `127.0.0.1`, **n'importe quelle machine du LAN** peut lancer/tuer des sessions, exporter cookies, lire proxies+passwords.

**Correction** :
1. Forcer bind `127.0.0.1` (loopback only).
2. Token aléatoire généré au démarrage, stocké dans `~/.camoufox/bridge.token`, requis dans header `X-Bridge-Token`.
3. Refus si origin différente.

---

### 6.2 — Proxies stockés en clair dans `state.json`
**Fichier** : `proxypool/store.py`
**Sévérité** : 🟠 Majeur

`./proxies.json` contient `user:pass@host:port` en clair, mode 0644. Lisible par tous les users du host.

**Correction** :
- chmod 0600 à la création.
- Optionnel : chiffrement AES-GCM avec clé dérivée du keychain OS (`keyring` Python).

---

### 6.3 — Webhooks vers URL utilisateur sans validation
**Fichier** : `launcher/bridge/webhook.py:81`
**Sévérité** : 🟠 Majeur (SSRF)

L'URL webhook est fournie par l'utilisateur via l'UI. Aucune validation. Si un utilisateur configure `http://169.254.169.254/latest/meta-data/` (AWS IMDS) ou `http://127.0.0.1:8080/admin`, le launcher fait la requête depuis le host → SSRF dans les logs.

**Correction** : whitelist scheme `https://`, refus si IP privée/loopback (RFC 1918, link-local), DNS-rebinding protection (résoudre puis vérifier l'IP).

---

### 6.4 — `eval_js` dans le DSL d'actions exécute du JS arbitraire
**Fichier** : `actions/runner.py`
**Sévérité** : 🟠 Majeur (par design, mais à documenter)

L'action `{"type": "eval_js", "code": "..."}` fait `page.evaluate(code)`. Si un script de tâches vient d'une source non fiable (ex. téléchargé depuis un serveur de campagne), exécution JS dans le contexte du site visité.

**Correction** :
- Documenter clairement que `eval_js` est privileged.
- Optionnel : flag `--allow-eval-js` au démarrage du worker, désactivé par défaut.

---

### 6.5 — `Popen([camoufox_bin, ...args])` avec args utilisateur
**Fichier** : `launcher/bridge/sessions.py:255`
**Sévérité** : 🟠 Majeur

Si `args` injectent un `--remote-debugging-port=0` ou `--user-data-dir=/etc`, on peut détourner le profil. Liste blanche d'args manquante.

**Correction** : whitelist stricte des args acceptés (`--headless`, `--width`, `--height`, etc.). Refus de tout `--user-data-dir`, `--remote-debugging-*`, `--new-window`.

---

### 6.6 — `cookie_export.py` écrit sur disque sans atomicité
**Fichier** : `launcher/bridge/cookie_export.py`
**Sévérité** : 🟡 Mineur

Si crash pendant écriture du JSON cookies, fichier tronqué = restore ratée silencieusement.

**Correction** : tmp + os.replace (cf. §1.5).

---

### 6.7 — Logs contiennent les valeurs de cookies / proxy passwords ?
**Fichiers** : `webhook.py`, `cookie_export.py`, `commands.py`
**Sévérité** : 🟠 Majeur (à vérifier)

Si `logger.info(f"payload={payload}")` est appelé avec un payload qui contient cookies/proxy creds, ils fuient dans les logs (et potentiellement dans les webhooks).

**Correction** : redaction filter `RedactSecretsFilter` qui masque `password=***`, `Set-Cookie: ***` dans tous les loggers.

---

### 6.8 — Pas de signature des actions DSL
**Fichier** : `actions/runner.py`
**Sévérité** : 🟡 Mineur

Si les fichiers d'actions sont stockés dans un dossier partagé (ex. NAS d'équipe), un attaquant peut modifier un script à distance pour ajouter `eval_js` malveillant.

**Correction** : signer les fichiers d'actions avec une clé HMAC par worker, vérifier au load.

---

## §7. Performance (🟠/🟡)

### 7.1 — Polling 2s pour 50 sessions = 25 stat() / sec
**Fichier** : `launcher/bridge/sessions.py` `_reconcile`
**Sévérité** : 🟡 Mineur

Chaque cycle, le manager fait `os.stat(session.json)` + `os.kill(pid, 0)` pour chaque session. À 50 sessions × 0.5 Hz = 25 syscalls/s. Pas critique, mais sur Windows les syscalls fs sont 10× plus chers que Linux.

**Correction** : event-driven via `inotify` (Linux) / `ReadDirectoryChangesW` (Windows) sur `./profiles/`. Fallback poll à 5s.

---

### 7.2 — `page.url` interrogé toutes les 2s par session
**Fichier** : `launcher/bridge/session_runner.py:374`
**Sévérité** : 🟠 Majeur

`page.url` traverse Juggler → IPC vers le content process. Si la page est sur un site lent (ex. Cloudflare en cours de challenge), l'appel peut bloquer plusieurs centaines de ms. Multiplié par 50 sessions, le runner principal lag.

**Correction** :
- Délégation par session : un thread par session pour son monitoring (déjà partiellement le cas).
- Cache local de `last_known_url` mis à jour par les events Juggler (`Page.frameNavigated`).

---

### 7.3 — `creepjsscore` ré-instancie un browser par run
**Fichier** : `creepjsscore/scorer.py`
**Sévérité** : 🟡 Mineur

Chaque appel à `score(profile)` lance un nouveau Camoufox, attend chargement CreepJS (~30s), parse, ferme. Pour benchmarker 100 profils, 50 min.

**Correction** : pool de browsers réutilisables (1 browser → N pages → N profils via context swap).

---

### 7.4 — `humanlike.cursor` calcule la trajectoire complète d'avance
**Fichier** : `humanlike/cursor.py`
**Sévérité** : 🟡 Mineur

La courbe Bezier est échantillonnée en N points (~50–100), tous calculés avant le premier `mouse.move`. Sur des trajectoires longues (full-screen drag), pic CPU.

**Correction** : générator yield-on-the-fly, calcul lazy au rythme du `await sleep(dt)`.

---

### 7.5 — `fpgen.profile` ne cache pas le pool BrowserForge
**Fichier** : `fpgen/profile.py`
**Sévérité** : 🟡 Mineur

Si BrowserForge charge sa base statistique à chaque appel (`from browserforge.fingerprints import FingerprintGenerator()`), c'est ~10 MB lus chaque fois.

**Correction** : `_GENERATOR = FingerprintGenerator()` au niveau module, lazy.

---

### 7.6 — `tiling.py` re-énumère toutes les fenêtres à chaque tile
**Fichier** : `launcher/bridge/tiling.py`
**Sévérité** : 🟡 Mineur

`EnumWindows` itère toutes les fenêtres du desktop (~300 sur un Windows utilisé). Pour 50 sessions, on enumère 50× → 15 000 itérations.

**Correction** : un seul `EnumWindows` qui retourne dict `pid → hwnd`, puis lookup.

---

### 7.7 — Logs JSONL avec `json.dumps(indent=2)`
**Fichier** : à confirmer
**Sévérité** : 🟡 Mineur

Si les logs sont indentés, taille ×3 et IO disque proportionnel.

**Correction** : `json.dumps(obj, separators=(",", ":"))` en logs prod, indent uniquement en dev.

---

### 7.8 — Pas de circuit breaker sur les webhooks
**Fichier** : `launcher/bridge/webhook.py`
**Sévérité** : 🟠 Majeur

Si Discord est en panne, chaque appel timeout 5s. À 1 event/s, 1 thread bloqué en permanence par le retry naïf.

**Correction** : circuit breaker ouvert 60s après 3 échecs consécutifs, half-open ensuite.

---

## §8. Architecture / dette technique

### 8.1 — Couplage fort `commands.py` ↔ `SessionManager`
**Sévérité** : 🟡 Mineur

`commands.py` accède directement à `manager._state` dans certains handlers. Casse l'encapsulation.

**Correction** : exposer uniquement `manager.list()`, `manager.get(sid)`, `manager.update()`. Marquer `_state` comme privé strict.

---

### 8.2 — Pas de tests unitaires sur les modules Python
**Sévérité** : 🟠 Majeur (dette)

Aucun `test_*.py` dans `fpgen/`, `proxypool/`, `taskqueue/`, `humanlike/`. Régression silencieuse à chaque refactor.

**Correction** : `pytest` + `tests/` minimum :
- `test_proxypool.py` (parser, round-robin)
- `test_taskqueue.py` (push/claim/pop_due, race avec 2 workers)
- `test_humanlike.py` (Bezier dans viewport)
- `test_fpgen.py` (cohérence OS/UA)

---

### 8.3 — Pas de séparation domain / infrastructure
**Sévérité** : 🟡 Mineur

`SessionManager` mélange logique métier (états valides) et IO (lecture session.json, Popen Firefox). Difficile à tester sans vrai disque.

**Correction** : interface `SessionStorage` (memory/file), injection de dépendance.

---

### 8.4 — Pas de schema versioning sur `session.json`
**Sévérité** : 🟠 Majeur

Si le format évolue (nouveau champ obligatoire), les sessions existantes deviennent invalides. Aucun champ `schema_version`.

**Correction** : `{"schema_version": 1, ...}` + migration automatique au load.

---

### 8.5 — Frontend Electron : Zustand store global non typé strictement
**Fichier** : `launcher/electron/src/store/`
**Sévérité** : 🟡 Mineur (à vérifier)

Si le store mélange data backend et UI state (modals, drawer ouvert), refresh → fuites d'état UI dans les snapshots.

**Correction** : split en `useSessionsStore`, `useUIStore`.

---

### 8.6 — Pas de healthcheck du bridge
**Fichier** : `launcher/bridge/server.py`
**Sévérité** : 🟡 Mineur

L'UI Electron ne sait pas si le bridge est vivant sans tenter une commande. Pas d'endpoint `GET /health`.

**Correction** : route `/health` qui retourne `{"ok": true, "uptime": N, "sessions": M}`.

---

### 8.7 — Patches `additions/juggler/` sans test de régression
**Sévérité** : 🟠 Majeur

Les modifs Juggler (sandboxing, `navigator.webdriver`) peuvent régresser à chaque upgrade Firefox sans qu'on s'en rende compte.

**Correction** : suite Playwright minimum qui assert :
- `navigator.webdriver === undefined`
- `window.chrome === undefined` (ou structure attendue)
- Pas de `__playwright_*` globals leaks

---

### 8.8 — Pas de versioning des patches
**Fichier** : `patches/`
**Sévérité** : 🟡 Mineur

Les patches n'ont pas de header `# Patch-Version: 1` ni de `# Targets-Firefox: 142.0.1`. Difficile de tracker quelles versions ont été testées avec quel patch.

**Correction** : header standardisé en commentaire en tête de chaque `.patch`.

---

**Fin Turn 4b.** À suivre :
- Turn 4c : §9 Issues upstream + §10 Top 10 recommandations
