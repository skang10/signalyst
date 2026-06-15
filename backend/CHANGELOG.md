# Changelog

## [0.17.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.16.0...signalyst-backend-v0.17.0) (2026-06-14)


### Features

* **backend:** generalize market profiles for sp500/eurusd ([#70](https://github.com/skang10/signalyst/issues/70)) ([cf205f1](https://github.com/skang10/signalyst/commit/cf205f129bb93cd2436107851fbb3e5c2755c1ad))
* wire results dashboard to real analysis data ([#71](https://github.com/skang10/signalyst/issues/71)) ([e83d9f8](https://github.com/skang10/signalyst/commit/e83d9f8364ae8eede95f65076a4737cc0118f525))

## [0.16.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.15.0...signalyst-backend-v0.16.0) (2026-06-14)


### Features

* connector chip grouping, staleness detection, and upload UI on Config page ([#59](https://github.com/skang10/signalyst/issues/59)) ([54d5076](https://github.com/skang10/signalyst/commit/54d50762c5f542d26e984947fff237e24ac153eb))
* surface and persist uploaded data sources across re-runs ([#63](https://github.com/skang10/signalyst/issues/63)) ([bcc8e08](https://github.com/skang10/signalyst/commit/bcc8e0898482c23bf087d3e6462cf446e4f79ba5))


### Bug Fixes

* **ci:** retry docker build on transient registry timeouts ([#58](https://github.com/skang10/signalyst/issues/58)) ([86a5690](https://github.com/skang10/signalyst/commit/86a56908e075164deda4a839ac2bb6e3e73d7e4d))
* improve chat-triggered data refetch UX ([71f8510](https://github.com/skang10/signalyst/commit/71f8510e875474c64b78b4ee3273edaed1d9cd70))
* improve chat-triggered data refetch UX ([154a5f3](https://github.com/skang10/signalyst/commit/154a5f32a2fd7b15abb279439dcf6238b9742a97))
* route refetch ticker symbols into yfinance params, not bogus connector IDs ([#65](https://github.com/skang10/signalyst/issues/65)) ([1b761d5](https://github.com/skang10/signalyst/commit/1b761d5b7c8967747d6458c9b0da75624847b95d))

## [0.15.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.14.0...signalyst-backend-v0.15.0) (2026-06-10)


### Features

* add timing and detail logs across chat and analysis pipeline ([#57](https://github.com/skang10/signalyst/issues/57)) ([d493861](https://github.com/skang10/signalyst/commit/d493861767e928c166cc8c1da7d413213d047d07))
* session config redesign — editable timeframe, data sources, and stale warnings ([#50](https://github.com/skang10/signalyst/issues/50)) ([f3c297a](https://github.com/skang10/signalyst/commit/f3c297a00f2b91155d5275ab38b228619bcd211b))


### Bug Fixes

* click-to-reveal add input and read featurizer config from session prop ([#52](https://github.com/skang10/signalyst/issues/52)) ([ed2a027](https://github.com/skang10/signalyst/commit/ed2a027b469e71d62e313f513f0ac0c722c16a52))
* include requested timeframe in data fetch cache key ([#54](https://github.com/skang10/signalyst/issues/54)) ([9e3d788](https://github.com/skang10/signalyst/commit/9e3d788a091b34fcf6d74c1f357b227ede674020))

## [0.14.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.13.0...signalyst-backend-v0.14.0) (2026-06-09)


### Features

* add follow-up analysis and refresh session UI ([#49](https://github.com/skang10/signalyst/issues/49)) ([a34eb66](https://github.com/skang10/signalyst/commit/a34eb664fbf3300e964998f375bf17cea4a6cc36))
* add FollowUpAgent and route FOLLOW_UP-stage chat to it (PR 4b) ([#47](https://github.com/skang10/signalyst/issues/47)) ([e0a4c77](https://github.com/skang10/signalyst/commit/e0a4c77a516f48df9ec8991ff27ffdcde99beb40))

## [0.13.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.12.0...signalyst-backend-v0.13.0) (2026-06-07)


### Features

* add ExplanationAgent and wire EXPLAINING into the pipeline ([#41](https://github.com/skang10/signalyst/issues/41)) ([542435b](https://github.com/skang10/signalyst/commit/542435b907705413cd98fb79e470bb34064f8a9e))
* move session tabs to a vertical sidebar and add an editable Config tab ([#39](https://github.com/skang10/signalyst/issues/39)) ([4e1bf7b](https://github.com/skang10/signalyst/commit/4e1bf7bce1a69904f0c3d547576e6383267fa1d9))

## [0.12.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.11.0...signalyst-backend-v0.12.0) (2026-06-07)


### Features

* replace RunAnalysisChip with UserReviewGate config editor ([#36](https://github.com/skang10/signalyst/issues/36)) ([718a88a](https://github.com/skang10/signalyst/commit/718a88aac80075bf42679bca7487572a1d2f0984))

## [0.11.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.10.0...signalyst-backend-v0.11.0) (2026-06-06)


### Features

* DataSourceDiscoveryAgent, DataAgent, ReviewInterpreter, /chat endpoint ([#32](https://github.com/skang10/signalyst/issues/32)) ([205728a](https://github.com/skang10/signalyst/commit/205728a457fddd72a392fd792631fcf3f968aec7))
* deterministic pipeline (FeaturizerService, TabPFNService, stage machine) ([#30](https://github.com/skang10/signalyst/issues/30)) ([648a17a](https://github.com/skang10/signalyst/commit/648a17abaaa0e909a78a16144f0b437863e5eeb9))

## [0.10.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.9.0...signalyst-backend-v0.10.0) (2026-06-04)


### Features

* **chat window:** collapsible chat panel with pre-run message context ([#15](https://github.com/skang10/signalyst/issues/15)) ([cbaeb89](https://github.com/skang10/signalyst/commit/cbaeb89f25b79f745c73dfd09787f215e8c6362f))
* session data model, CRUD API, and frontend rebuild ([#29](https://github.com/skang10/signalyst/issues/29)) ([baab910](https://github.com/skang10/signalyst/commit/baab9107e0a31919508c764f9d4ab24ff653221d))

## [0.9.0](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.8.1...signalyst-backend-v0.9.0) (2026-05-29)


### Features

* data discovery layer with user-extensible connectors ([#10](https://github.com/skang10/signalyst/issues/10)) ([182426d](https://github.com/skang10/signalyst/commit/182426d0cdb04188cd7ef82c4098913afe00499d))

## [0.8.1](https://github.com/skang10/signalyst/compare/signalyst-backend-v0.8.0...signalyst-backend-v0.8.1) (2026-05-28)


### Bug Fixes

* remove tabpfn-extensions and improve README ([#5](https://github.com/skang10/signalyst/issues/5)) ([da014f0](https://github.com/skang10/signalyst/commit/da014f09f2aace5b9f9e3293a92624cc99f9a45d))

## [0.8.0](https://github.com/skang10/temporal-agent/compare/temporal-agent-backend-v0.7.0...temporal-agent-backend-v0.8.0) (2026-05-25)


### Features

* Run/Resume UX + backend logging improvements ([#81](https://github.com/skang10/temporal-agent/issues/81)) ([434c4e1](https://github.com/skang10/temporal-agent/commit/434c4e1561e1ae654ae1fc5586a5c4622c99a02d))

## [0.7.0](https://github.com/skang10/temporal-agent/compare/temporal-agent-backend-v0.6.0...temporal-agent-backend-v0.7.0) (2026-05-20)


### Features

* agent drawer, live thought stream, and evaluate_features fix ([#71](https://github.com/skang10/temporal-agent/issues/71)) ([7fdf8a7](https://github.com/skang10/temporal-agent/commit/7fdf8a70bf25e5c132ceba63be893420578f5e00))

## [0.6.0](https://github.com/skang10/temporal-agent/compare/temporal-agent-backend-v0.5.0...temporal-agent-backend-v0.6.0) (2026-05-18)


### Features

* frontend split-pane dashboard ([#58](https://github.com/skang10/temporal-agent/issues/58)) ([c419fff](https://github.com/skang10/temporal-agent/commit/c419fff2127bf1ecefc4908fecc100fae24fb8f8))

## [0.5.0](https://github.com/skang10/temporal-agent/compare/temporal-agent-backend-v0.4.0...temporal-agent-backend-v0.5.0) (2026-05-08)


### Features

* deferred agent tools (GPR, drift, SHAP, backtest) ([#56](https://github.com/skang10/temporal-agent/issues/56)) ([22d8932](https://github.com/skang10/temporal-agent/commit/22d8932ce65e739b4ed3ea9e467ddd32dfa567b0))

## [0.4.0](https://github.com/skang10/temporal-agent/compare/temporal-agent-backend-v0.3.0...temporal-agent-backend-v0.4.0) (2026-05-07)


### Features

* tool registry, agent tools, and ReAct loop  ([#54](https://github.com/skang10/temporal-agent/issues/54)) ([c22ba0b](https://github.com/skang10/temporal-agent/commit/c22ba0b6840e986eaea8547806f377df485b9ded))


### Bug Fixes

* balanced regime labels and direction column display in demo ([#52](https://github.com/skang10/temporal-agent/issues/52)) ([631b5b0](https://github.com/skang10/temporal-agent/commit/631b5b0dda64a81b108762ff03aa7ab51d89beb5))

## [0.3.0](https://github.com/skang10/temporal-agent/compare/temporal-agent-backend-v0.2.0...temporal-agent-backend-v0.3.0) (2026-05-04)


### Features

* DB models and session management ([#51](https://github.com/skang10/temporal-agent/issues/51)) ([c655a43](https://github.com/skang10/temporal-agent/commit/c655a43b81537236c75bd2153f2e27acdc96e40b))
* TabPFN inference wrappers (OilRegimeClassifier + DirectionClassifier) ([#45](https://github.com/skang10/temporal-agent/issues/45)) ([385ae89](https://github.com/skang10/temporal-agent/commit/385ae89a5e8976bf997bdb4cef0c950da7f1f3d8))

## [0.2.0](https://github.com/skang10/temporal-agent/compare/temporal-agent-backend-v0.1.1...temporal-agent-backend-v0.2.0) (2026-05-03)


### Features

* data connectors + TimeSeriesFeaturizer ([#43](https://github.com/skang10/temporal-agent/issues/43)) ([54ab037](https://github.com/skang10/temporal-agent/commit/54ab037d615ad7fd16a43ec56e5cc6d7c1cfb660))

## [0.1.1](https://github.com/skang10/temporal-agent/compare/temporal-agent-backend-v0.1.0...temporal-agent-backend-v0.1.1) (2026-04-29)


### Bug Fixes

* harden scaffold validation ([20638b0](https://github.com/skang10/temporal-agent/commit/20638b0ab63d1670f2975bd3ecfa30a935c304ec))
* use uvx for pip-audit to avoid lock file dependency ([fbc5f23](https://github.com/skang10/temporal-agent/commit/fbc5f234bac5ff58343acf3df0a4f288f1e2eae2))
