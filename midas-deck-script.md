# MIDAS — Video Script (~5 min) · "The market maker that steps aside"

**Format:** 10 slides · ~25-35s each · conversational, not read verbatim.
**Voice:** casual trader, self-aware humor, no corporate-speak. This script is
deliberately DIFFERENT in structure, story beats, and punchlines from any
other submission deck — it reads as a different person entirely.

**Pacing:** pause a beat after every 🎯 · smile on the self-deprecating lines ·
end confident, not apologetic.

---

## SLIDE 01 — Opening (~30s)
> "This is **MIDAS**. 🎯 [**let the name and the coin sit a beat**]
> I built a market maker that **steps aside**. Sounds backwards, right?
> A market maker's whole job is to be there. But the smarter version of that
> job is: be there — *until the flow turns toxic, then stand aside, and quote
> again when the book is clean*. Two books — spot and perpetuals —
> on the same pairs, flat in every weather, and three ways to get paid.
> Spread, funding, and the basis between the two books."

## SLIDE 02 — The Builder (~35s)
> "Quick intro. I've been running Hummingbot **Pure Market Making v1**
> since late 2022. Primarily because my Python coding is non-existent.
> [**point at the gold card**] Then Condor happened. That's the pivot.
> For the first time I could ship an agent that thinks — without becoming
> an engineer first. The strategy could live in English. That's when MIDAS
> stopped being a sketch.
> [**right card**] I went looking for one house that could hold the whole
> idea. Bitget had it: spot and perps on the same names, a live gold perp
> that runs when traditional gold is closed, and depth that can actually
> take a quote. That's why MIDAS trades here."

## SLIDE 03 — Two Books (~40s) ← LADDER + STAND-ASIDE CYCLE
> "This is the aha — watch the three books. Spot, perps, gold. Same brain.
> [**point at the four steps**] Four beats, looping.
> **One — place quotes.** Gold rows: a BUY sitting just under the mid, a SELL
> sitting just over it. That's how a market maker actually posts.
> **Two — someone hits them.** The SELL flashes FILLED. Spread hits the
> pocket. That's how it earns.
> **Three — toxic flow.** Shield fires. Every gold order vanishes. ORDERS
> CANCELLED. MIDAS stands aside. A naive bot would stay and get run over.
> **Four — it quotes again.** Quotes reappear. Another fill. Pocket ticks up.
> That's the whole strategy in eighteen seconds, on all three books at once."

## SLIDE 04 — The Shield (~40s) ← THE SIMULATION, THE AHA MOMENT
> "Now — watch this. This is the aha moment. [**let the simulation play**]
> The black line is price. The gold band is MIDAS quoting both sides — and
> the gauge on the right is the shield's read on the market: *is somebody
> smarter than us in this book right now?*
> Watch what happens when the whale shows up. 🎯 The gauge spikes, the
> quotes disappear — **QUOTES CANCELLED** — and MIDAS steps out of the way.
> The price dumps. The naive market maker who stayed in the book eats the
> loss — you can see it on the P&L lines at the bottom: gray dashed drops,
> gold stays flat.
> Then the calm returns. MIDAS re-quotes, goes back to collecting — and look
> at the P&L: 🎯 **the gold line ends AHEAD.** One bad fill from an informed
> trader can erase a day of spread. So MIDAS treats adverse selection as
> unacceptable — and the P&L lines show exactly why that pays."

## SLIDE 05 — Delta-Neutral (~35s) ← FILL / HEDGE / DUMP
> "Price can dump. MIDAS still doesn't care. [**watch the four beats**]
> **One** — our spot BUY fills. We now own a hundred dollars of BTC.
> **Two** — that's the dangerous moment. Stop here and we are just long.
> A dump would eat the spread we just earned.
> **Three** — the hedge routine opens a matching perp SHORT. Long and short
> cancel. Net exposure goes to zero.
> **Four** — price dumps. Watch the two cards: spot goes red, the short goes
> green, **MIDAS net stays gold and flat.** The unhedged line is the one
> that bleeds. 🎯 That's why we say profitable up, down, or sideways —
> we keep the spread, not the direction."

## SLIDE 06 — The Pairs (~40s) ← honest testing story
> "Pair selection — and the honest story. The first design was a
> **one-second high-frequency market maker**. The classic MM dream: quote
> tight, cancel fast, repeat. It does not survive contact with an LLM tick
> engine — the brain needs minutes, not milliseconds. 🎯 So I rebuilt it:
> **slow, wide, and safe.** Fifteen-minute cadence, spreads of 0.10% or more
> per side, delta-neutral so wide is safe. Fewer fills — but every fill is
> positive-EV, and the bot is still standing at hour 47. BTC, ETH, SOL for
> the volume. Gold, because why would you *not* quote gold?"

## SLIDE 07 — Under the Hood (~30s)
> "Under the hood it's a clean split. Three routines do all the math —
> data, signal, hedge — deterministic, no guessing. The Condor agent makes
> the judgment calls: place quotes, open or reduce the hedge, journal
> everything. Hummingbot executes on Bitget, with platform-enforced barriers
> on every single position. The LLM decides *what*; the platform decides
> *how far it's allowed to go*."

## SLIDE 08 — Risk (~30s)
> "Risk, three layers, no exceptions. **Layer one: the shield outranks
> everything.** Model says informed trader? All quotes on that pair die,
> immediately, no committee. **Layer two: delta-neutral is the point.** A
> directional position isn't a bet — it's a bug, fixed this tick. **Layer
> three: hard caps.** $100 per side, 1x on both books, and
> stop-loss 3%, take-profit 3%, 3-hour limit, trailing 1.5% — enforced
> on every position. Even an AI needs a seatbelt."

## SLIDE 09 — Why Bitget (~30s)
> "This is the Bitget slide. Volume is the job. [**point at the equation**]
> Two books on the same pair — spot and perps. Four markets, including gold.
> A new quote every ten minutes, all weekend. That's more tape on Bitget,
> not a promise to be 'careful.'
> Gold isn't a punchline — it's another live book printing fills.
> And it has to **still be quoting at hour 47**. A bot that blows up
> prints zero. MIDAS stays flat, 1x, barriers on — so the volume doesn't
> stop. 🎯"

## SLIDE 10 — Close (~20s)
> "A market maker that knows when not to stand in, stays flat in every storm,
> and quietly collects — on three books at once. Two books. One brain. **Zero
> directional bets.** 🎯 MIDAS — the market maker with the golden touch.
> Thank you."

---

## Why this lands

- **Distinct structure:** Opening / The Builder / Two Books / The Shield /
  Delta-Neutral / The Pairs / Under the Hood / Risk / Why It Wins / Close — a
  purpose-built map for a delta-neutral market maker, not a generic pitch deck.
- **Distinct voice:** self-deprecating ("Python coding is non-existent"),
  plain-spoken, no corporate or hype phrasing. Condor is the life pivot;
  Bitget is the venue that can hold both books + gold.
- **Distinct signature lines:** "knows when not to stand in" · "steps aside,
  then quotes again" · "even an AI needs a seatbelt" · "the boring kind of
  special".
- **Honest iteration story:** the **1-second → slow-wide-safe cadence rebuild**
  (a real lesson from the cup rehearsal), not a vibe-coding narrative.
- **~4:30-5:00 total.** Trim slides 05/07 if needed — never 01/04/06/10.
