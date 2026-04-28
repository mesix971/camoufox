# FARMING_ARCHITECTURE.md — Système de farm de profils

> Document d'architecture pour le système de farming de profils Camoufox.
> Statut : **draft** — à valider avant implémentation.

## §1. Objectifs & non-objectifs

### Objectifs
- Faire vieillir des profils Camoufox de manière indétectable pour qu'ils paraissent appartenir à un humain réel utilisant Firefox depuis plusieurs jours/semaines.
- Augmenter le taux de succès sur **WAF avancés** (Cloudflare Bot Management, Akamai BMP, DataDome, PerimeterX, Incapsula) qui scorent négativement les profils "fresh".
- Permettre à un profil "mature" de passer un checkout SNKRS / Supreme / Shopify Plus sans déclencher de challenge.
- Industrialiser le processus : 50–500 profils en parallèle sans intervention humaine.

### Non-objectifs (volontairement exclus)
- Pas de **résolution de captcha pendant le farm** (les sites de farm sont choisis pour ne pas en présenter).
- Pas de **création de comptes** sur les sites visités (signup = footprint identifiable, contre-productif).
- Pas de **purchase history** (interactions e-com limitées au browse, pas de cart/checkout).
- Pas de **multi-account farming** sur un même site (un profil ne devient pas "client" d'un site, juste "visiteur récurrent").

---

## §2. Signaux de détection que le farming doit satisfaire

> Ce qu'un détecteur regarde pour distinguer un profil "réel ancien" d'un profil "fresh+spoofé".

### 2.1 Signaux côté navigateur (lus par JS sur la page)
| Signal | Profil fresh | Profil farmé attendu |
|--------|-------------|---------------------|
| `document.cookie` count par origin | 0–2 | 5–30 (variable selon site) |
| Cookies avec `Max-Age > 30 jours` (persistants) | 0 | présents (Google `NID`, Cloudflare `__cf_bm`, etc.) |
| `localStorage` keys count par origin | 0 | 3–20 (chaque site stocke des prefs) |
| `localStorage` size cumulé | 0 KB | 10–500 KB |
| `IndexedDB` databases | 0 | 1–5 (YouTube, Discord, GitHub en créent) |
| `navigator.serviceWorker.getRegistrations()` count | 0 | 1–5 (PWA installées invisiblement) |
| `caches.keys()` (Cache API) | 0 | présents si SW actifs |
| Date de création la plus ancienne d'un cookie | maintenant | jours/semaines |

### 2.2 Signaux côté réseau (vus par le site cible et les WAF)
| Signal | Profil fresh | Profil farmé attendu |
|--------|-------------|---------------------|
| Premier `Set-Cookie` reçu (date | maintenant | maintenant **mais** le profil envoie déjà des cookies anciens d'autres origines |
| `Referer` chain réaliste | absent | depuis Google/social/news selon contexte |
| ORD (`Origin Resource Distribution`) — diversité des origines déjà visitées (vu via TLS fingerprint persistant + fetch metadata) | mono-origin | multi-origin |
| ETags / `If-None-Match` envoyés au revisit | absents (nouveau) | présents (ressources déjà cachées) |
| `Sec-Fetch-Site: same-origin` après navigation interne | rarement | normal |

### 2.3 Signaux comportementaux (collectés par les Bot Management JS)
| Signal | Profil fresh | Profil farmé attendu |
|--------|-------------|---------------------|
| Mouvements de souris non-linéaires | absent | présents |
| Scroll patterns (vitesse, pauses) | constant ou absent | variable, naturel |
| Touche `Tab` utilisée pour navigation form | jamais | parfois |
| Temps de lecture vs taille du contenu | aléatoire | corrélé à la complexité |
| Focus blur events (changement d'onglet) | absent | présents (humains multitâchent) |
| `requestIdleCallback` exécuté pendant idle réel | absent | normal |

### 2.4 Signaux temporels
- **Première visite vs maintenant** : un profil devrait avoir une dispersion sur plusieurs jours, pas un burst de 50 visites en 2h.
- **Distribution heure/jour** : les visites se concentrent en heures éveillées du fuseau horaire claimé par le profil (cohérence avec `timezone` + `navigator.languages`).
- **Pauses** : weekend différent de la semaine, moins d'activité tôt le matin / tard le soir.

---

## §3. Cycle de vie d'un profil

```
                    ┌──────────────────┐
   [créé fpgen] ──► │      FRESH       │ — jamais farmé
                    └──────────────────┘
                             │
                       (1ère farm session)
                             │
                             ▼
                    ┌──────────────────┐
                    │     WARMING      │ — < 3 jours, < 10 sessions
                    └──────────────────┘
                             │
                      (maturity ≥ seuil)
                             │
                             ▼
                    ┌──────────────────┐
                    │      MATURE      │ — éligible aux drops
                    └──────────────────┘
                       │            │
              (drop)   │            │ (continue farm)
                       ▼            ▼
                 ┌────────┐   ┌──────────┐
                 │ ACTIVE │   │ MATURE   │ (loop)
                 └────────┘   └──────────┘
                       │
                  (success/fail)
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
       ┌────────┐           ┌─────────┐
       │ COOLED │           │ BURNED  │
       └────────┘           └─────────┘
       (1-7 jours        (captcha hard,
        repos avant       challenge échoué,
        re-mature)        IP flagged ⇒
                          retire profil)
```

### 3.1 Statuts (à ajouter au dataclass `Profile`)
- `FRESH` : créé, jamais farmé. Maturity = 0.
- `WARMING` : farm en cours, pas encore éligible au drop. Maturity 0–60.
- `MATURE` : prêt à l'usage. Maturity ≥ 60.
- `ACTIVE` : actuellement utilisé pour un drop (lock exclusif via §1.1 du fix lock-per-profile).
- `COOLED` : revient de drop, en cooldown 1–7 jours (le proxy/IP a été "vu" sur le site cible).
- `BURNED` : profil flaggé (challenge échoué multiple, IP banned). Retiré du pool actif, supprimé après 30 jours.

### 3.2 Transitions automatiques
- `FRESH → WARMING` : à la première session farm enqueuée.
- `WARMING → MATURE` : quand `maturity_score >= MATURITY_THRESHOLD` (configurable, défaut 60).
- `MATURE → ACTIVE` : lors d'un launch-session avec `--use-mature-profile`.
- `ACTIVE → MATURE` : succès du drop (back to pool).
- `ACTIVE → COOLED` : échec soft (retry plus tard).
- `ACTIVE → BURNED` : échec hard (captcha échoué 3×, banned).
- `COOLED → MATURE` : après cooldown_until passé.

---

## §4. Maturity score

> Note unique 0–100 calculée à partir de signaux mesurables sur le profil. Permet de comparer les profils et de décider lesquels utiliser.

### 4.1 Composantes (somme pondérée, plafonnée à 100)

| Composante | Poids | Calcul | Plafond |
|-----------|-------|--------|---------|
| **Âge** | 25 | `min(25, days_since_first_farm)` | 25 (à 25 j) |
| **Diversité d'origines** | 20 | `min(20, unique_origins_visited * 0.4)` | 20 (50 origines) |
| **Profondeur cookies** | 15 | `min(15, total_cookie_count * 0.1)` | 15 (150 cookies) |
| **Cookies persistants** | 10 | `min(10, persistent_cookies * 0.5)` | 10 (20 cookies long-lived) |
| **Diversité catégories** | 10 | `len(set(categories_visited))` × 1.5 | 10 (7 catégories) |
| **Sessions count** | 10 | `min(10, session_count * 0.2)` | 10 (50 sessions) |
| **Dispersion temporelle** | 5 | `min(5, distinct_hours_visited * 0.25)` | 5 (24h variées) |
| **Aucun captcha rencontré** | 5 | 5 si zéro captcha sur 30 derniers jours, sinon 0 | 5 |

**Total max = 100.** Seuil MATURE par défaut = 60.

### 4.2 Pénalités (soustraites du score)
- `-30` si captcha hard rencontré (Cloudflare interstitial passé) dans les 24h
- `-50` si banned IP détecté (403 sustainedly sur sites cibles)
- `-10` par jour d'inactivité au-delà de 7 jours (un profil dormant perd de la valeur — il a l'air "récemment réveillé")

### 4.3 Décroissance (decay) sans farm
- Un profil mature non farmé perd `~2 points/jour` après 7 jours d'inactivité.
- À `maturity < 30` après decay, retour automatique à `WARMING`.

### 4.4 Champs à ajouter au dataclass `Profile`
```python
status: ProfileStatus = ProfileStatus.FRESH
first_farmed_at: Optional[str] = None
last_farmed_at: Optional[str] = None
farm_session_count: int = 0
unique_origins_visited: List[str] = field(default_factory=list)
categories_visited: List[str] = field(default_factory=list)
hours_visited_utc: List[int] = field(default_factory=list)  # hours-of-day [0..23]
captcha_encounters: List[Dict] = field(default_factory=list)  # last 30 days
last_drop_at: Optional[str] = None
cooldown_until: Optional[str] = None
burned_reason: Optional[str] = None
```

`maturity_score` est calculé à la volée à partir de ces champs (pas stocké, sinon il devient stale).

---

## §5. Scheduler des sessions de farm

> Quand et à quelle fréquence lancer une session farm pour un profil donné.

### 5.1 Modèle de fréquence
- **Cible** : 2–5 sessions/jour par profil en `WARMING`, 1–2/jour en `MATURE`.
- **Durée par session** : tirée d'une distribution log-normale, médiane 25 min, σ ≈ 0.5 (range pratique 5–90 min).
- **Espacement** : minimum 90 min entre 2 sessions du même profil (sinon pattern de bot évident).

### 5.2 Distribution heure-de-jour (cohérente avec timezone du profil)
Au lieu d'une loi uniforme, on suit une courbe d'activité humaine plausible **dans le fuseau du profil** :

```
Probabilité de spawn par heure locale (timezone profil) :
  00-06  ▏           très faible (5%)
  06-09  ▍▍          réveil (20%)
  09-12  ▍▍▍▍        bureau matin (40%)
  12-14  ▍▍▍         pause déj (30%)
  14-18  ▍▍▍▍▍       bureau aprem (50%)
  18-22  ▍▍▍▍▍▍▍     soirée (70%)
  22-24  ▍▍▍         tard (30%)
```

Variation **weekend** : poids déplacés vers 10h-14h et 20h-23h.

### 5.3 Job dans le scheduler existant
Étendre `launcher/bridge/scheduler.py` avec un nouveau job :

```python
JOBS = [
    ...,
    ("farm_dispatcher", 300, dispatch_farm_sessions),  # toutes les 5 min
]
```

Le dispatcher :
1. Liste les profils `WARMING` ou `MATURE` éligibles (pas en `ACTIVE`, pas en `COOLED`).
2. Pour chaque profil, calcule sa "due-ness" : `now - last_farmed_at >= jitter(target_interval, ±30%)`.
3. Échantillonne selon la courbe heure-de-jour : roll un dice contre la proba locale.
4. Si éligible, enqueue une tâche `farm-session` dans le taskqueue.
5. Plafond global : pas plus de N sessions farm concurrentes (défaut N=10, configurable).

### 5.4 Cooldown global après captcha
Si un profil rencontre un captcha pendant une farm session, **tous les profils sur le même proxy** entrent en cooldown 1h (même IP probablement flaggée).

---

## §6. Site catalog

> Quels sites visiter et selon quelle stratégie de rotation.

### 6.1 Catégorisation
8 catégories pondérées pour ressembler à un usage humain réel :

| Catégorie | Poids | Exemples |
|----------|-------|----------|
| `search` | 20 | google.com, bing.com, duckduckgo.com |
| `news` | 15 | bbc.com, cnn.com, lemonde.fr (par locale) |
| `video` | 15 | youtube.com, dailymotion.com, twitch.tv |
| `social` | 10 | reddit.com, x.com (lecture seulement, pas login) |
| `ecom_browse` | 15 | amazon.com, ebay.com, etsy.com (browse, pas cart) |
| `wiki_ref` | 10 | wikipedia.org, stackoverflow.com, mdn |
| `weather_utility` | 5 | weather.com, accuweather.com |
| `dev_tech` | 10 | github.com, hackernews.com (pour profils dev-archetype) |

Chaque profil a un **biais** (`profile.archetype` déjà existant via `fpgen`) qui module les poids :
- Archetype `gamer` : +30% video, +20% social, -50% news.
- Archetype `business` : +50% news, +30% ecom_browse, -50% video.
- Archetype `casual` : poids par défaut.

### 6.2 Sélection par session
Une farm session visite **3–8 sites** (tirage uniforme), répartis en :
- 1 site "entry" (search engine, le plus fréquent).
- 2–6 sites "browse" (selon catégories pondérées).
- 1 site "exit" optionnel (retour à un site déjà connu du profil = pattern de fin de session).

### 6.3 Réutilisation vs nouveauté
- **70% des sites** : déjà visités par ce profil (revisit = signal de récurrence, accumule cookies).
- **30% des sites** : nouveau pour ce profil (étend `unique_origins_visited`).

### 6.4 Anti-pattern : ne PAS visiter les sites cibles pendant le farm
Si le profil sera utilisé pour Nike SNKRS, **ne jamais visiter nike.com pendant le farm**. Le site cible doit voir le profil pour la première fois lors du drop (cohérent avec un humain qui découvre le drop).

### 6.5 Storage du catalog
`launcher/data/farm_catalog.json` :
```json
{
  "version": 1,
  "categories": {
    "search": {
      "weight": 20,
      "sites": [
        {"url": "https://www.google.com/search?q={query}", "params": {"query": ["news today", "weather", ...]}},
        ...
      ]
    },
    ...
  },
  "do_not_visit": ["nike.com", "snkrs.com", "supremenewyork.com", ...]
}
```

Catalog éditable par l'utilisateur via UI.

---

## §7. Simulation de comportement in-page

> Ce qui se passe une fois que le browser est sur un site pendant une farm session.

### 7.1 Pattern par type de site

#### `search`
1. Naviguer vers la page de recherche.
2. `humanlike.fill` du champ search (vitesse de frappe variable 100–300ms/char).
3. Submit.
4. Lire les résultats (scroll lent, pause 2–8s).
5. Click sur le 1er–3e résultat avec proba pondérée (1er = 60%, 2e = 25%, 3e = 15%).
6. Sortir vers le site cliqué (devient le site suivant de la session).

#### `news`
1. Land sur homepage.
2. Scroll progressif (5–15 scrolls de 200–600px, pauses 1–4s).
3. Click sur 1–3 articles, lire chacun (dwell ~ `len(text) / 250 mots/min`).
4. Retour homepage entre articles 50% du temps.

#### `video` (YouTube)
1. Land sur homepage ou search.
2. Scroll feed.
3. Click sur 1–2 vidéos.
4. Pause **lecture vidéo** : laisse jouer 30s–4 min (la page accumule du cookie viewer).
5. Like/comment **jamais** (signup requis, footprint).

#### `social` (Reddit, X read-only)
1. Land sur subreddit/feed.
2. Scroll lent.
3. Click sur 2–4 threads.
4. Lire (dwell), retour back.

#### `ecom_browse`
1. Land sur homepage.
2. Search produit aléatoire (tiré d'une liste générique : "shoes", "laptop", "headphones").
3. Click 2–3 produits.
4. **Jamais** : add-to-cart, wishlist, account creation.

### 7.2 Comportements transverses (toutes catégories)
- `humanlike.cursor.move` entre les clicks (curve Bezier déjà implémentée).
- Mouvements de souris **idle** : 1–3 micro-mouvements pendant les pauses (jitter 5–20px).
- Scroll avec `humanlike.scroll` (vitesse variable, pauses).
- **Tab/Esc/Ctrl+F** rare (~5% des sessions) — humanise.
- Focus blur simulé : `page.evaluate("window.dispatchEvent(new Event('blur'))")` 2–4 fois par session.

### 7.3 DSL de farm
Réutiliser le DSL `actions` existant. Une farm session = un script DSL généré dynamiquement à partir du pattern par type de site. Avantage : tout passe par `run_script` qui gère déjà MAX_ACTIONS (cf. fix #3.6).

```python
def build_farm_script(profile: Profile, site: Site) -> ActionScript:
    template = SITE_PATTERNS[site.category]
    return template.render(profile=profile, site=site, rng=Random(profile.id))
```

---

## §8. Proxy binding

> La règle d'or : un profil farmé doit toujours sortir par la même IP (ou au moins le même /24 résidentiel), sinon les WAF voient un humain qui change de FAI tous les jours = bot.

### 8.1 Sticky session par profil
- Au moment du `farm_dispatcher`, on récupère le proxy assigné au profil via `profile.assigned_proxy_id`.
- Si pas assigné, on en assigne un selon :
  - Géo cohérente avec `profile.timezone` + `profile.locale`.
  - Type **résidentiel** (datacenter exclu pour le farm — trop facile à fingerprinter).
  - Sticky session activée chez le provider (iproyal `_session-{profile.id[:8]}`).
- L'assignation est **persistante** : `profile.assigned_proxy_id` survit au restart.

### 8.2 Rotation d'IP au sein d'un proxy sticky
- Provider iproyal : sticky session jusqu'à 30 min, puis nouvelle IP **dans le même /24**.
- Acceptable car un humain change parfois d'IP (FAI réassigne).
- **Pas acceptable** : changement de pays ou /16 → ce serait suspect.

### 8.3 Failover si proxy mort
- Si proxy assigné est `dead` (via `proxypool.health`), le farm session est :
  1. **Reportée** de 30 min (peut-être que c'est temporaire).
  2. Si toujours dead après 3 reports → **réassignation** vers un proxy similaire (même provider, même géo) **avec marquage `proxy_changed_at`**.
  3. Si pas de proxy similaire → profil entre en pause (`status=COOLED`, durée 24h).

### 8.4 Anti-leak
- WebRTC ICE : déjà fixé par le patch `webrtc-ice-candidate-order.patch` + `webrtc-ip-spoofing.patch` du fork.
- DNS leak : Camoufox force le DNS via le proxy (vérifier dans `MaskConfig`).
- IPv6 : désactiver (proxies IPv4 only) — pref `network.dns.disableIPv6 = true`.

### 8.5 Coût
Estimation pour 100 profils farmés à 3 sessions/jour × 25 min médiane :
- 100 × 3 × 25 / 60 = **125 h-proxy/jour**
- Bande passante moyenne ~50 MB/session (pages + vidéo YT) × 300 sessions = **15 GB/jour**
- Coût iproyal résidentiel : ~$5/GB → **~75 $/jour pour 100 profils en farm continu**

⇒ Le farm est **cher** ; il faut prioriser quels profils farmer (cf. §11 priorisation).

---

## §9. Failure modes & recovery

> Tout ce qui peut mal tourner pendant un farm, et comment le système réagit.

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| Captcha hard rencontré (Cloudflare interstitial) | IP suspectée | Marquer `captcha_encounters`, abort session, **cooldown 6h sur le proxy entier** |
| 403 sustainedly sur un site | IP banned ou profil flagged | `BURNED` si récurrent, sinon `COOLED` 24h |
| Profil crash mid-farm | Process died | Relancer 1× (retry policy taskqueue), 2e échec → marquer session FAILED, decrement maturity |
| Proxy mort pendant session | Provider down ou IP rotated trop tôt | Retry 30 min, sinon réassignation |
| Site cible (do-not-visit) accidentellement chargé | Lien dans une page browse | Abort immédiat, `last_browse_url` purgé du history |
| `MAX_ACTIONS_PER_RUN` atteint | Bug dans pattern, redirect loop | Log warning, profil OK, juste session tronquée |
| Disk full (user_data_dir) | Cache YouTube monstrueux accumulé | Quota 500 MB/profil, purge cache si dépassé |
| Profil flag par browser detection (`__cf_bm` invalide) | Trop de bot signals envoyés | `BURNED` |

### 9.1 Détecteurs internes
- **Captcha detector** (réutilise le code `_detect_and_solve_captcha` du `session_runner.py:58`) : présence d'iframe Turnstile/reCAPTCHA/hCaptcha = signal d'échec.
- **403/blocked detector** : compteur de réponses HTTP ≥ 400 sur les sites visités. Si > 3 sur la session → fail.
- **Profile bloat detector** : `du -sh user_data_dir` > 500 MB → trigger cleanup (purge cache HTTP, garde cookies + localStorage).

### 9.2 Métriques exportées
À chaque farm session, push dans le store :
```json
{
  "profile_id": "...",
  "session_id": "...",
  "started_at": "...",
  "duration_seconds": 1245,
  "sites_visited": ["google.com", "youtube.com", ...],
  "categories_touched": ["search", "video"],
  "captcha_encountered": false,
  "errors": [],
  "maturity_before": 42,
  "maturity_after": 47
}
```

Logs accessibles via UI pour debugger un profil qui régresse.

---

## §10. Intégration avec les modules existants

> Comment le farming se branche sur le toolkit actuel sans tout casser.

### 10.1 Modules réutilisés tels quels
- **`fpgen`** : pas de changement à la génération du profil. Juste ajout des champs §4.4 au dataclass `Profile`.
- **`proxypool`** : ajouter `assigned_to_profile: Optional[str]` au dataclass `Proxy` pour visibilité.
- **`taskqueue`** : nouvelle action type `farm-session` (cf. §10.4).
- **`humanlike`** : utilisé tel quel pour mouse/keyboard.
- **`actions`** (DSL) : utilisé tel quel pour exprimer les patterns farm.
- **`launcher.bridge.sessions`** : utilisé tel quel — le farm session est un subprocess Camoufox standard.
- **`launcher.bridge.scheduler`** : nouveau job `farm_dispatcher` ajouté à `JOBS`.

### 10.2 Nouveau module : `farming/`
```
farming/
├── __init__.py
├── catalog.py        # site catalog loader
├── patterns.py       # patterns par catégorie (search, news, video, ...)
├── builder.py        # build_farm_script(profile, site) -> ActionScript
├── scheduler.py      # eligibility logic, hour-of-day curve
├── maturity.py       # maturity_score(profile) -> int
├── lifecycle.py      # status transitions (FRESH ↔ WARMING ↔ MATURE ↔ ...)
├── data/
│   └── farm_catalog.json
└── tests/
    ├── test_maturity.py
    ├── test_scheduler.py
    ├── test_patterns.py
    └── test_lifecycle.py
```

### 10.3 Nouvelles commandes du bridge (`launcher.bridge.commands`)
- `farm_start <profile_id>` : enqueue immédiatement une farm session.
- `farm_stop <profile_id>` : annule les farm sessions en cours pour ce profil.
- `farm_status` : tableau de tous les profils avec status + maturity_score + last_farmed.
- `farm_catalog_list` : retourne le contenu du catalog.
- `farm_catalog_set <category> <url>` : ajoute un site au catalog.
- `farm_burn <profile_id> <reason>` : marque manuellement comme `BURNED`.
- `farm_unburn <profile_id>` : retire le statut `BURNED` (manuel, après vérif).
- `farm_set_archetype <profile_id> <archetype>` : modifie le biais des poids catégories.
- `farm_metrics` : statistiques globales (sessions/jour, taux captcha, coût proxy estimé).

### 10.4 Nouveau type d'action taskqueue : `farm-session`
```json
{
  "type": "farm-session",
  "profile_id": "abc123",
  "duration_minutes": 25,
  "site_count": 5,
  "rng_seed": 12345
}
```

Handler dans `task_worker.py` :
```python
def _dispatch_farm(action: Dict) -> Dict:
    from farming.builder import build_farm_script
    from farming.lifecycle import on_farm_started, on_farm_finished
    profile_id = action["profile_id"]
    on_farm_started(profile_id)  # acquires lock, sets WARMING if FRESH
    script = build_farm_script(profile_id, ...)
    # Spawn session with the script auto-loaded
    s = mgr.spawn(profile_id=profile_id, run_macro=script.serialize_inline(),
                  persistent=True, headless=True)
    # Wait for completion
    wait_for_session_done(s.id, timeout=action["duration_minutes"]*60+120)
    on_farm_finished(profile_id, success=True)
    return {"session_id": s.id}
```

### 10.5 Tests d'intégration nécessaires
- `farm_dispatcher` ne lance pas plus de N sessions concurrentes (plafond global).
- Profil `BURNED` ne reçoit pas de farm session.
- Sticky proxy assignation persiste entre dispatcher invocations.
- `maturity_score` recalculé à chaque appel reflète les changements de `unique_origins_visited`.

---

## §11. Data model — modifications nécessaires

### 11.1 `fpgen.Profile` — ajouts
Cf. §4.4 (status, first_farmed_at, etc.).

### 11.2 `proxypool.Proxy` — ajouts
```python
assigned_to_profile: Optional[str] = None  # profile_id sticky
last_assigned_at: Optional[str] = None
```

### 11.3 Nouveau store : `farming.SessionMetrics`
Une entrée par farm session pour audit/debug.

```python
@dataclass
class FarmSessionMetric:
    session_id: str
    profile_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    sites_visited: List[str]
    categories_touched: List[str]
    captcha_encountered: bool
    errors: List[str]
    maturity_before: int
    maturity_after: int
```

Stocké dans `~/.camoufox/farming/metrics/<YYYY-MM-DD>/<session_id>.json` (rotation par jour, purge > 90 jours).

### 11.4 Schema versioning
Ajouter `schema_version: int = 2` au `Profile` pour migration auto des profils créés avant le farm system. Migration : tous les profils v1 démarrent en `FRESH` avec metrics vides.

### 11.5 Priorisation des profils à farmer
Quand le budget proxy est limité, prioriser :
1. Profils `WARMING` proches du seuil MATURE (60). Effort marginal le plus rentable.
2. Profils `MATURE` qui décroissent (decay > 5 points sous le seuil). Peu de farm pour les remonter.
3. Profils `COOLED` arrivant en fin de cooldown.
4. Profils `MATURE` haut score → farm minimal (1×/jour) juste pour entretenir.

Score de priorité : `priority = max(0, MATURE_THRESHOLD - maturity_score) + days_since_last_farm × 5`.

---

## §12. CLI / UI

### 12.1 Onglet "Farming" dans l'UI Electron
Nouveau tab principal :
- **Vue Profils** : table avec colonnes `name | status | maturity | last_farmed | proxy | actions`.
- **Filtres** : par status (FRESH/WARMING/MATURE/...), par archetype, par maturity range.
- **Actions inline** : start farm now, view metrics, burn, unburn, edit archetype.
- **Vue Globale** :
  - Graphique : nombre de sessions farm par jour (7 derniers jours).
  - Graphique : distribution des maturity scores.
  - Compteur : profils prêts pour drop (`MATURE` count).
  - Coût proxy estimé / mois.
- **Vue Catalog** : éditeur du `farm_catalog.json`, drag-and-drop pour réorganiser.
- **Vue Métriques** : drill-down par session (logs, sites visités, durée).

### 12.2 CLI
```bash
# Démarrer le scheduler farm
python -m launcher.bridge.scheduler --enable-farm

# Status global
python -m launcher.bridge farm_status

# Farmer un profil immédiatement
python -m launcher.bridge farm_start --profile-id abc123

# Voir les métriques d'un profil
python -m launcher.bridge farm_metrics --profile-id abc123 --days 7
```

### 12.3 Notifications webhook
Événements importants :
- Profil atteint `MATURE` : success notification.
- Profil `BURNED` : error notification (action user requise).
- Captcha hard rencontré : warn notification.
- Coût proxy quotidien dépassé : warn notification.

---

## §13. Open questions / risques

### 13.1 Questions à trancher avant implémentation
1. **Headless ou headful pour le farm ?** Headful = plus naturel (vraies dimensions, vraies fonts), mais explose la RAM (50 profils × 300 MB = 15 GB). Headless = plus économe mais détectable via certains heuristiques. **Recommandation** : headless avec patches anti-headless du fork (déjà en place via `force-default-pointer.patch`).

2. **Quel niveau de simulation comportementale est suffisant ?** Mouse curves + scroll + dwell suffisent ? Ou faut-il aller jusqu'aux interactions complexes (drag, swipe, gestes) ? **Recommandation** : démarrer simple (curves+scroll+dwell), itérer si CreepJS / FpJS détectent.

3. **Rotation de fingerprint pendant le farm ?** Un humain ne change pas de browser tous les jours. **Recommandation** : fingerprint figé pour la durée de vie du profil. Si le profil régresse, le burner et en créer un nouveau, pas changer le FP en place.

4. **Multi-tab pendant farm ?** Ouvrir 2-3 tabs = humain, mais Camoufox = 1 fingerprint = 1 process. **Recommandation** : pas de multi-tab pour le farm — limite par design.

5. **Faut-il farmer h24 ou respecter le sleep du timezone ?** Faux : un humain ne navigue pas à 4h du matin (ou très peu). Le scheduler §5.2 le respecte déjà. **Recommandation** : respecter strictement, c'est gratuit.

6. **Persistent_context vs export/import de cookies ?** Persistent = simple, mais profil ne peut être farmé que sur 1 host. Export/import = portabilité. **Recommandation** : persistent par défaut, export comme fonctionnalité d'urgence (déjà via `cookie_export.py`).

### 13.2 Risques majeurs
- **Coût proxy explosif** : si on farm 500 profils × 3 sessions/jour, on est à ~375$/jour. Doit être budgété ou throttlé.
- **Pattern de farm détectable** : si tous les profils visitent les mêmes 50 sites au même rythme, le pattern devient signature. Solution : grand catalog (>200 sites), poids randomisés par profil.
- **Faux sentiment de sécurité** : un profil `MATURE` n'est pas garanti de passer un drop. C'est statistique. Communiquer sur les taux moyens, pas sur l'absolu.
- **Évolution des détecteurs** : Cloudflare/Akamai ajoutent de nouveaux signals tous les mois. Le système doit être versionné et auditer ses propres taux de succès régulièrement (cf. métriques §10.5).

### 13.3 Estimation effort d'implémentation
| Composant | Effort |
|-----------|--------|
| `farming/` module (lifecycle + maturity + catalog + patterns + scheduler + builder) | 3 j |
| Modifications `fpgen.Profile` + migration v1→v2 | 0.5 j |
| Modifications `proxypool.Proxy` + sticky assignation | 0.5 j |
| Action `farm-session` dans `task_worker.py` | 1 j |
| Job `farm_dispatcher` dans `scheduler.py` | 0.5 j |
| Commandes bridge (9 nouvelles) | 1 j |
| Onglet Electron "Farming" + 4 sous-vues | 3 j |
| Catalog initial (200+ sites par catégorie) | 1 j |
| Tests unitaires + intégration | 2 j |
| Documentation utilisateur | 0.5 j |
| **Total** | **~13 j-homme** |

### 13.4 MVP en 3 jours
Si le budget est serré, version minimale :
- `farming.maturity` + `farming.lifecycle` (sans archetype bias, formule simple).
- 1 seul pattern par catégorie (pas de variantes).
- Catalog hardcodé 50 sites.
- Pas de scheduler intégré : trigger manuel via `farm_start`.
- Pas d'UI : juste `farm_status` en CLI.

Permet de valider l'approche sur 5-10 profils avant d'investir dans le scaling.

---

**Fin de l'architecture.** Prochaine étape : décision go/no-go + priorisation du backlog d'implémentation.
