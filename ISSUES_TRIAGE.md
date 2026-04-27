# ISSUES_TRIAGE.md — Triage post-vérification de ISSUES_AUDIT.md

> Reclassement de chaque bug listé dans `ISSUES_AUDIT.md` après vérification du code source réel (lecture de `sessions.py`, `cookie_export.py`, `webhook.py`, `humanlike/cursor.py`, `taskqueue/queue.py`, `proxypool/parsers.py`, `session_runner.py`, `scheduler.py`, `task_worker.py`, `__main__.py`).
>
> Convention :
> - 🔴 **CRITIQUE** — crash, perte de données, faille de sécurité exploitable
> - 🟠 **MAJEUR** — fonctionnalité cassée mais contournable
> - 🟡 **MINEUR** — cosmétique, propreté, perf marginale
> - ⚪ **FAUX POSITIF** — claim de l'audit invalidé après lecture du code
>
> Format : section audit (§X.Y) → claim original → vérification → classement final.

---

## §1. Bugs critiques (audit)

### §1.1 — Lancement concurrent sur le même `user_data_dir`
**Vérification** : `cookie_export.py:59-64` lance bien `Camoufox(persistent_context=True, user_data_dir=...)` sur le profil. Aucun guard côté commande pour empêcher l'export pendant que la session est `running`. Le profil Firefox a un lockfile (`parent.lock`) → collision réelle.
**Classement final** : 🔴 **CRITIQUE** — corruption confirmée possible.

### §1.2 — Webhook bloquant freeze le runner
**Vérification** : `webhook.py:81` confirme `requests.post(hook, json=payload, timeout=5.0)` synchrone. `session_runner._main_loop` (ligne 366-405) appelle `webhook_notify` depuis sa boucle principale (ligne 399-402 pour queue front, ligne 324-327 pour crash). Pas de thread séparé.
**Classement final** : 🟠 **MAJEUR** — la boucle principale est dans un sous-process dédié à UNE session, donc le freeze de 5 s n'affecte qu'elle. Ce n'est pas le runner global qui freeze. Sévérité revue à la baisse.

### §1.3 — `os.kill` sans validation de réutilisation de PID
**Vérification** : `sessions.py:75` → `os.kill(pid, 0)` POSIX sans start_time check. Sur Windows (`_pid_alive_windows` lignes 83-110), utilise `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess` qui retourne `STILL_ACTIVE=259` — robuste vs PID reuse. POSIX reste vulnérable.
**Classement final** : 🟠 **MAJEUR** sur POSIX uniquement (Windows OK). Risque réel mais nécessite host long-running + PID wrap.

### §1.4 — `Popen` sans `close_fds=True`
**Vérification** : `sessions.py:236-255` montre `popen_kwargs` avec `stdin=subprocess.DEVNULL, stdout=log_fh, stderr=subprocess.STDOUT`. Python 3.7+ a `close_fds=True` par défaut. `creationflags` Windows correctement posé pour breakaway.
**Classement final** : ⚪ **FAUX POSITIF** — la claim de l'audit était infondée. Le code est correct.

### §1.5 — Lecture de `session.json` sans verrou pendant écriture
**Vérification** : `sessions.py:125-129` (write tmp + replace) et `sessions.py:131-135` (read). Pas de retry sur `PermissionError`. Sur Windows, `os.replace` lit-pendant-écriture peut échouer rarement.
**Classement final** : 🟡 **MINEUR** — fenêtre très étroite (microseconde de replace), erreur intermittente possible mais pas corruption.

### §1.6 — `cookie_export.py` injecte `page.evaluate` non sanitisé
**Vérification** : `cookie_export.py:80-85`. Le code passé à `page.evaluate` est `() => Object.fromEntries(Object.entries(localStorage))` — **aucune** interpolation utilisateur. Pas d'injection possible.
**Classement final** : ⚪ **FAUX POSITIF** — pas de surface d'attaque.

### §1.7 — Patches drafts non testés
**Vérification** : `ls patches/draft-*` → aucun fichier. Les patches existent sous `canvas-webgl-pixel-noise.patch`, `webrtc-ice-candidate-order.patch`, `webrtc-ip-spoofing.patch` (pas préfixés draft). Le navigator.userAgentData n'existe pas du tout dans `patches/`.
**Classement final** : ⚪ **FAUX POSITIF** sur la nomenclature. Reste un 🟠 **MAJEUR** sur l'absence de validation de build pour les 3 patches mentionnés (à vérifier en CI).

---

**Bilan §1 (7 entrées)** :
- 🔴 Critique : 1 (§1.1)
- 🟠 Majeur : 3 (§1.2 rétrogradé, §1.3 POSIX-only, §1.7 partiel)
- 🟡 Mineur : 1 (§1.5)
- ⚪ Faux positif : 2 (§1.4, §1.6)

**Fin T2a.** Prochain : T2b §2 Race conditions.

---

## §2. Race conditions et concurrence (audit)

### §2.1 — `taskqueue.pop_due` `os.link` cross-fs
**Vérification** : `taskqueue/queue.py:182` confirme `os.link(tmp, lock)`. La queue root et le claim sont dans le même répertoire (`self.root`), donc même filesystem garanti par construction. Le risque cross-fs n'existe que si l'utilisateur monte un volume au milieu de `self.root` (rarissime).
**Classement final** : 🟡 **MINEUR** — risque réel mais cas d'usage exotique. Le module documente lignes 25-31 que c'est "for a few dozen tasks/sec max".

### §2.2 — Trois variables `_STOP` distinctes
**Vérification** : confirmé 3 fichiers (`scheduler.py:66`, `session_runner.py:147`, `task_worker.py:40`). **MAIS** ces 3 fichiers sont chacun des `python -m` séparés — ce sont des **processus distincts**, pas des threads dans le même process. Chaque process a son propre signal handler. Aucun besoin de centraliser : c'est l'architecture attendue.
**Classement final** : ⚪ **FAUX POSITIF** — pas de partage de mémoire entre les 3, donc pas de bug.

### §2.3 — `SessionManager._reconcile` vs `session_runner._mark_running`
**Vérification** : `sessions.py:155-167` (`_reconcile`) ne write **que** quand le state transitionne (`STARTING → RUNNING` ou `→ STOPPED`). `session_runner._mark_running` (lignes 460-471) écrit aussi via tmp + os.replace. Les deux peuvent se télescoper sur Windows brièvement. Sur POSIX, `os.replace` est atomique.
**Classement final** : 🟡 **MINEUR** sur POSIX, 🟠 **MAJEUR** sur Windows si forte concurrence UI.

### §2.4 — `_last_pos` non thread-safe
**Vérification** : `humanlike/cursor.py:30-33` confirme dict module-level. **Le commentaire ligne 31-32 documente explicitement** "Entries live for the lifetime of the process — acceptable for automation scripts". Pas de threading dans humanlike (Playwright sync est mono-thread). Pas de race en pratique.
**Classement final** : ⚪ **FAUX POSITIF** sur la race condition. La fuite mémoire reste valide → cf. §4.1.

### §2.5 — Signal handler vs `Popen.wait()`
**Vérification** : `session_runner._main_loop:366` boucle sur `not _STOP` avec `time.sleep(0.25)`. Le `_handle_signal` set `_STOP=True`. Pas de `Popen.wait()` — le runner *est* le child du browser, pas son parent. Le browser est lancé par `Camoufox(...)` context manager qui gère son propre cleanup.
**Classement final** : ⚪ **FAUX POSITIF** — le runner n'a pas de Popen à waiter ; c'est le browser qui est dans un `with` block.

### §2.6 — `requests.Session()` non partagée
**Vérification** : `webhook.py:81` et `cookie_export.py:154` créent un `requests.post()` à chaque appel sans Session. Confirmé.
**Classement final** : 🟡 **MINEUR** — perf marginale, jamais critique sauf à 50+ webhooks/sec sustained.

### §2.7 — Warmup vs task_worker double-launch
**Vérification** : `task_worker.py:72-115` — `_dispatch_launch_session` et `_dispatch_warmup` sont 2 actions distinctes du même worker. Chaque action génère un nouveau `session_id` via `Session.new_id()`, mais elles partagent `_profile_user_data_dir(profile_id)` (line 144 de session_runner). Si user enqueue les deux pour le même `profile_id` simultanément, 2 Camoufox sur le même `user_data_dir` → corruption (cf. §1.1).
**Classement final** : 🔴 **CRITIQUE** — même cause racine que §1.1 mais via une voie différente (taskqueue).

---

**Bilan §2 (7 entrées)** :
- 🔴 Critique : 1 (§2.7)
- 🟠 Majeur : 1 (§2.3 sur Windows)
- 🟡 Mineur : 3 (§2.1, §2.3 POSIX, §2.6)
- ⚪ Faux positif : 3 (§2.2, §2.4, §2.5)

**Fin T2b.** Prochain : T2c §3 Edge + §4 Leaks.
