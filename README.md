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
- **Phase 2 :** persistance PostgreSQL/Redis, SMC avancé (BOS/CHOCH, FVG,
  liquidity sweeps, Wyckoff — faiblement pondérés), walk-forward complet, rapport
  HTML.
- **Phase 3 :** données réelles (ccxt/yfinance), News/Macro/Sentiment/On-chain.
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
