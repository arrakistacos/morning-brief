import anthropic
import json
from datetime import datetime

SYSTEM_PROMPT = """You are a senior macro analyst and day trader with 20 years of experience across equities, commodities, currencies, and derivatives. Your job is to analyze overnight and morning news and produce a structured intelligence briefing for a day trader.

Your analysis must go DEEP on causality. Don't just state what happened — trace the full chain:
- What happened (the event)
- Why it matters mechanically (supply/demand, policy, geopolitical)
- Which commodities, currencies, sectors, and specific stocks are affected
- Direction of expected price movement and magnitude (high/medium/low confidence)
- Time horizon (intraday, days, weeks)
- Second-order effects (e.g., if oil spikes → airlines hurt → travel sector → hotels)
- Geographic dimensions (which countries, ports, chokepoints, trade routes involved)
- Historical analogs (similar past events and how markets reacted)
- Counterarguments and risks to the thesis

Example of the depth required:
If news says "Iran tensions in the Strait of Hormuz" → you should analyze:
- 21% of global oil trade passes through Hormuz
- LNG from Qatar to Europe/Asia is affected
- Specific tanker routes (VLCC routes to China, Japan, Korea)
- Brent crude vs WTI spread implications
- Oil majors: XOM, CVX, BP likely up; airlines DAL, UAL, LUV likely down
- Tanker stocks: INSW, DHT, FRO likely up on war risk premium
- Defense contractors: LMT, RTX, NOC as potential beneficiaries
- USD likely strengthens as safe haven
- EM currencies of oil importers (INR, TRY, IDR) likely weaken
- Duration: previous Hormuz incidents resolved in 2-6 weeks typically

Apply this same depth to ALL major stories."""


def analyze_news(articles: list, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)

    # Prepare news digest
    news_text = "\n\n".join([
        f"[{a['source']}] {a['title']}\n{a['summary']}"
        for a in articles[:80]  # top 80 articles
    ])

    today = datetime.now().strftime("%A, %B %d, %Y")

    user_prompt = f"""Today is {today}. Here are the overnight and morning news headlines and summaries:

---
{news_text}
---

Produce a comprehensive morning trading brief in the following JSON structure:

{{
  "date": "{today}",
  "overall_sentiment": "BULLISH|BEARISH|NEUTRAL|MIXED",
  "sentiment_score": <-10 to +10, where -10 is extremely bearish, +10 is extremely bullish>,
  "sentiment_reasoning": "<2-3 sentence summary of why>",

  "summary": {{
    "gist": "<2-3 sentences capturing the single most important market narrative of the day. Write like a sharp analyst briefing a fund manager — no hedging, no 'it could go either way', just the signal. State the dominant force, its mechanism, and the directional bet it implies.>",
    "actionable_items": [
      "<Specific, concrete thing to watch or act on today — include ticker, condition, and expected move. Example: 'Watch XOM pre-market — oil above $90 + refinery disruption = gap up likely'>",
      "<Another specific actionable item with ticker and condition>",
      "<Another specific actionable item>",
      "<Another specific actionable item>",
      "<Another specific actionable item>"
    ],
    "stoic_quote": {{
      "text": "<One stoic quote from Marcus Aurelius, Epictetus, or Seneca that is genuinely relevant to today's market conditions. If markets are in panic or fear, choose something about equanimity. If it is a greed rally, choose something about restraint. If there is uncertainty, choose something about focusing on what you control.>",
      "attribution": "<Author name — Work title if applicable, e.g. 'Marcus Aurelius — Meditations'>"
    }}
  }},

  "top_themes": [
    "<theme 1>",
    "<theme 2>",
    "<theme 3>"
  ],

  "macro_events": [
    {{
      "event": "<what happened>",
      "source": "<news source>",
      "significance": "HIGH|MEDIUM|LOW",
      "causal_chain": "<detailed multi-step analysis of cause and effect>",
      "affected_sectors": ["<sector>"],
      "affected_commodities": ["<commodity>"],
      "affected_currencies": ["<currency pair>"],
      "specific_stocks": [
        {{"ticker": "XYZ", "direction": "UP|DOWN", "confidence": "HIGH|MEDIUM|LOW", "reasoning": "<why>"}}
      ],
      "time_horizon": "INTRADAY|DAYS|WEEKS|MONTHS",
      "historical_analog": "<similar past event and market reaction>",
      "counterarguments": "<risks to the thesis>",
      "geographic_dimension": "<countries, regions, trade routes affected>"
    }}
  ],

  "sector_outlook": {{
    "energy": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}},
    "financials": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}},
    "technology": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}},
    "industrials": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}},
    "consumer": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}},
    "healthcare": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}},
    "materials": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}},
    "utilities": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}},
    "real_estate": {{"sentiment": "BULLISH|BEARISH|NEUTRAL", "reasoning": "<>", "key_names": []}}
  }},

  "commodity_outlook": {{
    "crude_oil": {{"direction": "<>", "key_driver": "<>"}},
    "natural_gas": {{"direction": "<>", "key_driver": "<>"}},
    "gold": {{"direction": "<>", "key_driver": "<>"}},
    "silver": {{"direction": "<>", "key_driver": "<>"}},
    "copper": {{"direction": "<>", "key_driver": "<>"}},
    "wheat": {{"direction": "<>", "key_driver": "<>"}},
    "soybeans": {{"direction": "<>", "key_driver": "<>"}}
  }},

  "currency_outlook": {{
    "DXY": "<STRONGER|WEAKER|FLAT and why>",
    "EUR_USD": "<direction and driver>",
    "USD_JPY": "<direction and driver>",
    "USD_CNH": "<direction and driver>"
  }},

  "watchlist": [
    {{
      "ticker": "<>",
      "action": "WATCH_LONG|WATCH_SHORT|AVOID",
      "catalyst": "<specific news-driven reason>",
      "entry_idea": "<price level or condition to watch>",
      "risk": "<what could go wrong>"
    }}
  ],

  "risks_to_watch": [
    "<key risk 1 that could surprise markets today>",
    "<key risk 2>",
    "<key risk 3>"
  ],

  "executive_summary": "<4-6 sentence executive summary a busy trader reads in 30 seconds. Lead with the most important market-moving developments. Include overall directional bias for the day.>"
}}

Be thorough, specific, and actionable. Include real ticker symbols. Prioritize events by market impact."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        messages=[
            {"role": "user", "content": user_prompt}
        ],
        system=SYSTEM_PROMPT,
    )

    # Parse JSON from response
    content = response.content[0].text
    # Extract JSON (handle cases where model wraps in markdown)
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    return json.loads(content)
