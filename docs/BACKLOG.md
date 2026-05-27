# Backlog

Known issues and future improvements that don't belong in a specific session plan.

---

## Inference / Label Quality

### ~~Label imbalance in regime classifier~~ ✅ Fixed (PR #52)
Hand-labeled known historical regime periods added to `scripts/demo.py` as `_KNOWN_REGIMES`. Heuristic thresholds also lowered from ±20% to ±15%. Label distribution improved from 92% `range_bound` to a balanced ~30/22/18/12% split.

### ~~Direction column shows "—" for last N rows in demo~~ ✅ Fixed (PR #52)
`_sample_prediction_dates` now picks only dates present in both regime and direction indices.

---

## Sessions Roadmap

| Session | Focus | Status |
|---|---|---|
| Session 1 | Data connectors + TimeSeriesFeaturizer | ✅ Done (PR #43) |
| Session 2 | TabPFN inference wrappers | ✅ Done (PR #45) |
| Session 3 | `src/db/` — SQLModel run/history models + Alembic migration | ✅ Done (PR #51) |
| Session 4 | `src/agent/` — tool definitions + ReAct loop (Anthropic SDK) | ✅ Done (PR #56) |
| Session 5 | Wire up API routes + deferred tools (drift, SHAP, backtest, GPR) | ✅ Done (PR #56) |
| Session 6 | Frontend core — split-pane layout, AgentStream, RegimeCard, DirectionCard, SummaryPanel | ✅ Done (PR #58) |
| Session 7 | Frontend UX — collapsible agent drawer, live thought stream, tab navigation, fix evaluate_features crash | ✅ Done (PR #71) |

---

## Planned but Not Yet Built

### Mid Tier

#### Authentication
JWT backend + NextAuth.js frontend. All dependencies are already installed (`python-jose`, `passlib[bcrypt]`, `next-auth`) — just not wired up.
- Backend: User model, `POST /api/auth/register`, `POST /api/auth/token` (OAuth2 password flow), `Depends(get_current_user)` guard on routes, per-user run history
- Frontend: NextAuth.js Credentials provider, `useSession()` gate on dashboard, `Authorization: Bearer` header on API client

#### WebSocket Redis pub/sub
`api/ws.py` has a `TODO: subscribe to Redis channel`. Currently WS broadcasts directly from the agent loop, which won't scale past a single backend instance. Needs Redis pub/sub so any backend replica can receive and forward messages.

---

### Frontend Gaps

#### Derivatives Panel
`src/derivatives/` (GBM/Heston Monte Carlo, options pricing, Greeks) and `POST /api/derivatives/price` are fully implemented on the backend. The frontend panel was never built:
- Animated Monte Carlo path fan chart
- Payoff surface (price vs. time)
- Greeks dashboard (delta, gamma, vega, theta)
- European vs. American side-by-side comparison
- Regime auto-fills vol assumption from TabPFN output

#### Geopolitical Risk Chart
GPR index is fetched by the agent (`fetch_geopolitical_risk` tool) but there is no dedicated chart tab. Planned as an overlay on WTI price (see PLAN.md Step 4).

#### History Page
`GET /api/history` exists on the backend but there is no UI for it. User flow Step 1 references "summary of last analysis" on the home page.

---

### Phase 2 (Later)

- **Follow-up questions chat box** — user types questions after analysis; agent calls tools and streams back the answer
- **Save & export** — PDF report, CSV data, shareable read-only link
- **Satellite imagery** — oil storage tank fill levels, refinery activity, shipping traffic via vision encoder → TabPFN features
