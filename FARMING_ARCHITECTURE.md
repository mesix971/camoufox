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

**Fin Turn FA1.** À suivre :
- T2 : §5 Scheduler + §6 Site catalog + §7 Behavior simulation + §8 Proxy binding
- T3 : §9 Failure modes + §10 Intégration modules + §11 Data model + §12 CLI/UI + §13 Open questions
