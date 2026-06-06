# Changelog

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
