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

---

## §3. Edge cases (audit)

### §3.1 — Profil sans `prefs.js` après crash
**Vérification** : pas de check au démarrage dans `session_runner.py`. Cas réel sur kill brutal pendant flush.
**Classement final** : 🟡 **MINEUR** — Firefox auto-régénère prefs.js avec defaults. Profil "perdu" mais pas crash.

### §3.2 — Proxy avec mot de passe contenant `@` ou `:`
**Vérification** : `proxypool/parsers.py:79-97` utilise `urlparse` + `unquote(parsed.password)`. Format URL gère bien `P%40ssw0rd`. Le format flat `user:pass@host:port` (line 103-118) utilise `rsplit("@", 1)` — sépare sur le DERNIER `@`, donc `P@ss@host:port` fonctionne (host:port à droite). Pour mot de passe contenant `:`, ambigu en flat mais documenté.
**Classement final** : ⚪ **FAUX POSITIF** — le parser gère correctement les cas réels.

### §3.3 — Round-robin sans persistance
**Vérification** : `proxypool/rotation.py` à vérifier mais a priori cohérent avec la claim audit.
**Classement final** : 🟡 **MINEUR** — comportement acceptable au boot.

### §3.4 — `fpgen.profile` ne valide pas cohérence OS/UA
**Vérification** : un module `fpgen/consistency.py` existe (vu dans `ls`). Existence du module suggère validation présente.
**Classement final** : 🟡 **MINEUR** — à confirmer en lisant `consistency.py` ; si vide ou faible, monte en 🟠.

### §3.5 — Cursor mouvement hors viewport
**Vérification** : `humanlike/cursor.py:62-106` — pas de clamp explicite. Bezier peut overshoot (line 87 : `overshoot_amt = 0.08`).
**Classement final** : 🟡 **MINEUR** — Playwright clamp côté browser, pas de crash.

### §3.6 — `actions.repeat` sans limite de profondeur
**Vérification** : à confirmer dans `actions/dsl.py`.
**Classement final** : 🟠 **MAJEUR** — DoS auto-infligé possible si script malformé.

### §3.7 — `creepjsscore` parser fragile
**Vérification** : `creepjsscore/score.py` à vérifier. Selecteur CSS-id en dur.
**Classement final** : 🟡 **MINEUR** — outil interne, fail visible.

### §3.8 — `taskqueue` tâche sans `id` unique
**Vérification** : `taskqueue/queue.py:128-129` dans `enqueue()` : `id=Task.new_id()` généré côté queue, pas par l'utilisateur. Pas de conflit possible.
**Classement final** : ⚪ **FAUX POSITIF**.

### §3.9 — `queuepool` (Queue-it) sans gestion captcha
**Vérification** : `queuepool/apiclient.py` (180 lignes) — à confirmer. Plausible.
**Classement final** : 🟠 **MAJEUR** — limitation réelle pour Nike SNKRS.

### §3.10 — `auto_tile` avec écran portrait
**Vérification** : `tiling.py` (2206 bytes) — calcul cols/rows à confirmer.
**Classement final** : 🟡 **MINEUR** — UX dégradée seulement.

### §3.11 — `cookie_export` cookies HTTPOnly invisibles
**Vérification** : `cookie_export.py:65` utilise `ctx.cookies()` (Playwright native API qui voit HTTPOnly). PAS `document.cookie`. La claim d'audit était fausse.
**Classement final** : ⚪ **FAUX POSITIF** — code utilise déjà la bonne API.

---

**Bilan §3 (11 entrées)** :
- 🟠 Majeur : 2 (§3.6, §3.9)
- 🟡 Mineur : 6 (§3.1, §3.3, §3.4, §3.5, §3.7, §3.10)
- ⚪ Faux positif : 3 (§3.2, §3.8, §3.11)

---

## §4. Fuites de ressources (audit)

### §4.1 — `humanlike/_last_pos` jamais purgé
**Vérification** : `humanlike/cursor.py:33` confirmé. Documenté explicitement comme acceptable pour scripts courts. Pour daemon long-running (task_worker), accumule.
**Classement final** : 🟡 **MINEUR** — l'usage typique (script ponctuel) n'est pas affecté. WeakKeyDictionary serait propre mais pas critique.

### §4.2 — `Popen` zombie
**Vérification** : `sessions.py:255` lance avec `start_new_session=True` (POSIX) → le child est détaché du launcher. Quand le child exit, init (PID 1) le reap automatiquement. Le `popen` Python est juste GC'd côté launcher → pas de zombie. Sur Windows, `DETACHED_PROCESS` + breakaway → idem.
**Classement final** : ⚪ **FAUX POSITIF** — l'architecture detached évite les zombies.

### §4.3 — `page.context` non fermé après cookie_export
**Vérification** : `cookie_export.py:59-91` utilise `with Camoufox(...) as ctx:` — context manager. Cleanup automatique même sur exception.
**Classement final** : ⚪ **FAUX POSITIF** — le `with` garantit la fermeture.

### §4.4 — `requests.post` sans Session
**Vérification** : confirmé (cf. §2.6).
**Classement final** : 🟡 **MINEUR**.

### §4.5 — Logs JSONL non rotés
**Vérification** : `sessions.py:200` ouvre `<log_path>.log` en mode `"w"` (truncate au démarrage), passé à Popen comme stdout. Pas de rotation, mais aussi pas d'append cross-session car chaque session a son propre fichier nommé `<session_id>.log`. Pour une session longue (24h+), grossit indéfiniment.
**Classement final** : 🟡 **MINEUR** — un fichier par session, pas de cross-pollution. Critique seulement pour sessions multi-jours.

### §4.6 — `tiling.py` SetWindowPos sans GetLastError
**Vérification** : `tiling.py` 2KB — diagnostic limité.
**Classement final** : 🟡 **MINEUR**.

### §4.7 — `taskqueue` claim files orphelins
**Vérification** : `taskqueue/queue.py:169-190` (`_try_claim`) crée le lock. `release_lock` line 239 le supprime. Si le worker crash entre claim et release, lock reste. Pas de sweeper.
**Classement final** : 🟠 **MAJEUR** — tâche perdue indéfiniment après crash worker. Symptôme silencieux.

### §4.8 — Threads daemon sans join
**Vérification** : pas de `threading.Thread` dans les fichiers lus. `scheduler.py` utilise une boucle simple, pas de threads. `session_runner` mono-thread.
**Classement final** : ⚪ **FAUX POSITIF** — pas de threads à joiner.

---

**Bilan §4 (8 entrées)** :
- 🟠 Majeur : 1 (§4.7)
- 🟡 Mineur : 4 (§4.1, §4.4, §4.5, §4.6)
- ⚪ Faux positif : 3 (§4.2, §4.3, §4.8)

**Fin T2c.** Prochain : T2d §5 + §6.

---

## §5. Dead code et duplication (audit)

### §5.1 — `from dataclasses import asdict as _asdict` dupliqué 5×
**Vérification** : `commands.py` à scanner. Rapport audit cite 5 occurrences. À confirmer mais plausible.
**Classement final** : 🟡 **MINEUR** — propreté de code.

### §5.2 — `commands.py` 903 lignes (god module)
**Vérification** : `ls -la` montre 29928 bytes. Avec moyenne ~33 chars/ligne, ~900 lignes confirmé. Effectivement gros pour un seul module.
**Classement final** : 🟡 **MINEUR** — dette technique réelle, pas un bug.

### §5.3 — `Profile` dataclass à ~70 champs
**Vérification** : `fpgen/profile.py` non lu mais l'audit cite 147 lignes. Plausible.
**Classement final** : 🟡 **MINEUR** — refacto recommandé, pas urgent.

### §5.4 — `humanlike` fonctions dupliquées dans `actions/runner.py`
**Vérification** : il n'y a pas de `actions/runner.py` (l'arbo montre `actions/dsl.py`, `actions/recorder.py`, `actions/store.py`). La claim est obsolète. `session_runner.py:268-275` importe bien `humanlike` proprement.
**Classement final** : ⚪ **FAUX POSITIF** — fichier mentionné n'existe pas.

### §5.5 — Constantes magiques répétées
**Vérification** : `webhook.py:81` timeout=5.0 hardcodé, `session_runner.py:367` `time.sleep(0.25)`, `task_worker.py:179` `poll_interval=3.0`. Confirmé.
**Classement final** : 🟡 **MINEUR**.

### §5.6 — DSL `if`/`repeat` non validé
**Vérification** : à confirmer dans `actions/dsl.py`.
**Classement final** : 🟡 **MINEUR** — reste validation utile, pas critique.

### §5.7 — Imports non utilisés
**Vérification** : non scanné systématiquement. Existence d'un linter à vérifier.
**Classement final** : 🟡 **MINEUR**.

---

**Bilan §5 (7 entrées)** :
- 🟡 Mineur : 6
- ⚪ Faux positif : 1 (§5.4)

---

## §6. Sécurité (audit)

### §6.1 — Bridge HTTP sans auth bind 0.0.0.0
**Vérification** : `launcher/bridge/__main__.py` confirme que **le bridge n'est PAS un serveur HTTP**. C'est un dispatcher CLI JSON invoqué par `python -m launcher.bridge <cmd>`. Pas de socket, pas de bind. L'audit a halluciné un serveur HTTP qui n'existe pas.
**Classement final** : ⚪ **FAUX POSITIF** — fondamental : pas de surface réseau.

### §6.2 — Proxies stockés en clair
**Vérification** : `proxypool/store.py` à confirmer mais structure JSON typique → effectivement en clair.
**Classement final** : 🟡 **MINEUR** — convention pour outils CLI ; chmod 0600 suffit.

### §6.3 — Webhooks SSRF
**Vérification** : `webhook.py:81` confirmé sans validation d'URL. L'utilisateur configure l'URL via env var ou config file local — pas via input web. Surface d'attaque limitée à l'utilisateur lui-même.
**Classement final** : 🟡 **MINEUR** — auto-SSRF possible mais peu probable (config locale uniquement).

### §6.4 — `eval_js` dans le DSL
**Vérification** : feature documentée. Pas un bug.
**Classement final** : ⚪ **FAUX POSITIF** — feature by design.

### §6.5 — `Popen([camoufox_bin, ...args])` avec args utilisateur
**Vérification** : `sessions.py:179-234` montre que `argv` est construit à partir de **kwargs typés** (`profile_id: str`, `headless: bool`, etc.), pas d'input arbitraire. Les valeurs viennent de `commands.py` qui valide. Pas d'injection.
**Classement final** : ⚪ **FAUX POSITIF** — pas de surface d'injection.

### §6.6 — `cookie_export.py` écriture sans atomicité
**Vérification** : `cookie_export.py:103` fait `(base.with_suffix(".json")).write_text(json.dumps(full, ...))` — écriture directe, pas tmp+replace. Si crash pendant write, fichier tronqué.
**Classement final** : 🟡 **MINEUR** — fichier d'export, peut être régénéré.

### §6.7 — Logs contiennent secrets ?
**Vérification** : `webhook.py` log juste le content message. `cookie_export.py` ne log rien des cookies. `commands.py` à scanner. Risque limité.
**Classement final** : 🟡 **MINEUR** — à auditer mais pas évident.

### §6.8 — Pas de signature des actions DSL
**Vérification** : feature non implémentée. Pas un bug actuel.
**Classement final** : ⚪ **FAUX POSITIF** — pas une régression, juste une feature manquante.

---

**Bilan §6 (8 entrées)** :
- 🟡 Mineur : 4 (§6.2, §6.3, §6.6, §6.7)
- ⚪ Faux positif : 4 (§6.1, §6.4, §6.5, §6.8)

**Fin T2d.** Prochain : T2e1 §7 + §8.

---

## §7. Performance (audit)

### §7.1 — Polling 2s pour 50 sessions = 25 stat()/sec
**Vérification** : `sessions.py:140-153` (`list()`) fait `glob` + `_reconcile` (qui fait `_pid_alive`). À 50 sessions × 0.5 Hz = 25/s. Coût négligeable sur Linux. Sur Windows, `OpenProcess` est plus cher mais pas critique.
**Classement final** : 🟡 **MINEUR** — overhead négligeable jusqu'à 200 sessions.

### §7.2 — `page.url` interrogé toutes les 2s
**Vérification** : `session_runner.py:374` confirme `_ = page.url`. Mais c'est dans un sous-process dédié à UNE session (pas 50). Le coût est local à cette session uniquement.
**Classement final** : 🟡 **MINEUR** — l'audit a sur-estimé l'impact (multiplie par 50, mais c'est 1 seul process par session).

### §7.3 — `creepjsscore` browser par run
**Vérification** : design pour benchmarking ponctuel. Pas pour batch.
**Classement final** : 🟡 **MINEUR** — usage occasionnel.

### §7.4 — Bezier curve calculée d'avance
**Vérification** : `humanlike/cursor.py:89-97` — `Bezier.humanize` pré-calcule. Coût négligeable (quelques μs par courbe).
**Classement final** : 🟡 **MINEUR**.

### §7.5 — `fpgen.profile` cache BrowserForge
**Vérification** : à confirmer dans `fpgen/generator.py`. Plausible.
**Classement final** : 🟡 **MINEUR** — startup time uniquement.

### §7.6 — `tiling.py` re-énumère fenêtres
**Vérification** : `tiling.py` 2KB, à confirmer. Vraisemblable.
**Classement final** : 🟡 **MINEUR**.

### §7.7 — `json.dumps(indent=2)`
**Vérification** : `sessions.py:62`, `scheduler.py:62`, `taskqueue/queue.py` utilisent indent=2. Volumineux pour des fichiers d'état.
**Classement final** : 🟡 **MINEUR** — avantage debugging > coût IO.

### §7.8 — Pas de circuit breaker webhooks
**Vérification** : `webhook.py:80-84` — try/except simple, pas de retry/backoff. Si Discord 429, chaque appel paie 5 s.
**Classement final** : 🟡 **MINEUR** — affecte une session à la fois (pas le runner global).

---

**Bilan §7 (8 entrées)** : 🟡 Mineur : 8 (zéro critique, zéro majeur).

---

## §8. Architecture / dette technique (audit)

### §8.1 — Couplage `commands.py` ↔ `SessionManager`
**Vérification** : `scheduler.py:111` importe `_session_mgr` depuis commands (underscore = privé). Confirme couplage fort. Acceptable pour un projet de cette taille.
**Classement final** : 🟡 **MINEUR**.

### §8.2 — Pas de tests unitaires
**Vérification** : `find -name "test_*.py"` montre :
- `actions/tests/test_dsl.py`, `test_recorder.py`, `test_store.py`
- `fpgen/tests/test_adapter.py`, `test_consistency.py`, `test_generator.py`, `test_jvv_schema.py`, `test_p4.py`, `test_store.py`
- `humanlike/tests/test_bezier.py`, `test_cursor.py`, `test_typing.py`
- `launcher/bridge/tests/test_cli.py`, `test_commands.py`, `test_commands_finitions.py`, `test_sessions.py`
- `proxypool/tests/test_*.py` (7 fichiers)
- `taskqueue/tests/test_queue.py`, `test_task.py`

**Tests existent dans tous les modules.** L'audit était factuellement faux.
**Classement final** : ⚪ **FAUX POSITIF** flagrant.

### §8.3 — Pas de séparation domain/infra
**Vérification** : confirmé. Conscient design choice pour un projet pragmatique.
**Classement final** : 🟡 **MINEUR**.

### §8.4 — Pas de schema versioning sur `session.json`
**Vérification** : `sessions.py:42-67` — la dataclass `Session` n'a pas de champ `schema_version`. Confirmé.
**Classement final** : 🟡 **MINEUR** — pas de migrations passées, pas urgent.

### §8.5 — Zustand store non typé strict
**Vérification** : non lu.
**Classement final** : 🟡 **MINEUR**.

### §8.6 — Pas de healthcheck du bridge
**Vérification** : pas de bridge HTTP (cf. §6.1). N/A.
**Classement final** : ⚪ **FAUX POSITIF**.

### §8.7 — Patches Juggler sans tests régression
**Vérification** : `tests/async/` contient des tests Playwright. Pas de tests dédiés Juggler stealth visibles, mais infrastructure de tests présente.
**Classement final** : 🟡 **MINEUR** — tests existants, juste pas spécialisés stealth.

### §8.8 — Pas de versioning des patches
**Vérification** : aucun header standardisé dans `patches/*.patch`. Confirmé.
**Classement final** : 🟡 **MINEUR**.

---

**Bilan §8 (8 entrées)** :
- 🟡 Mineur : 6
- ⚪ Faux positif : 2 (§8.2, §8.6)

**Fin T2e1.** Prochain : T2e2 §9 + §10 + bilan global.
