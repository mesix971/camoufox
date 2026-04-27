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
