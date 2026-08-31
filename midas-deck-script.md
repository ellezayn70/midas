# MIDAS — Video Script (~5 min)

**Deck:** `midas-deck.html`  
**Length:** 4–6 minutes. Talk over the slides. Don’t read the cards.  
**Voice:** like you’re telling another Hummingbot user how you got here. Simple. First person.

The story lives **in this video**, not on the deck.

---

## Beat 1 — Cover (~60s)  ← hello, then why the name

**On screen:** MIDAS and the coin. Smile first. Don’t rush the hello. Point at the coin when you say “golden touch.”

Hello there.
Good morning!

If you have ever quoted a book
with a small wallet,
you already know this feeling.

Price dumps.
Your stomach drops.
You want to sell.

I built a market maker
named after a king.

The one with
the golden touch.

Introducing, MIDAS!

I named it Midas
for a reason.

Adverse selection
is one of the hardest
problems in market making.

Especially
when your capital is small.

Price dumps.
Somebody knew more than I did.
Toxic flow.

Most days,
that fear makes you sell.

You think —
if I don’t get out now,
it will keep falling.

But some of those dumps
are only there
to scare you
into letting go.

I see those now
as golden moments.

An ordinary coin
in my hand.
If I can hold it —
if I don’t panic sell —
it turns gold.

That is the reminder
in the hard times.

The golden touch.

So this market maker
has Adverse Selection Detection.

Dynamic hedging.
Position sizing.
Self-correcting logic.

It detects toxic flow
and steps aside.

Then it hedges flat
and sizes
so it can keep quoting.

---

## Beat 2 — The House & Builder (~35s)

**On screen:** three Bitget cards, then **I am Elle** at the bottom.

The Trading House is at Bitget.
Why at Bitget?

Bitget has two books
on same pairs for
BTC, ETH, SOL.
It has spot and perps.

A spot fill
hedges on the perp.
That only works
if both books live here.

Gold that does not close.
XAU-USDT perpetual.
Midas can trade it
Twenty-four seven.

Traditional gold market sleeps.
This book does not sleep
at Bitget.

Finally, Bitget volume are deep enough.
A hundred dollars
is a fill, not a noise.


By the way, 
I am Elle, 
the Midas Builder.

I am a Hummingbot user
since late 2022.
From Hummingbot Miner
to XRPLiquid.

Thanks to Condor AI,
my Midas concept
comes to reality.


---

## Beat 3 — The Shield (~50s)  ← let the sim play

**On screen:** the chart. Don’t rush. Wait for TOXIC FLOW, then talk.

Watch this.

The black line is price.

Is somebody smarter than us?

Detection spikes.
Toxic flow.
MIDAS steps out of the way.

Price dumps.

Calm returns.
MIDAS re-quotes.

So MIDAS treats
adverse selection
as unacceptable.

Detection is self-correcting.
It re-evaluates every tick.

---

## Beat 4 — Delta-neutral (~35s)

**On screen:** four steps. Point One, Two, Three, Four as they light.

Here is the Dynamic Hedging.

One —
our spot buy fills.

Two —
we are long.

Three —
Hedge opens
a perp short.
Net exposure goes to zero.

Four —
price dumps.

Spot goes red.
The short goes green.
MIDAS net stays gold
and flat.

We keep the spread,
not the direction.

---

## Beat 5 — The Pairs (~35s)

**On screen:** BTC, ETH, SOL, gold.

Here is the Pair selection.
And the honest story.

The first design
was a one-second
high-frequency market maker.

It does not survive
contact with an LLM tick engine.

The brain needs minutes,
not milliseconds.

So I rebuilt it.
Slow.
Wide.
And safe.

Ten-minute cadence.
Spreads of point one percent
or more per side.
Delta-neutral
so wide is safe.

BTC, ETH, SOL
for the volume.

Gold
for extra tape
that doesn’t correlate
with crypto.

---

## Beat 6 — Under the Hood (~25s)

**On screen:** the four stages.

Here is Under the hood
it is a clean split.

Three routines
do all the math.
Data.
Signal.
Hedge.
No guessing.

The Condor agent
makes the judgment calls.

Hummingbot executes
on Bitget.

Condor decides the trade.
Quote. Hedge. Stand aside.

Hummingbot caps the damage.
Stop-loss. Take-profit.
Time limit. Trailing.
Those sit on every position.

---

## Beat 7 — Implementation (~40s)

**On screen:** three tall cards, then the three-line note at the bottom.

Here is the Technical Implementation.

Detect.
Hedge.
Size.

Adverse Selection Detection.
Five reads of the book.
If P is over point seven,
every quote on that pair
is cancelled.
Immediately.
MIDAS stands aside.

Dynamic Hedging.
Delta equals
spot inventory
plus perp inventory.
Spot long.
Perp short.
Hedge on the same tick.
A dump cannot eat
the spread just collected.

And Position Sizing.
A hundred dollars per side.
One times on both books.
Stop-loss two percent.
Take-profit two percent.
One-hour time limit.
Trailing one point five.
It re-reads the book
every tick.

---

## Beat 8 — Demo in Condor (~25s)

**On screen:** MIDAS lockup, then the Condor screenshot. Point at the shot.

Here is Midas 
running in Condor.

In Portfolio,
We have about 60 dollars
total test fund.
We have 20 dollars in Spot.
and 40 dollars in Futures.

Here in Experiments,
we can see the tests sessions.

We can also see the 3 Routines here.
The Data routine is showing the BTC and SOL books.
The Signal routine is showing the buy and sell prices, 
as well as the spreads.
And Finally, Hedge routine is showing the net delta
and required action for each pair.

In Agents tab,
We can ask Midas agents
some questions.
This is pretty cool for me.

Now lets start Midas.
using Start New Session.
Pick the Midas-Condor Server.
Make sure we selected Loop.
Then click Start.

So Now, Midas is running live.
Lets check our Orders in Bitget Spot.
Here, 
we have 2 BUY orders.
While in Bitget Futures,
there is no order yet.

After some time, our order got filled in spot.
So in Futures, 
we have a new SHORT order opened.

Alright, Midas is working well in Condor.


So, once again.
Remember
MIDAS.

The market maker with
Adverse Selection Detection.
Dynamic hedging.
Position sizing.
Self-correcting logic.

Proudly running in Bitget.
Powered by Condor.

May you all have 
The Golden Touch.

Thank you.

---

## Timing

| Beat | ~s |
|---|---|
| **1 Cover / name** | **60** |
| 2 House & Builder | 35 |
| **3 Shield** | **50** |
| 4 Delta-neutral | 35 |
| 5 Pairs | 35 |
| 6 Under the hood | 25 |
| **7 Implementation** | **40** |
| 8 Demo | 25 |
| **Sum** | **~5:05** |

If you run long, shorten beat 6. **Never shorten beat 1 or 3.** The name, then the aha.

---

## How to say it

- **Cover:** smile. Hello, thanks for watching — not “good morning.” Hook: small wallet, dump, stomach. Then king / golden touch / **MIDAS**. Pause. Then the name story. Don’t list pair names yet. Don’t say “I am Elle” here — that is beat 2.
- Talk like Discord, not like a spec. “Steps aside” is better than “cancels on P(informed).”
- On beat 3, stop talking when the dump starts. Let TOXIC FLOW and QUOTES CANCELLED land. Then pick up.
- Point at the four delta steps. Don’t race them.
- Pause after “I am Elle.” Then Miner to XRPLiquid. Condor and AI.
- Don’t promise easy money. End on the live run, not a slogan.
- Pair names later: **BTC-USDT**, **ETH-USDT**, **SOL-USDT**, **XAU-USDT**.
