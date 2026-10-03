# MIDAS — Organizer Capital Note ($800 Cup entry)

Split-book: two funded sleeves, no auto-transfer between them.

| Sleeve | Share | USD | Venue | Job |
|---|---|---|---|---|
| **Volume** | 70% | **$560** | Binance `midas_usd_quote_desk` (FDUSD-USDT, fallback USD1-USDT) | Race turnover only |
| **P&L** | 30% | **$240** | Bitget spot+perp `midas_hybrid_operator` | Spread/basis/funding — patient |
| **Total** | 100% | **$800** | two venues, two accounts | |

| | |
|---|---|
| P&L-sleeve stop | **$60 USDT** absolute, on this sleeve's own NAV |
| Code | `routines/_midas_sizing.portfolio_stop_usd` · `pnl_stop_loss_usd: 60` |
| Volume pair | `FDUSD-USDT` → fallback `USD1-USDT` (`midas_usd_quote_desk._ensure_pair`) |
| P&L size unstick | `routines/_midas_sizing.effective_per_side` lifts a confidence-tapered—or—tight-table size to the pair's known venue min instead of refusing forever |

Fund the Binance desk and the Bitget sleeve from separate accounts. Do not
transfer between them mid-race; do not use the P&L sleeve to manufacture volume.
