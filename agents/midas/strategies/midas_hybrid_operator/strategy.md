---
name: Midas Hybrid Operator
description: >-
  Tick playbook for MIDAS — hybrid spot+perp market maker on Bitget.
  Refresh books, run the ML shield, hedge to flat, quote both books,
  journal. Wide, slow, always delta-neutral.
agent_key: claude-acp:sonnet
skills: []
default_config:
  execution_mode: loop
  frequency_sec: 30
  max_ticks: 0
  size_mode: test
  total_amount_quote: 800
  risk_limits:
    max_position_size_quote: 800
    max_open_executors: 8
    max_drawdown_pct: 10
    max_leverage: 1
    require_triple_barrier: true
    require_trailing_stop: true
  # Self-healing backstop: midas_selfheal force-closes any delta drift
  # this tick failed to hedge. Condor has no post-turn routine hook, so the
  # tick calls it itself as its last step (see the tick sequence).
default_trading_context: >-
  Trade BTC-USDT and SOL-USDT ONLY on bitget_perpetual (perps) and bitget
  (spot for BTC/SOL). Quote BOTH books. Delta-neutral mandatory. ML CANCEL
  outranks you. TEST size: BTC $14 and SOL $16 quote notional per side at
  1x, with a matching perp hedge per pair. Do NOT trade ETH or XAU (exceeds
  test wallet). Wide spreads (0.10%+ per side). Every create MUST call
  create_position_executor with FLAT args: amount in BASE units
  (= Size$ / entry_price) and top-level controller_id, plus the full
  barrier: SL 2% / TP 2% / 1h / trailing 1.5% / 1.5%, leverage 1.
created_by: 0
created_at: '2026-08-17T00:00:00+00:00'
---

# MIDAS — Tick Playbook (the how)

Identity lives in `AGENT.md`. This file is the procedure. Follow it exactly.
Routines compute; you execute. Numbers live **here only**.

## Sizing — same notional on both books

`$100 per side` is **quote notional**. Spot has no leverage. Perps are
**1x** so $100 notional = $100 margin. A spot LONG of $100 plus a perp
SHORT of $100 nets to 0. **2x on the perp leaves a leftover short** —
that is a directional bet, not a hedge.

| Leg | Connector | Leverage | `total_amount_quote` |
|---|---|---|---|
| Spot BUY / SELL | `bitget` | 1 or omit | **100** (or TEST Size$) |
| Perp quote | `bitget_perpetual` | **1** | **same number** |
| Perp SHORT hedge | `bitget_perpetual` | **1** | **= filled spot notional** |

Quotes MUST use `open_order_type: 2` (LIMIT) so they rest and can be
cancelled / refreshed next tick. `1` is MARKET — only for a hedge or
an emergency close. `amount` = `Size$ / entry_price` in base units.

Two caps:
- **Per create:** $100 (Cup) or the signal row's `Size$` (TEST).
- **Platform aggregate:** `risk_limits.max_position_size_quote: 800`.
  A $100 fill + $100 hedge = $200 on that pair — intended.

**8 executors** = 4 pairs × (quote + hedge). Do not post four-way
(spot bid+ask AND perp bid+ask) on every pair at once.

## Tick sequence


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
- BTC/ETH/SOL — spot BUY at `buy`, spot SELL at `sell` on `bitget`. Matching
  perp limits only if a slot is free.
- XAU — perp only on `bitget_perpetual`.
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
Barriers (SL 2% / TP 2% / 1h / trail 1.5%) do the exits. Do not micromanage.

**9 — Journal** with `trading_agent_journal_write`, every tick:
- Shield per pair (`QUOTE`/`CANCEL` + P(informed))
- Net delta + hedge actions
- Quotes (price/side/size) and fills
- Funding / executor count / drawdown %
- `Cooldowns:` line (`none` if empty)

**10 - Self-heal backstop.** Close the tick with
`manage_routines(action="run", name="midas_selfheal", agent="midas", config={"pairs": "<this session's pairs>", "controller_id": "<this session's controller_id>"})`.
Condor has no post-turn routine hook - this call IS the backstop. If you skip
it, an unhedged spot fill stays unhedged. It reads exchange truth, recomputes
the net delta, and FORCE-PLACES the `SHORT_PERP` hedge when a fill is sitting
unhedged with no matching perp executor RUNNING. If it fires, the journal
shows a `self_heal` action; reconcile your next tick to its state.

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
  stop_loss=0.02,                         # author barrier: SL/TP 2%, 1h
  take_profit=0.02,
  time_limit=3600,
  trailing_stop_activation_price=0.015,
  trailing_stop_trailing_delta=0.015,
  open_order_type=2                       # 1=MARKET 2=LIMIT 3=LIMIT_MAKER
)
```

Never call `create_position_executor` without `amount` and `controller_id` -
a create missing either is refused. There is no schema-fetch round trip
any more: pass the whole call in one go.

Hedge creates use the same barrier and `leverage=1`. Size them to
`hedge_usd`, not a second full Size$ if the fill was smaller.

**Enforcement:** nested `risk_limits` — 8 executors, $800 aggregate, 10%
drawdown pause, max 1x, full triple barrier + trailing. Top-level
`max_leverage` keys are **ignored** by the engine. A blocked create is a
refusal, not a suggestion.

## Guardrails

- Net delta outside the cap is a bug this tick.
- `CANCEL` outranks you.
- Base half-spread 0.10%; never tighter than 0.05% per side.
- Never open a naked perp LONG. `SHORT_PERP` is a hedge.
- XAU is perp-only.
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
| 8 | Fills | write `midas_spot_*` | SL 3 / TP 3 / 3h / 1.5% |
| 9 | Journal | shield + Δ + cooldowns | every tick |

## TEST mode — same loop, venue-floor dollars

Use this for a 48h rehearsal or an organizer sandbox with a small wallet.
**Do not change cadence, leverage, barriers, or pairs.** Only dollars change.

| Pair | Books | TEST `$` / side | Binding Bitget min |
|---|---|---|---|
| BTC-USDT | spot + perp | **8** | 0.0001 BTC ≈ $6.40 |
| ETH-USDT | spot + perp | **20** | 0.01 ETH ≈ $19 |
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

Flip back to Cup: omit `size_mode`, restore $100 / 8 / $800.

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
