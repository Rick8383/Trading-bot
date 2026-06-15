# Algo Trading Bot — multi-agent, risk-first, self-learning

> **Devise du système :** Préserver le capital d'abord. Croître ensuite. Ne trader
> qu'avec un avantage statistique mesuré. Réduire l'exposition dès que cet
> avantage disparaît.

Un bot de trading algorithmique modulaire, déterministe-d'abord, **paper-first**,
avec une **boucle d'auto-apprentissage** : il journalise chaque trade, fait son
post-mortem, en tire des leçons persistantes, et pénalise les configurations qui
ressemblent à ses pertes passées — pour ne pas les répéter et devenir plus pointu
avec le temps.

⚠️ **Aucune promesse de performance.** Logiciel de recherche/éducation. Le trading
comporte un risque de perte substantiel. Le live trading est **désactivé par
défaut** et verrouillé derrière un déverrouillage manuel explicite.

---

## Pourquoi cette architecture

La spec initiale visait 20 agents + ML + Deep Learning + Kafka/Airflow/Kubernetes
d'un coup. C'est le piège qui tue ce genre de projet. Nous livrons d'abord un
**noyau réellement fonctionnel, testé et auditable** (Phase 1), puis nous
empilerons les couches avancées sur des fondations solides.

**Trois règles structurelles, non négociables :**

1. **Risk-first** — le `RiskManager` a un droit de veto absolu. Aucun agent, pas
   même le CIO, ne peut l'outrepasser.
2. **Paper-first** — seul le `PaperBroker` est activé. Le live exige
   `LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK`.
3. **Rule-first** — les IA *proposent, scorent, expliquent*. Les garde-fous
   quantitatifs décident. Le `SelfImprovementEngine` ne déploie jamais seul.

---

## La boucle d'auto-apprentissage (le cœur de la demande)

```
décision + résultat ─▶ TradeJournal (mémoire durable, append-only)
                    ─▶ post-mortem    (taggue ce qui a foiré, avec remède)
                    ─▶ KnowledgeBase  (agrège les leçons sur gagnants ET perdants)
                    ─▶ pénalités de conviction réinjectées dans le CIO
                    ─▶ ImprovementEngine (propositions, JAMAIS auto-appliquées)
```

- Une « leçon » n'est retenue qu'avec **assez d'échantillons** *et* une espérance
  **négative démontrée** (calculée sur gains et pertes). Pas de sur-apprentissage
  sur un coup de malchance.
- Au moment de décider, le pipeline calcule la **signature de contexte** du setup
  envisagé (régime, flags de risque, conviction…) et interroge la base de
  connaissances : si ce contexte a historiquement perdu, la conviction est
  **pénalisée** (plafonnée), ce qui réduit ou annule la position.
- La symétrie « signature à la décision == signature au post-mortem » rend la
  boucle **statistiquement honnête**.

Voir `app/learning/` et le test `tests/test_learning.py`.

---

## Architecture

```
app/
├── core/          config typée (pydantic), logging audit, constantes, exceptions
├── data/          indicateurs (RSI/MACD/ATR/ADX/EMA/OBV/...), data provider
├── strategies/    classificateur de régime de marché
├── decision/      ★ couche philosophie : EV, conviction, exposition,
│                    risque adaptatif, préservation du capital
├── risk/          sizing, stops/trailing, drawdown guard, RiskManager (veto)
├── agents/        base + agents analytiques (Trend, Momentum, Volatility,
│                    Regime, Volume, Structure, Quant) + CIO + Audit
├── scoring/       agrégation des votes, conviction, ranking des opportunités
├── execution/     PaperBroker, validation pré-trade, modèle de coûts/slippage
├── learning/      ★ journal, post-mortem, base de connaissances, auto-amélioration
├── backtesting/   moteur event-driven, Monte Carlo, walk-forward
├── monitoring/    kill switch, métriques (Sharpe/Sortino/Calmar/PF), alertes
├── orchestration/ pipeline de décision (10 étapes) + session de paper trading
└── api/           API FastAPI (santé, config, kill switch)
```

### Le pipeline de décision (10 étapes, auditable)

1. Données multi-timeframe → 2. Force relative cross-section → 3. Agents
analytiques → 4. Agrégation des votes + régime → 5. Risque adaptatif (régime +
volatilité + pertes consécutives) → 6. Préservation du capital (échelle de
drawdown) → 7. Pénalités apprises → 8. **Veto du Risk Manager** → 9. Décision
finale du CIO (conviction → allocation progressive) → 10. Audit.

Règle ultime : si `EV ≤ 0` **ou** conviction insuffisante **ou** veto risque →
`FLAT`. Le bot a le droit de dire « aucune opportunité aujourd'hui ».

---

## Gestion du risque (codée, pas espérée)

| Mécanisme | Règle |
|---|---|
| Risque par trade | 0,5 % – 1 % de l'équité, **borné par la distance au stop** |
| Reward/Risk min | ≥ 2:1 sinon **rejet** |
| Stop obligatoire | un ordre sans stop est **refusé** à la validation |
| Levier | 1.0 par défaut, > max refusé |
| Anti-surconfiance | le risque **n'augmente jamais** après une série de gains |
| Drawdown | >5 %→75 % expo · >8 %→50 % · >10 %→cash/paper · >15 %→**kill switch** |
| Recovery | ré-exposition **progressive** (25→50→75→100 %) |
| Régime crash | risque mis à zéro |

---

## Démarrage rapide

```bash
git clone <repo> && cd Trading-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                      # la suite de tests (le filet de sécurité)
python scripts/run_paper.py    # paper trading sur capital fictif + apprentissage
python scripts/run_backtest.py # backtest + robustesse Monte Carlo

uvicorn app.main:app --reload  # API de monitoring -> http://localhost:8000/docs
```

Avec Docker :

```bash
docker compose build && docker compose up -d   # api + postgres + redis
```

### Exemple de sortie `run_paper.py`

Le bot évalue des milliers de décisions, n'en exécute qu'une poignée à forte
conviction (préservation du capital), affiche Sharpe/Sortino/Calmar/Profit
Factor/Max Drawdown, **les leçons apprises**, et **les propositions d'amélioration**
(consultatives).

---

## Visualisation — voir ce qu'il fait

**Rapport HTML autonome** (graphiques SVG générés côté serveur, zéro dépendance
externe, s'ouvre hors-ligne) :

```bash
python scripts/run_paper.py --db data_store/trading.db --report reports/paper_report.html
# -> ouvre reports/paper_report.html : KPI, courbe d'équité + drawdown, trades,
#    leçons apprises, propositions d'amélioration
```

**Dashboard live** (FastAPI, lit la base durable, auto-refresh 15 s) :

```bash
TRADING_DB=data_store/trading.db uvicorn app.main:app --reload
# -> http://localhost:8000/dashboard   (HTML)   ·   /docs (API)
#    endpoints JSON : /metrics /trades /decisions /lessons /kill-switch
```

## Exécution live-paper (argent fictif, zéro risque réel)

Le bot peut exécuter sur de **vrais comptes paper / testnet** (soldes fictifs) —
jamais d'argent réel sans modifier les endpoints à la main. Double barrière :
il faut **à la fois** le jeton de déverrouillage **et** des clés API.

```bash
# Défaut sûr : broker paper interne sur vraies bougies, quelques cycles
python scripts/run_live.py --source crypto --cycles 3

# Alpaca paper (actions US, argent fictif) — clés gratuites sur alpaca.markets
export LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK
export ALPACA_KEY=... ALPACA_SECRET=...
python scripts/run_live.py --source equities --venue alpaca --interval 3600

# Binance testnet (crypto, argent fictif) — clés sur testnet.binance.vision
export LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK
export BINANCE_KEY=... BINANCE_SECRET=...
python scripts/run_live.py --source crypto --venue binance --interval 900
```

Sans le jeton **ou** les clés, chaque venue **retombe sur le paper broker interne**
et l'indique. Chaque ordre passe la validation (stop obligatoire) **avant** tout
appel réseau, paper comme live. Le loop utilise APScheduler s'il est présent,
sinon une boucle `time.sleep`.

> **À toi de créer les comptes (gratuits, fictifs) :** Alpaca *paper* pour les
> actions, Binance *testnet* pour la crypto. Trade Republic / TradingView ne
> conviennent pas (pas d'API d'exécution). À lancer en local (réseau ouvert).

## Données & courtiers — faut-il un compte ?

**Pour voir ce que le bot sait faire : non, aucun compte.** Le paper trading a
besoin de **données de marché**, pas d'un courtier.

| Service | Données ? | Exécution bot ? | Verdict |
|---|---|---|---|
| **ccxt** (Binance/Kraken/…) | ✅ OHLCV public, **sans clé API** | (plus tard) | ✅ crypto, gratuit |
| **yfinance** (Yahoo) | ✅ actions/ETF, gratuit, sans compte | ❌ | ✅ actions, gratuit |
| **Trade Republic** | ❌ | ❌ pas d'API publique | ⛔ inutilisable pour un bot |
| **TradingView** | partiel | ❌ n'exécute pas d'ordres (alertes seulement) | ⛔ pas un courtier |
| **Alpaca** | ✅ | ✅ **paper trading API gratuite** | 🔜 cible pour le live-paper (actions US) |
| **Binance testnet** | ✅ | ✅ ordres fictifs | 🔜 cible crypto live-paper |

Donc : on commence sur **données réelles gratuites** (ccxt + yfinance). Plus tard,
pour exécuter des ordres « comme en vrai » sans risquer d'argent, on branchera
**Alpaca paper** et/ou **Binance testnet** (un compte gratuit, des clés *paper*,
zéro argent réel). Trade Republic / TradingView ne conviennent pas à un bot.

### Lancer sur de vraies bougies

```bash
python scripts/fetch_data.py --source crypto                  # met en cache BTC, ETH, ...
python scripts/run_paper.py  --source crypto                  # paper sur crypto réel
python scripts/run_paper.py  --source equities                # paper sur SPY/QQQ/...
python scripts/run_paper.py  --source auto --symbols BTC/USDT SPY QQQ
python scripts/run_paper.py  --db data_store/trading.db       # mémoire durable (SQLite)
```

> **Session cloud (egress restreint) :** les hôtes de données doivent être sur
> l'allowlist réseau de l'environnement (`api.binance.com`,
> `query1.finance.yahoo.com`, `query2.finance.yahoo.com`). Sinon le bot **bascule
> automatiquement sur des données synthétiques** et l'indique (`synthetic_fallback`).
> Voir https://code.claude.com/docs/en/claude-code-on-the-web pour la politique réseau.
> En local (réseau ouvert), tout fonctionne directement.

### Persistance

`--db data_store/trading.db` active une base **SQLite** (zéro infrastructure) qui
conserve décisions, trades, leçons et métriques **entre les runs** : la mémoire
d'apprentissage s'accumule et le bot s'affine à chaque session. Le schéma est
identique aux migrations PostgreSQL (`migrations/`), donc passer à Postgres en
production = un changement de chaîne de connexion, pas une réécriture.

## Univers

Actions large-cap liquides, ETF (SPY/QQQ/IWM/TLT/GLD/XLF/XLK/XLE), crypto
(BTC/ETH/SOL/BNB/XRP/AVAX/LINK), avec filtres volume/spread. Configurable dans
`config.yaml`.

> **Données :** la Phase 1 utilise un générateur OHLCV **synthétique déterministe**
> pour que tout tourne et se teste hors-ligne. Les connecteurs réels (ccxt /
> yfinance) sont des dépendances optionnelles à brancher en Phase 3 en
> sous-classant `MarketDataProvider` — sans toucher au reste.

---

## Feuille de route

- **Phase 1 — ✅ livrée :** agents déterministes (Trend, Momentum, Volatility,
  Regime, Volume, Structure, Quant), CIO, Risk, Execution paper, Audit,
  backtesting, **boucle d'apprentissage**, API, tests.
- **Phase 2 — ✅ livrée :** connecteurs de **données réelles** (ccxt crypto +
  yfinance actions/ETF) avec cache disque et repli synthétique, multi-timeframe
  réel (1D + 1W resamplé), **persistance durable SQLite** (décisions/trades/
  leçons/métriques accumulées entre runs), scripts `fetch_data` / `run_paper
  --source`.
- **Phase 3 — ✅ visualisation livrée :** rapport HTML autonome (SVG côté
  serveur) + dashboard live FastAPI (`/dashboard`, auto-refresh) lisant la base
  durable ; endpoints JSON métriques/trades/décisions/leçons.
- **Phase 3b — ✅ livrée :** exécution **live-paper** via Alpaca paper + Binance
  testnet (argent fictif), boucle temps réel (`RealtimeRunner`, APScheduler),
  factory broker sûre par défaut, `scripts/run_live.py`.
- **Phase 4 — ✅ affinage livré :** walk-forward **out-of-sample** complet
  (sélection in-sample, éval hors-échantillon, stabilité des paramètres +
  Monte Carlo), agent **SMC** (BOS/CHOCH, FVG, liquidity sweeps — faiblement
  pondéré), agent **ML proposeur** (régression logistique numpy, XGBoost/sklearn
  auto-détectés ; advisory only).
- **Phase 4b :** Wyckoff, News/Macro/Sentiment/On-chain, PostgreSQL/Redis,
  Grafana/Prometheus.

### Affiner l'intelligence

```bash
python scripts/run_walkforward.py --bars 1000     # robustesse hors-échantillon
python scripts/run_paper.py --ml                  # active l'agent ML (proposeur)
```

SMC et ML sont des **proposeurs faiblement pondérés** : ils nuancent la
conviction mais ne peuvent ni décider, ni outrepasser le veto risque. Le ML
s'entraîne par cycle (donc opt-in via `--ml`) et s'abstient (score 0) sans
données suffisantes.
- **Phase 4 :** ML (XGBoost/LightGBM/CatBoost) puis Deep Learning (LSTM/TFT/TCN),
  toujours en *proposeurs*, jamais décideurs seuls.
- **Phase 5 :** live trading — désactivé par défaut, déverrouillage manuel, après
  ≥ 3 mois de paper concluant et montée progressive du capital (1 %→5 %→…→100 %).

---

## Séquence de mise en production recommandée

1. **Paper trading** ≥ 3 mois, détecter les lacunes, laisser la base de
   connaissances mûrir.
2. **Petit capital** (1–5 % de la cible) uniquement si Sharpe stable + DD maîtrisé
   + exécution conforme.
3. **Montée progressive** 10 % → 25 % → 50 % → 100 %.

La survie du capital prime sur la recherche de rendement. Toujours.
