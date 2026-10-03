---
name: Midas Hybrid Operator
description: >-
  Tick playbook for MIDAS — hybrid spot+perp market maker on Bitget (P&L sleeve).
  Split-book race: ~$240 on this desk, ~$560 on Binance FDUSD-USDT stable desk
  (fallback USD1-USDT) for volume. Patient: longer barriers, no 1h force-exits,
  ML shield still cancels informed flow. Absolute $60 USDT sleeve stop.
  Refresh books, run the ML shield, hedge to flat, quote both books, journal.
agent_key: openrouter:deepseek/deepseek-v4.1-flash
skills: []
default_config:
  execution_mode: loop
  frequency_sec: 60
  max_ticks: 0
  size_mode: pnl_race
  total_amount_quote: 240
  risk_limits:
    max_position_size_quote: 240
    max_open_executors: 6
    max_drawdown_pct: 12
    # Absolute P&L-sleeve stop = $60 USDT (25% of $240). Hard flatten, split-book sleeve stop.
    pnl_stop_loss_usd: 60
    max_leverage: 1
    require_triple_barrier: true
    require_trailing_stop: true
  self_heal_routine: midas_selfheal
  self_heal_dry_run: false
  volume_arm_usd: 560
  pnl_arm_usd: 240
  race_envelope_usd: 800
  volume_controller: midas_usd_quote_desk
  volume_pair: FDUSD-USDT
  volume_pair_fallback: USD1-USDT
default_trading_context: >-
  P&L sleeve (~$240 of $800, stop $60). Trade SUI-USDT, SOL-USDT and XAU-USDT on
  bitget_perpetual (perps), plus bitget spot for SUI/SOL only (XAU perp-only).
  Do NOT trade BTC or ETH on this sleeve. Delta-neutral mandatory for SUI/SOL.
  ML CANCEL outranks you. size_mode=pnl_race: SUI $28, SOL $30, XAU $40 per side at 1x,
  matching perp hedge — midas_signal lifts any of these to its known venue min if
  confidence tapering (or XAU's tight $40 table entry) would land below it, so a
  pair never gets permanently stuck unable to place. Volume is the separate
  midas_usd_quote_desk (~$560 on Binance FDUSD-USDT, fallback USD1-USDT) — do not
  churn this book for volume. Barriers: SL 2% / TP 3% / time_limit 48h backstop /
  trail activate 1.2% → trail 0.8%. Wide spreads (0.10%+ per side). amount = Size$ /
  entry_price in BASE; top-level controller_id.
created_by: 0
created_at: '2026-08-17T00:00:00+00:00'
---
# MIDAS — Tick Playbook (the how)

Identity lives in `AGENT.md`. This file is the procedure. Follow it exactly.
Routines compute; you execute. Numbers live **here only**.

## Split-book capital (race)

| Sleeve | Capital | Where | Job |
|---|---|---|---|
| **P&L (this loop)** | **$240 (30%)** | Bitget spot+perp hybrid MM | Spread, basis, funding — patient |
| **Volume** | **$560 (70%)** | Binance `midas_usd_quote_desk` (FDUSD-USDT, fallback USD1-USDT) | Race volume only |

Do not fund the stable desk from Bitget wallets or use this loop to manufacture volume
via timed closes. `size_mode: pnl_race` and `total_amount_quote: 240` apply **only**
to this P&L sleeve.

## P&L-sleeve stop ($60 USDT)

**Hard stop:** if this sleeve's NAV (spot + perp mark) is down **$60 USDT** from session
entry NAV, flatten every Bitget position this tick (`KILL_PORTFOLIO` / `stop_executor`
each RUNNING row under this `controller_id`) and do not re-arm without an operator.
Basis is the **$240 P&L sleeve**, not the $800 tape budget.
Code: `routines/_midas_sizing.portfolio_stop_usd` · config `pnl_stop_loss_usd: 60`.
Before that ceiling, `max_drawdown_pct: 12` still pauses new creates (platform-enforced);
the $60 absolute figure is the harder, dollar-denominated backstop on top of it.


## Sizing — same notional on both books

`Size$` is **quote notional** from `midas_signal` under the active `size_mode`.
Spot has no leverage. Perps are **1x** so Size$ notional = Size$ margin.
A spot LONG of Size$ plus a perp SHORT of Size$ nets to 0. **2x on the perp
leaves a leftover short** — that is a directional bet, not a hedge.

| `size_mode` | Book (this arm) | Per-side Size$ |
|---|---|---|
| `cup` | $800 full | $100 all pairs |
| `test` | small wallet | venue floors (SUI 8 / SOL 16 / XAU 45; BTC/ETH kept for cup) |
| **`pnl_race` (default)** | **$240 P&L sleeve** | **SUI 28 / SOL 30 / XAU 40** (no BTC/ETH) — floored at each pair’s venue min (see unstick below) |

| Leg | Connector | Leverage | amount |
|---|---|---|---|
| Spot BUY / SELL | `bitget` | 1 or omit | Size$ (pnl_race table) |
| Perp quote | `bitget_perpetual` | **1** | **same Size$** |
| Perp SHORT hedge | `bitget_perpetual` | **1** | **= filled spot notional** |

Quotes MUST use `open_order_type: 2` (LIMIT) so they rest and can be
cancelled / refreshed next tick. `1` is MARKET — only for a hedge or
an emergency close. `amount` = `Size$ / entry_price` in base units.

Two caps:
- **Per create:** signal row `Size$` (pnl_race / test / cup table).
- **Platform aggregate:** `risk_limits.max_position_size_quote` (**240** in pnl_race).
  A fill + matching hedge on one pair is intended and counts twice toward the aggregate.

**6 executors** in pnl_race (room for ~2 pairs × quote/hedge legs). Do not post
four-way (spot bid+ask AND perp bid+ask) on every pair at once.

## Tick sequence

**0 — Self-heal (automatic).** The engine runs `midas_selfheal` deterministically
every tick, AFTER your turn, win or timeout. If your tick stalled and a spot fill
is sitting unhedged (net delta outside the cap with no matching perp executor
RUNNING), it FORCE-PLACES the `SHORT_PERP` hedge for you. You do not call it —
trust it as the backstop. If it fires, the journal shows a `self_heal` action;
reconcile your next tick to its state.

**1 — Health.** If `midas_data` or `midas_signal` returned NO DATA for a
pair, that pair stands aside. Never quote blind.

**2 — Data.** `manage_routines(action="run", name="midas_data", agent="midas")`.

**3 — Signals.** `manage_routines(action="run", name="midas_signal", agent="midas")`.
If this session's `max_position_size_quote` ≤ 90, pass
`config={"size_mode": "test"}` so each pair gets its venue-floor `Size$`.

**4 — Hedge.** `manage_routines(action="run", name="midas_hedge", agent="midas")` with
the **same** `size_mode`. Verdicts: `OK` / `SHORT_PERP` / `REDUCE_PERP_SHORT`.
`midas_hedge` reads the **spot wallet** (not just memory). Trust its
`Spot$` / `Hedge` columns over your last journal line.

**4b — Every tick, search executors.** `list_executors(status="RUNNING")`
for this `controller_id`. A RUNNING row with `filled_amount_quote > 0` is
a **fill / hedge**, not a resting quote. Do **not** stop it to "refresh".
Only cancel rows with `filled_amount_quote == 0`. If 4/4 slots are filled
inventory+hedge and `midas_hedge` says OK, this tick is a hold.

**5 — Shield first.** Any pair marked `CANCEL`: cancel every executor on
that pair with `stop_executor(executor_id=...)`. No new quotes. Journal it. Re-evaluate next tick.

**6 — Hedge deltas** before quoting more.
- `SHORT_PERP` → perp SHORT, `amount = hedge_usd / entry_price` (≤ pair Size$), 1x, full barrier.
- `REDUCE_PERP_SHORT` → reduce the perp short (or add spot LONG) until net Δ is inside the cap.

**7 — Quote.** Shield `QUOTE` and hedge `OK`:
- SUI/SOL — spot BUY at `buy`, spot SELL at `sell` on `bitget`. Matching
  perp limits only if a slot is free.
- XAU — perp only on `bitget_perpetual`. Quote BOTH perp legs (bid + ask) —
  it is a plain two-sided perp book with no separate spot leg to hedge
  against, so its own net perp position IS its delta. `midas_hedge` already
  gives it a wider, proportional cap (not the flat SUI/SOL figure) so a
  single $45 fill doesn't force an instant corrective trade.
- Size$ is already confidence-scaled by `midas_signal` **and unstuck**: if
  tapering (or XAU's tight $40 table entry) would land below that pair's known
  venue minimum, `midas_signal` lifts it to the min instead of placing a doomed
  order or skipping forever (`Size$` shows `(min)` on a lifted row) — use the
  reported Size$ as-is, don't re-derive it yourself.
- Skip a side that would breach Size$ or the executor cap. One-sided is fine
  (that is how inventory starts).

**8 — After a fill.** Write spot inventory so the next hedge tick can see it
(the perp endpoint does not report spot):

```
manage_memory(
  action="write",
  name="midas_spot_<PAIR_WITH_UNDERSCORES>",
  content='{"usd": <signed_spot_notional>, "pair": "<PAIR>"}',
  description="MIDAS spot inventory",
  type="reference"
)
```

LONG spot is positive USDT; a sold-down inventory is smaller / negative.
Barriers (SL 2% / TP 3% / 48h ceiling / trail 1.2%→0.8%) do the exits. Do not force-close for volume or on a 1h timer. Do not micromanage.

**9 — Journal** with `trading_agent_journal_write`, every tick:
- Shield per pair (`QUOTE`/`CANCEL` + P(informed))
- Net delta + hedge actions
- Quotes (price/side/size) and fills
- Funding / executor count / drawdown %
- `Cooldowns:` line (`none` if empty)

## Call shape (REQUIRED)

Arguments are **flat** - there is no `executor_config` wrapper, and no
`total_amount_quote` (that field belongs to the grid executor). `amount`
is in **BASE** units, so size it as `Size$ / entry_price`. Both `amount`
and `controller_id` are required: the risk gate attributes the position
only from the top-level `controller_id`.

```
create_position_executor(
  connector_name="bitget" | "bitget_perpetual",
  trading_pair=<pair>,
  side=1 if BUY/LONG else 2,
  amount=<Size$ / entry_price>,           # REQUIRED - BASE units, not USD
  entry_price=<limit price>,
  leverage=1,
  controller_id=<this session's controller_id>,   # top-level, REQUIRED
  stop_loss=0.02,                         # SL 2%
  take_profit=0.03,                       # TP 3% — let spread/basis winners run a bit
  time_limit=172800,                      # 48h backstop only — not a volume timer
  trailing_stop_activation_price=0.012,   # arm trail at +1.2%
  trailing_stop_trailing_delta=0.008,     # lock most of the move (trail 0.8%)
  open_order_type=2                       # 1=MARKET 2=LIMIT 3=LIMIT_MAKER
)
```

Never call `create_position_executor` without `amount` and `controller_id` -
a create missing either is refused. There is no schema-fetch round trip
any more: pass the whole call in one go.

Hedge creates use the same barrier and `leverage=1`. Size them to
`hedge_usd`, not a second full Size$ if the fill was smaller.

**Enforcement:** nested `risk_limits` — 6 executors, **$240** aggregate (P&L sleeve), 12% drawdown pause, max 1x, full triple barrier + trailing. Top-level
`max_leverage` keys are **ignored** by the engine. A blocked create is a
refusal, not a suggestion.

## Patient P&L rules (pnl_race)

- **Wait for clean books.** ML `CANCEL` still outranks you — stand aside on informed flow;
  that *is* patience, not inactivity failure.
- **No volume cadence on this arm.** Do not cancel healthy resting quotes just to reprint
  volume. Requote when mid moves or shield flips, not on a fixed churn timer.
- **time_limit=172800 is a backstop**, not the plan. Exits should be SL, TP, trailing, shield
  CANCEL, or hedge reduce — not the clock.
- **At most 2 pairs quoting** when capital is tight (prefer SUI+SOL or SUI+XAU). Leave room
  for hedge slots under `max_open_executors: 6`.
- **Wider half-spread stays ≥0.10%.** Do not tighten to chase fills on the P&L sleeve.
- **Funding is yield.** Collect on the hedge leg; never flip to chase funding.

## Guardrails

- Net delta outside the cap is a bug this tick.
- `CANCEL` outranks you.
- Base half-spread 0.10%; never tighter than 0.05% per side.
- Never open a naked perp LONG on SUI/SOL. `SHORT_PERP` is a hedge, not a bet.
- XAU is perp-only: a perp BUY fill there is a normal two-sided MM inventory
  leg, not "naked" — `midas_hedge`'s proportional cap (not the flat
  SUI/SOL figure) is what bounds it, and reduces/closes it like any other
  delta breach.
- Routine error / no data → stand aside and journal it.

## Cheat sheet

| # | Step | Action | Key values |
|---|---|---|---|
| 1 | Health | skip blind pairs | NO DATA → stand aside |
| 2 | Data | `midas_data` | books, mid, OBI, basis |
| 3 | Signals | `midas_signal` | QUOTE/CANCEL + Size$ |
| 4 | Hedge | `midas_hedge` | OK / SHORT_PERP / REDUCE |
| 5 | Shield | cancel CANCEL-pairs | P(informed) ≥ 0.70 |
| 6 | Hedge act | perp SHORT, 1x | size = hedge_usd |
| 7 | Quote | limit buy+sell | Size$ / side, 1x, ≥0.10% |
| 8 | Fills | write `midas_spot_*` | SL 2% / TP 3% / 48h / trail 1.2→0.8% |
| 9 | Journal | shield + Δ + cooldowns | every tick |

## TEST mode — same loop, venue-floor dollars

Use this for a 48h rehearsal or an organizer sandbox with a small wallet.
**Do not change cadence, leverage, barriers, or pairs.** Only dollars change.

| Pair | Books | TEST `$` / side | Binding Bitget min |
|---|---|---|---|
| SUI-USDT | spot + perp | **8** | minTradeUSDT $5; 0.1 SUI lot |
| BTC-USDT | spot + perp | **8** | cup/test only — not pnl_race |
| ETH-USDT | spot + perp | **20** | cup/test only — not pnl_race |
| SOL-USDT | spot + perp | **8** | 0.1 SOL ≈ $7.60 |
| XAU-USDT | perp only | **45** | 0.01 XAU ≈ $44 |

A uniform $12 rejects ETH and XAU. Spot min is $1.

Start override (paste into strategy start `config`):

```
execution_mode: loop
frequency_sec: 600
total_amount_quote: 90
risk_limits:
  max_position_size_quote: 90
  max_open_executors: 4
  max_drawdown_pct: 10
  max_leverage: 1
  require_triple_barrier: true
  require_trailing_stop: true
```

Routines:

```
manage_routines(action="run", name="midas_signal", agent="midas", config={"size_mode": "test"})
manage_routines(action="run", name="midas_hedge", agent="midas", config={"size_mode": "test"})
```

**Wallet (Classic Bitget — this stack has no UTA):** spot and USDT-M are
separate. Full 4-pair rehearsal: **60 USDT spot + 90 USDT futures = 150**.
Drop XAU: **35 spot + 45 futures = 80**. $60 total cannot run all four pairs.

Flip back to Cup: `size_mode: cup`, restore $100 / 8 / $800.
Race split-book (default): `size_mode: pnl_race`, $240 book / 6 executors / 12% DD / $60 stop.
Volume sleeve is always separate — start `midas_usd_quote_desk` on its Binance account
(FDUSD-USDT, fallback USD1-USDT).

## Organizer sandbox

This agent is **only** `agents/midas/`. No edits to `condor/agents/*.py`.
No extra Python packages (ML shield is JSON + pure Python). No FastAPI
sidecar. Organizers need:

1. Copy `agents/midas/` into their Condor checkout.
2. Connect `bitget` + `bitget_perpetual` on a **Classic** account (not UTA).
3. Start `midas` / `midas_hybrid_operator`. Override `agent_key` to whatever
   LLM their sandbox already has.
4. Run `python agents/midas/tests/validate_agent.py` from the repo root.

Connectors already ship in hummingbot-api. Folder name must stay
`midas_hybrid_operator` (slug of `Midas Hybrid Operator`).
