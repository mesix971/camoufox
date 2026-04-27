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

**Fin Turn 3a.** À suivre :
- Turn 3b : §2 Race conditions et concurrence
- Turn 3c : §3 Edge cases + §4 Fuites de ressources
- Turn 4 : §5–§10 (dead code, sécurité, perf, archi, upstream, recommandations)
