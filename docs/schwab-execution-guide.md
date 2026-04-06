# 📱 Charles Schwab Android Execution Guide
*Translating Muad'Dib Simulator Signals into Real Trades*

---

## 1. Introduction

The Muad'Dib simulator outputs precise trade signals each morning — entry price, stop loss, take profit, and a plain-English thesis. This guide translates each field into exact steps inside the Charles Schwab Android app, so every simulated trade has a clear real-world equivalent.

> ⚠️ **Disclaimer:** This guide is for educational and simulation purposes. The simulator is a paper trading system. Always apply your own judgment before placing real trades.

---

## 2. Reading the Simulator's Trade Signal

| Simulator Field | What It Means | Schwab Setting |
|---|---|---|
| `ticker` | Stock symbol to trade | Search bar |
| `action` | BUY = open long, SELL = close | Buy / Sell button |
| `shares` | Number of shares | Quantity field |
| `price` | Simulated entry price | Limit Price (Buy order) |
| `stop_loss_price` | Auto-sell if stock falls here | Stop Price (Stop order) |
| `stop_loss_pct` | % below entry (e.g., 8%) | Reference only |
| `target_price` | Take profit level | Limit Price (Sell order) |
| `target_pct` | % above entry (e.g., 15%) | Reference only |
| `risk_reward_ratio` | Target % ÷ Stop % | Reference only |
| `risk_per_trade` | Max dollar loss if stop hits | Reference only |
| `setup_type` | Chart pattern (e.g., bull flag) | Context for entry decision |
| `entry_trigger` | Specific condition that triggered entry | Context for entry decision |
| `timeframe` | Expected hold (days/weeks) | Use GTC duration |
| `exit_plan` | Plain-English exit instructions | Your exit strategy |

### Example Trade Signal

```
ticker:            XOM
action:            BUY
shares:            25
price:             $114.20       → Limit Buy at $114.20
stop_loss_price:   $105.06       → Stop Sell at $105.06 (GTC)
target_price:      $131.33       → Limit Sell at $131.33 (GTC)
risk_reward_ratio: 1.875         → Risking 8% to make 15%
setup_type:        bull flag breakout
timeframe:         1–2 weeks     → Use GTC duration
```

---

## 3. Placing the Entry (Buy) Order

1. Open the Schwab app and tap the **Search** icon.
2. Enter the `ticker` symbol (e.g., `XOM`) and select it.
3. Tap **Trade** → **Buy**.
4. Set **Order Type** to **Limit**.
5. Enter the `shares` value in the **Quantity** field.
6. Enter the simulator's `price` in the **Limit Price** field.
7. Set **Duration** to **GTC** (Good Till Cancelled).
8. Review the order summary — verify ticker, quantity, limit price, and GTC duration.
9. Tap **Place Order**.

> 💡 **Why Limit, not Market?** A Market order fills at whatever the current ask price is — which can be significantly higher than expected. Your Limit price IS the simulator's entry price. Never use Market orders for entries.

**Price tolerance rule:** Only place the entry if the current market price is within 1.5% of the simulator's `price`. If the stock has run too far, skip or wait for a pullback (see Section 9).

---

## 4. Setting the Stop Loss

Place this order **immediately** after the buy order fills — before doing anything else.

| Order Type | How It Works | Use When |
|---|---|---|
| **Stop (Market)** | Triggers at stop price, fills at next available price | Liquid large-caps (AAPL, XOM, SPY) — guaranteed to execute |
| **Stop Limit** | Triggers at stop price, only fills at or above limit price | Avoid for stop losses — may not fill in a fast drop |

### Steps to Place a Stop (Market) Sell Order

1. From the position, tap **Trade** → **Sell**.
2. Set **Order Type** to **Stop**.
3. Enter the simulator's `stop_loss_price` in the **Stop Price** field.
4. Enter the full share quantity in **Quantity**.
5. Set **Duration** to **GTC**.
6. Review and tap **Place Order**.

> ✅ **Rule:** Place your stop loss order immediately after the buy fills — before doing anything else. The simulator enforces an 8% hard stop. Replicate that discipline.

---

## 5. Setting the Take Profit

1. From the position, tap **Trade** → **Sell**.
2. Set **Order Type** to **Limit**.
3. Enter the simulator's `target_price` in the **Limit Price** field.
4. Enter the full share quantity (or half, for partial profit — see below).
5. Set **Duration** to **GTC**.
6. Review and tap **Place Order**.

> 💡 **Partial Profit Taking:** The simulator sometimes sells only HALF at the target and lets the rest ride. To mirror this: set your Limit Sell order for half the shares. After it fills, update your stop loss on the remaining shares to lock in gains (raise stop to your entry price or higher).

---

## 6. The Most Efficient Method: OCO Bracket Orders ⭐

An OCO (One-Cancels-the-Other) bracket order lets you place the stop loss and take profit simultaneously. When one fills, the other automatically cancels — no manual cleanup required.

### Steps to Place a Bracket Order

1. Open the ticker and tap **Trade** → **Buy**.
2. Set **Order Type** to **Limit** and fill in `price` and `shares`.
3. Look for the **"Advanced Order"** or **"Add Bracket"** toggle — tap it.
4. In the **Stop Loss leg**: set type to **Stop**, price to `stop_loss_price`, duration **GTC**.
5. In the **Take Profit leg**: set type to **Limit**, price to `target_price`, duration **GTC**.
6. Review all three legs (entry buy, stop loss sell, take profit sell).
7. Tap **Place Order**.

> ⭐ **Recommended:** OCO bracket orders are the closest real-world replica of how the simulator manages a trade. One order, three legs, automatic cleanup. Use them whenever available.

---

## 7. Closing a Position Early

When the simulator's midday or EOD check recommends an early exit (thesis broken, unexpected news, or a manual close signal):

> ⚠️ **Always cancel existing stop and target orders BEFORE placing a close order.** Failure to cancel open sell orders can result in an unintended short position or duplicate fills.

### Steps

1. Go to **Orders** → find and cancel the GTC Stop order.
2. Go to **Orders** → find and cancel the GTC Limit (take profit) order.
3. Confirm both are cancelled.
4. Return to the position and tap **Trade** → **Sell**.
5. Set **Order Type** to **Market** (for immediate close) or **Limit** (to target a specific price).
6. Enter full remaining share quantity.
7. Tap **Place Order**.

---

## 8. Modifying Orders

Use this when the simulator raises its trailing stop or you want to lock in gains after a significant move.

### Steps to Raise a Stop Loss

1. Go to **Orders** and find the active GTC Stop order.
2. Tap the order → **Modify**.
3. Raise the **Stop Price** to your new level.
4. Confirm and tap **Place Order**.

**Example:** Position is up 8% from entry. Move the stop to breakeven (your original entry price) to eliminate downside risk while letting gains continue to run.

---

## 9. Price Matching Rules

| Scenario | Action |
|---|---|
| Real price within 0.5% of simulator price | Proceed — place Limit at simulator's exact price |
| Real price up to 1.5% above simulator price | Enter, but adjust stop and target proportionally |
| Real price more than 1.5% above simulator price | Wait — chasing destroys risk/reward. Skip or wait for pullback |
| Real price below simulator price | Set Limit at simulator's price and wait for it to fill |

---

## 10. Quick Reference Cheat Sheet

| What to Do | Simulator Field | Schwab Setting |
|---|---|---|
| Enter position | `price` | Buy Limit @ price, GTC |
| Set stop loss | `stop_loss_price` | Sell Stop @ stop_loss_price, GTC |
| Set take profit | `target_price` | Sell Limit @ target_price, GTC |
| Quantity | `shares` | Quantity field |
| Hold duration | timeframe = days/weeks | Always GTC |
| Raise stop after gain | Entry price = new floor | Modify existing Stop order |
| Full close (thesis broken) | N/A | Cancel GTC orders → Sell Market |
| Partial profit | `shares ÷ 2` | Sell Limit @ target for half shares |

---

## 11. Important Rules

### Pattern Day Trader (PDT) Rule

If account equity < $25,000, you are limited to 3 day trades per rolling 5-business-day period. Since this simulator uses swing trading (multi-day holds), this should rarely trigger. Always check your day trade count before initiating a same-day exit.

### T+2 Settlement

Cash from a sell takes 2 business days to settle. The simulator tracks this in the `cash` (settled) vs `unsettled_cash` fields. Schwab displays settled vs. unsettled cash separately in your account view — do not trade with unsettled funds.

### Extended Hours

The simulator only trades regular market hours (9:30 AM – 4:00 PM ET). Avoid extended hours for swing entries — wide spreads and thin liquidity undermine your limit price targets.

### Pre-Trade Checklist

- [ ] Ticker matches exactly
- [ ] Shares quantity correct
- [ ] Limit price within 1.5% of simulator entry
- [ ] Stop loss placed immediately after buy fills
- [ ] Take profit GTC Limit order active
- [ ] Duration is GTC (not Day)
- [ ] Position ≤ 30% of total portfolio
- [ ] No more than 3 open positions

---

> *"I must not fear. Fear is the mind-killer." — Frank Herbert, Dune*

*Execute with precision. Follow the plan. The spice must flow.*
