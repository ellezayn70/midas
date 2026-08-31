<p align="center">
  <img src="midas-cover.png" alt="MIDAS — hybrid market maker on Bitget" width="880">
</p>

# MIDAS

A hybrid spot + perpetual market maker on Bitget. It quotes both books of the same pair, stays delta-neutral, and steps aside when an informed-flow shield fires. Edge is the spread, the spot↔perp basis, and funding on the hedge — not a directional bet. BTC, ETH, and SOL run two books; XAU-USDT is perp-only.

Not a hummingbot/condor fork. Drop `agents/midas/` into a Condor checkout, connect **Classic** `bitget` + `bitget_perpetual`, start `midas` / `midas_hybrid_operator`, then:

```bash
./.venv/bin/python agents/midas/tests/validate_agent.py
```
