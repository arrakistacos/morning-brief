import feedparser
import requests
from datetime import datetime, timedelta
import json

RSS_FEEDS = {
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Reuters Markets": "https://feeds.reuters.com/reuters/companyNews",
    "AP Business": "https://feeds.apnews.com/rss/apf-business",
    "CNBC Top News": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC Finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "Financial Times": "https://www.ft.com/rss/home",
    "Seeking Alpha": "https://seekingalpha.com/market_currents.xml",
    "Benzinga": "https://www.benzinga.com/feed",
    "Investing.com News": "https://www.investing.com/rss/news.rss",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
}

GEOPOLITICAL_FEEDS = {
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Foreign Policy": "https://foreignpolicy.com/feed/",
}

ECONOMIC_FEEDS = {
    "Fed Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "BLS": "https://www.bls.gov/feed/bls_latest.rss",
    "IMF": "https://www.imf.org/en/News/rss",
}


def fetch_all_news(hours_back=12):
    """Fetch news from all sources from the last N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours_back)
    articles = []

    all_feeds = {**RSS_FEEDS, **GEOPOLITICAL_FEEDS, **ECONOMIC_FEEDS}

    for source, url in all_feeds.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:  # max 15 per source
                # Parse publish date
                published = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    from time import mktime
                    published = datetime.fromtimestamp(mktime(entry.published_parsed))

                # Only include recent articles
                if published and published < cutoff:
                    continue

                articles.append({
                    "source": source,
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", "")[:500],
                    "link": entry.get("link", ""),
                    "published": published.isoformat() if published else None,
                })
        except Exception as e:
            print(f"Failed to fetch {source}: {e}")

    # Sort by recency
    articles.sort(key=lambda x: x.get("published") or "", reverse=True)
    return articles


def fetch_economic_calendar():
    """Return known upcoming economic events (hardcoded major ones to watch)."""
    return {
        "reminder": "Check FOMC meeting dates, CPI/PPI release, jobs report, earnings season"
    }
