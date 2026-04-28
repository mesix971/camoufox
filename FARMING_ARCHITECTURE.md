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

**Fin Turn FA2.** À suivre :
- T3 : §9 Failure modes + §10 Intégration modules + §11 Data model + §12 CLI/UI + §13 Open questions
