"""Validate MIDAS against Condor's real loaders (no network, no trading).

Organizers: run from the Condor repo root
  .venv/bin/python agents/midas/tests/validate_agent.py
"""
import inspect
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

ok = True

from routines.base import discover_routines_from_path

rdir = REPO / "agents/midas/routines"
found = discover_routines_from_path(rdir, agent_slug="midas")
print("=== ROUTINE DISCOVERY ===")
for name in sorted(found):
    info = found[name]
    fields = list(info.config_class.model_fields) if getattr(info, "config_class", None) else []
    print(f"  [OK] {name:<14} category={info.category:<12} config_fields={fields}")
for expected in ("midas_data", "midas_signal", "midas_hedge"):
    if expected not in found:
        print(f"  [FAIL] {expected} NOT discovered")
        ok = False
if "midas_sizing" in found:
    print("  [FAIL] midas_sizing should not be a routine (helper only)")
    ok = False

print("\n=== ROUTINE CONTRACT ===")
VALID = {"Market Data", "Analysis", "Arbitrage", "Monitoring"}
for name, info in sorted(found.items()):
    has_run = inspect.iscoroutinefunction(info.run_fn)
    good = has_run and info.config_class is not None and info.category in VALID
    ok &= good
    print(
        f"  [{'OK' if good else 'FAIL'}] {name:<14} "
        f"async_run={has_run} Config={bool(info.config_class)} CATEGORY={info.category!r}"
    )

print("\n=== AGENT / STRATEGY LOADING ===")
from condor.agents.agent import AgentStore
from condor.agents.strategy import StrategyStore, _slugify

agent = AgentStore().get("midas")
if not agent:
    print("  [FAIL] agent 'midas' not loaded")
    ok = False
else:
    print(f"  [OK] agent slug={agent.slug} key={agent.agent_key} created_by={agent.created_by}")
    if str(agent.created_by) == "5587715073":
        print("  [FAIL] created_by must not be a personal Telegram id")
        ok = False
    banned = ("hy3", "deepseek", "opencode-go")
    body = (agent.instructions or "").lower()
    leaked = [b for b in banned if b in body]
    # agent_key may name the model; body must not (deck/submitter firewall)
    if leaked:
        print(f"  [FAIL] AGENT.md body leaks provider names: {leaked}")
        ok = False
    else:
        print("  [OK] AGENT.md body has no provider names")

strats = [s for s in StrategyStore().list_all() if s.agent_slug == "midas"]
if not strats:
    print("  [FAIL] no strategy loaded for midas")
    ok = False
for s in strats:
    rl = (s.default_config or {}).get("risk_limits") or {}
    print(f"  [OK] strategy key={s.key} name={s.name}")
    print(f"       freq={s.default_config.get('frequency_sec')}s risk={rl}")
    if not isinstance(rl, dict) or not rl.get("require_triple_barrier"):
        print("  [FAIL] risk_limits must be nested and require_triple_barrier=true")
        ok = False
    exp = _slugify(s.name)
    d = (REPO / "agents/midas/strategies" / exp).is_dir()
    ok &= d
    print(f"  [{'OK' if d else 'FAIL'}] folder '{exp}' matches slugified name")

print("\n=== ISOLATION ===")
import ast

imports = []
for py in (REPO / "agents/midas/routines").glob("*.py"):
    tree = ast.parse(py.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append((py.name, node.module))
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports.append((py.name, a.name))
bad = [f"{f}: {m}" for f, m in imports if m.startswith("agents.midas") or m in ("joblib", "sklearn", "pandas")]
if bad:
    print("  [FAIL] sandbox-unsafe imports:", bad)
    ok = False
else:
    print("  [OK] no agents.midas / joblib / sklearn / pandas imports")

json_model = REPO / "agents/midas/data/informed_trader_model.json"
json_stats = REPO / "agents/midas/data/feature_stats.json"
ok_json = json_model.is_file() and json_stats.is_file()
print(f"  [{'OK' if ok_json else 'FAIL'}] JSON ML weights present")
ok &= ok_json

print("\n=== RESULT:", "ALL CHECKS PASSED" if ok else "FAILURES PRESENT", "===")
sys.exit(0 if ok else 1)
