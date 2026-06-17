# PROJECT.md — Résumé vivant du projet

> Document de référence, **tenu à jour** à chaque évolution. Dernière mise à jour :
> Phase 5 (PostgreSQL/Grafana + News/Macro/Sentiment).

Bot de trading algorithmique **multi-agents, risk-first, paper-first**, avec une
**boucle d'auto-apprentissage**. Priorité absolue : préservation du capital.
Aucune promesse de performance. Live trading désactivé par défaut.

---

## 1. Vision & philosophie (le cœur, stable)

> Préserver le capital d'abord. Croître ensuite. Ne trader qu'avec un avantage
> statistique mesuré. Réduire l'exposition dès qu'il disparaît.

Trois règles **structurelles** (codées, pas seulement promises) :
1. **Risk-first** — le `RiskManager` a un veto absolu. Aucun agent, ni le CIO,
   ne peut l'outrepasser.
2. **Paper-first** — seul le paper broker est actif. Le live exige
   `LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK` **et** des clés.
3. **Rule-first** — les IA (y compris ML) *proposent, scorent, expliquent*. Les
   garde-fous quantitatifs décident.

---

## 2. État d'avancement

| Phase | Contenu | Statut |
|---|---|---|
| 1 | Agents déterministes, CIO, Risk, Execution paper, Audit, backtest, **boucle d'apprentissage**, API, tests | ✅ |
| 2 | Données réelles (ccxt + yfinance) + cache + repli, multi-timeframe réel, **persistance SQLite** | ✅ |
| 3 | **Rapport HTML** autonome + **dashboard live** FastAPI | ✅ |
| 3b | **Live-paper** (Alpaca paper + Binance testnet), boucle temps réel | ✅ |
| 4 | **Walk-forward OOS**, agent **SMC**, agent **ML proposeur** | ✅ |
| 5 | **PostgreSQL** + **Prometheus/Grafana**, agents **Macro/News/Sentiment** | ✅ |
| 6 | **SL/TP structure-aware** (S/R, liquidité, FVG), **sorties intelligentes** (scale-out, break-even, trailing, time-stop), **entrées pullback** (ordres limite), **walk-forward pipeline complet** | ✅ |
| 6b | **Top-20 cryptos**, **timeframes intraday** (1m-1d), **profils de risque** (low/medium/high) | ✅ |
| 7 | **ML calibré** (Platt) → win_prob → EV, **Volume Profile / VWAP ancré**, **filtre edge-net-de-coûts** (anti-sur-trading) | ✅ |
| 8+ | Voir §6 « Vers le bot ultime » | 🔜 |

**Tests : `pytest -q` (doit rester vert).** Le détail du nombre de tests évolue ;
le filet de sécurité couvre indicateurs, décision, risque, exécution, agents,
pipeline, apprentissage, backtest, reporting, live-exec, intelligence, store.

---

## 3. Architecture

```
app/
├── core/          config typée, logging audit, constantes, exceptions
├── data/          indicateurs purs, providers (ccxt/yfinance/cache), sentiment/macro
├── strategies/    régime de marché, SMC (BOS/CHOCH/FVG/sweeps)
├── decision/      ★ EV, conviction, exposition, risque adaptatif, préservation capital
├── risk/          sizing (distance au stop), stops/trailing, drawdown guard, RiskManager (veto)
├── agents/        analytiques (trend/momentum/vol/regime/volume/structure/quant/SMC/ML/macro/news/social)
│                  + CIO (décision) + Audit (journal)
├── scoring/       agrégation des votes, conviction, ranking
├── execution/     PaperBroker, brokers live (Alpaca/Binance testnet), validation, slippage
├── learning/      ★ journal → post-mortem → base de connaissances → pénalités → propositions
├── backtesting/   moteur event-driven, walk-forward OOS, Monte Carlo
├── monitoring/    kill switch, métriques, rapport HTML, dashboard, Prometheus
├── orchestration/ pipeline de décision (10 étapes) + session paper
├── scheduler/     boucle temps réel (RealtimeRunner)
├── db/            persistance (SQLite + PostgreSQL, même interface)
└── api/           API FastAPI (santé, config, dashboard, kill switch, /prometheus)
```

### Pipeline de décision (10 étapes, auditable)
1. Données multi-timeframe → 2. Force relative → 3. Agents → 4. Agrégation +
régime → 5. Risque adaptatif → 6. Préservation capital → 7. Pénalités apprises →
8. **Veto risque** → 9. Décision CIO (conviction → allocation progressive) →
10. Audit. Règle ultime : `EV ≤ 0` **ou** conviction insuffisante **ou** veto →
`FLAT`.

### Boucle d'auto-apprentissage
`décision + résultat → journal → post-mortem (tag + remède) → base de
connaissances (stats sur gagnants ET perdants) → pénalités de conviction →
propositions d'amélioration (jamais auto-appliquées)`. Une leçon n'est retenue
qu'avec assez d'échantillons **et** une espérance négative démontrée.

---

## 4. Démarrage rapide

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                   # filet de sécurité

python scripts/run_paper.py                 # paper offline (synthétique mixte)
python scripts/run_paper.py --source crypto # vraies bougies crypto
python scripts/run_paper.py --ml            # + agent ML
python scripts/run_backtest.py              # backtest + Monte Carlo
python scripts/run_walkforward.py           # robustesse OOS (EMA-cross)
python scripts/run_walkforward.py --pipeline # robustesse OOS du pipeline COMPLET
python scripts/run_live.py --cycles 3       # boucle temps réel (paper)

TRADING_DB=data_store/trading.db uvicorn app.main:app --reload
#   → http://localhost:8000/dashboard   (live)   ·   /docs   ·   /prometheus
```

---

## 5. ALLUMER EN VRAI ET LE LAISSER APPRENDRE — pas à pas

> ⚠️ « En vrai » = **argent fictif** (paper/testnet). Aucun euro réel n'est
> risqué tant que tu ne modifies pas les endpoints à la main. C'est volontaire.

### Étape 0 — Préparer la machine (locale, réseau ouvert)
```bash
git clone <repo> && cd Trading-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q          # tout doit être vert
cp .env.example .env
```

### Étape 1 — Valider sur données réelles (aucun compte requis)
```bash
python scripts/fetch_data.py --source crypto      # met en cache BTC, ETH, …
python scripts/run_paper.py --source crypto --db data_store/trading.db --ml
```
Regarde le rapport `reports/paper_report.html` et lance le dashboard.

### Étape 2 — Walk-forward (vérifier la robustesse avant tout)
```bash
python scripts/run_walkforward.py --source crypto --symbol BTC/USDT --bars 1000
```
Si l'OOS est médiocre/instable → **ne pas passer en live-paper**, c'est normal :
le bot a le droit de ne pas avoir d'edge. On itère.

### Étape 3 — Créer les comptes (gratuits, fictifs)
- **Crypto** : Binance **testnet** → https://testnet.binance.vision → API key/secret.
- **Actions/ETF** : Alpaca **paper** → https://alpaca.markets → clés *paper*.
- (Trade Republic / TradingView : ❌ inutilisables, pas d'API d'exécution.)

Renseigne `.env` :
```
LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK
BINANCE_KEY=...   BINANCE_SECRET=...
ALPACA_KEY=...    ALPACA_SECRET=...
```

### Étape 4 — Lancer la boucle live-paper en continu
```bash
set -a && source .env && set +a
# Top-20 cryptos, intraday 5m (contexte 1H), risque élevé, cycle / 60 s :
python scripts/run_live.py --source crypto --venue binance \
    --timeframe 5m --context-tf 1H --risk high --interval 60 --ml
# Plus posé : 1h / contexte 1d, risque moyen :
python scripts/run_live.py --source crypto --venue binance \
    --timeframe 1H --context-tf 1D --risk medium --interval 300
# Actions sur Alpaca paper :
python scripts/run_live.py --source equities --venue alpaca --timeframe 1D --interval 3600
```
- `--timeframe` : `1m,5m,15m,30m,1H,4H,1D`. `--context-tf` : TF supérieur pour la confluence.
- `--risk` : `low | medium | high` (sizing + nombre de positions ; garde-fous toujours actifs).
- Sans le jeton **ou** les clés → repli automatique sur le paper interne (le dit).

> **Fréquence & risque — réalisme (important).** « Des centaines d'analyses/seconde »
> = HFT : **impossible** en retail (co-location, feeds directs) et **contre-productif**
> (les API gratuites plafonnent ~20 req/s ; surtout, trader trop souvent fait
> exploser frais + slippage et **brûle le capital**). Le plancher réaliste avec
> des données gratuites est **~30-60 s par cycle** sur des bougies 1m-5m. Plus on
> trade vite, plus l'edge par trade doit dépasser les coûts — sinon on perd. Le
> profil `high` augmente la taille et le nombre de positions, **pas** la fréquence
> au point de s'auto-saboter. Le levier reste à 1.0.

### Étape 5 — Le laisser apprendre (la durée fait la qualité)
- Garde **le même `--db`** : décisions, trades, leçons et métriques s'accumulent.
- La base de connaissances (`data_store/knowledge.json` + table `lessons`) mûrit :
  le bot pénalise les contextes perdants et s'affine.
- Surveille via le dashboard (`/dashboard`) et Grafana (§ Monitoring).
- Patience : compte **≥ 3 mois** de paper avant même d'envisager du capital réel.

### Étape 6 — Garde-fous opérationnels
- **Kill switch** manuel : `POST /kill-switch/trigger`. Reset : `POST /kill-switch/reset`.
- DD > 10 % → cash/paper automatique ; DD > 15 % → kill switch.
- Revue hebdo des **propositions d'amélioration** (advisory) avant tout changement.

### Étape 7 — Montée vers le réel (seulement si les KPI tiennent)
Jamais avant : Sharpe stable, DD maîtrisé, exécution conforme sur ≥ 3 mois.
Puis capital réel **très progressif** : 1 % → 5 % → 10 % → 25 % → 50 % → 100 %.
Le passage au live réel exige un travail d'intégration courtier dédié + revue.

---

## 6. Vers le « bot ultime » — toutes les étapes nécessaires

Liste de travail priorisée. Aucune ne garantit la performance ; chacune réduit
le risque de se tromper ou améliore la robustesse.

**A. Fiabilité & données**
1. Données intraday natives (1H/4H réels) + alignement multi-timeframe propre.
2. Qualité des données : détection de trous, splits/dividendes, devises.
3. Multi-sources avec réconciliation (ccxt multi-exchange, fallback).
4. Filtres d'univers réels (volume, spread, capitalisation, liquidité).

**B. Robustesse statistique**
5. ✅ Walk-forward sur le **pipeline complet** (`run_walkforward.py --pipeline`).
6. Validation croisée par régime + tests de stress (2008, 2020, 2022).
7. Purged/embargoed CV pour éviter les fuites temporelles côté ML.
8. Contrôle du sur-apprentissage (deflated Sharpe, PBO).

**C. Intelligence**
9. Wyckoff + order blocks ; pondération apprise des patterns.
10. ML sérieux : XGBoost/LightGBM avec features engineering + MLflow (tracking).
11. Deep Learning (LSTM/TFT/TCN) en proposeurs, calibrés et monitorés (drift).
12. Méta-modèle d'ensemble + calibration des probabilités (isotonic/Platt).
13. Sélection d'agents adaptative : désactiver un agent qui se dégrade.

> ✅ **Déjà livré (Phase 6) :** stops/cibles aux niveaux de structure (S/R,
> liquidité, FVG), sorties intelligentes (scale-out, break-even, trailing,
> time-stop), entrées sur pullback (ordres limite), walk-forward du pipeline
> complet.

**D. Portefeuille & risque**
14. Optimisation de portefeuille (risk parity, corrélations, secteurs).
15. Volatility targeting au niveau portefeuille ; budgets de risque.
16. Gestion fine des shorts (borrow, squeeze, earnings).
17. Stress VaR/CVaR temps réel + limites dynamiques.

**E. Exécution**
18. Exécution réaliste : carnet d'ordres, slippage dépendant de la taille, TWAP/VWAP.
19. Brokers live réels (au-delà du paper) derrière double validation humaine.
20. Réconciliation positions/cash continue + alertes d'incohérence.

**F. Apprentissage continu**
21. Réentraînement planifié + A/B des paramètres (champion/challenger).
22. Détection de drift de marché → bascule de régime de modèle.
23. Boucle « proposition → backtest auto → revue humaine → déploiement ».

**G. Production**
24. PostgreSQL + Redis (cache OHLCV, files de signaux). *(Phase 5: PG livré)*
25. Prometheus + Grafana + alertes Telegram/Email. *(Phase 5: Prometheus livré)*
26. Conteneurisation complète, CI/CD, tests d'intégration, secrets gérés.
27. Sauvegardes, reprise sur incident, journal d'audit immuable horodaté.
28. Conformité : journalisation réglementaire, limites, kill-switch testé.

**H. Gouvernance**
29. Revue humaine obligatoire pour tout changement de risque (déjà imposée par les tests).
30. Documentation vivante (ce fichier), runbooks d'incident.

> Priorité de bon sens : **B et A avant C**. Un modèle brillant sur des données
> douteuses ou sans validation hors-échantillon est dangereux.

---

## 7. Données & courtiers — récapitulatif

| Service | Données | Exécution bot | Usage |
|---|---|---|---|
| ccxt (public) | ✅ crypto, sans clé | — | données crypto |
| yfinance | ✅ actions/ETF | — | données actions |
| Binance testnet | ✅ | ✅ fictif | live-paper crypto |
| Alpaca paper | ✅ | ✅ fictif | live-paper actions |
| Trade Republic | ❌ | ❌ | ⛔ inutilisable |
| TradingView | partiel | ❌ | ⛔ pas de courtier |

> **Session cloud (egress restreint)** : autoriser `api.binance.com`,
> `query1/2.finance.yahoo.com` dans l'allowlist, sinon repli synthétique
> automatique. Voir https://code.claude.com/docs/en/claude-code-on-the-web.

---

## 8. Avertissement

Logiciel de recherche/éducation. Pas un conseil financier. Le trading comporte
un risque de perte substantiel. Les performances passées ou simulées ne
garantissent rien. N'utiliser qu'après un long paper trading hors-échantillon.
