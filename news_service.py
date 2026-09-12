# news_service.py

import re
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import feedparser

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# منابع کامل و دسته‌بندی‌شده بازارهای مالی ایران و جهان
RSS_FEEDS = {
    # منابع دست اول بورس، کدال، افشای اطلاعات و عرضه‌های اولیه
    "bourse_sena": "https://sena.ir/rss",
    "bourse_press": "https://boursepress.ir/rss",
    "bourse_news": "https://www.boursenews.ir/fa/rss/allnews",
    "bourse_nabz": "https://nabzebourse.com/fa/rss/allnews",

    # منابع کلان اقتصادی، بانکی، دلار و طلا
    "iran_eghtesadonline": "https://www.eghtesadonline.com/fa/rss/allnews",
    "iran_tasnim": "https://www.tasnimnews.com/fa/rss/feed/0/7/0/%D8%A7%D9%82%D8%AA%D8%B5%D8%A7%D8%AF%DB%8C",
    "iran_fars": "https://farsnews.ir/rss/economy",
    "iran_isna": "https://www.isna.ir/rss/tp/14",

    # منابع بین‌المللی کریپتو، نفت و طلای جهانی
    "crypto_coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "global_marketwatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "commodities_cnbc": "https://search.cnbc.com/rs/search/view.html?partnerId=2000&keywords=gold%20oil&sort=date",
}

SENT_NEWS_IDS = set()

CUSTOM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

SOURCE_NAMES = {
    "bourse_sena": "سنا (بازار سرمایه)",
    "bourse_press": "بورس‌پرس",
    "bourse_news": "بورس‌نیوز",
    "bourse_nabz": "نبض بورس",
    "iran_eghtesadonline": "اقتصاد آنلاین",
    "iran_tasnim": "خبرگزاری تسنیم",
    "iran_fars": "خبرگزاری فارس",
    "iran_isna": "خبرگزاری ایسنا",
    "crypto_coindesk": "CoinDesk",
    "global_marketwatch": "MarketWatch",
    "commodities_cnbc": "CNBC Commodities",
}


def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleanr = re.compile(r"<.*?>")
    cleantext = re.sub(cleanr, "", raw_html)
    return " ".join(cleantext.split()).strip()


def detect_asset(title: str, summary: str) -> str:
    """تشخیص عمیق دارایی بر اساس اصطلاحات بازار سرمایه و اقتصاد"""
    text = (title + " " + summary).lower()

    # کلمات کلیدی بورس، نمادها، کدال و عرضه‌های اولیه
    bourse_keywords = [
        "بورس", "فرابورس", "عرضه اولیه", "عرضه‌اولیه", "کدال", "شاخص کل", "سهام",
        "حق تقدم", "افزایش سرمایه", "سود مجمع", "تجدید ارزیابی", "نماد", "توقف نماد",
        "بازگشایی", "افشای اطلاعات", "گروه خودرو", "پتروشیمی", "نرخ خوراک", "فولاد",
        "خودرو", "فملی", "شستا", "پالایشی", "صندوق اهرمی", "دامنه نوسان"
    ]
    if any(k in text for k in bourse_keywords):
        return "bourse"

    # رمزارز و کریپتو
    crypto_keywords = [
        "bitcoin", "btc", "crypto", "ethereum", "eth", "tether", "binance",
        "بیت کوین", "بیت‌کوین", "اتریوم", "رمزارز", "کریپتو", "تتر", "هاوینگ", "صرافی ارز دیجیتال"
    ]
    if any(k in text for k in crypto_keywords):
        return "bitcoin"

    # طلا و سکه
    gold_keywords = [
        "gold", "xau", "bullion", "ounce", "طلا", "سکه", "مسکوکات", "اونس",
        "عیار", "حراج سکه", "شمش", "اتحادیه طلا", "حباب سکه", "سکه امامی", "ربع سکه"
    ]
    if any(k in text for k in gold_keywords):
        return "gold18"

    # نفت، گاز و کامودیتی
    oil_keywords = [
        "oil", "crude", "brent", "opec", "petroleum", "energy", "نفت",
        "اوپک", "برنت", "بنزین", "نفت خام", "گاز طبیعی", "پتروشیمی", "انرژی"
    ]
    if any(k in text for k in oil_keywords):
        return "oil"

    # ارز، دلار و سیاست‌های پولی
    dollar_keywords = [
        "dollar", "fed", "forex", "cpi", "rate cut", "دلار", "ارز", "بانک مرکزی",
        "مرکز مبادله", "نیما", "صرافی ملی", "یورو", "تورم", "نقدینگی", "نرخ بهره", "تحریم"
    ]
    if any(k in text for k in dollar_keywords):
        return "dollar"

    return "general"


def fetch_latest_news(target_asset: str = "all", limit: int = 8, hours_lookback: int = 36):
    """
    دریافت اخبار موثق با عمق زمانی مناسب (۳۶ ساعت اخیر)
    برای جلوگیری از نادیده گرفتن اخبار باارزش و عرضه‌های اولیه
    """
    all_news = []
    now = datetime.now(TEHRAN_TZ)
    time_threshold = now - timedelta(hours=hours_lookback)

    for category, url in RSS_FEEDS.items():
        try:
            req = urllib.request.Request(url, headers=CUSTOM_HEADERS)
            with urllib.request.urlopen(req, timeout=8) as response:
                feed_data = response.read()

            feed = feedparser.parse(feed_data)
            for entry in feed.entries[:12]:
                title = clean_html(entry.get("title", ""))
                summary = clean_html(entry.get("summary", entry.get("description", "")))[:350]
                link = entry.get("link", "")
                news_id = entry.get("id", link) or title

                # بررسی اعتبار زمانی خبر
                if entry.get("published_parsed"):
                    try:
                        pub_tuple = entry.published_parsed
                        entry_dt = datetime(*pub_tuple[:6], tzinfo=ZoneInfo("UTC")).astimezone(TEHRAN_TZ)
                        if entry_dt < time_threshold:
                            continue
                    except Exception:
                        pass

                asset = detect_asset(title, summary)
                is_domestic = not (category.startswith("crypto_") or category.startswith("global_") or category.startswith("commodities_"))
                source_name = SOURCE_NAMES.get(category, "اخبار اقتصادی")

                if target_asset == "all" or asset == target_asset:
                    all_news.append({
                        "id": news_id,
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "asset": asset,
                        "source_name": source_name,
                        "source_type": "داخلی" if is_domestic else "بین‌المللی",
                    })
        except Exception:
            continue

    # حذف موارد تکراری و مشابه
    unique_news = []
    seen_titles = set()
    for n in all_news:
        normalized_title = re.sub(r"[^\w\s]", "", n["title"][:45])
        if normalized_title not in seen_titles:
            seen_titles.add(normalized_title)
            unique_news.append(n)
        if len(unique_news) >= limit:
            break

    return unique_news


def is_news_already_sent(news_id: str) -> bool:
    return news_id in SENT_NEWS_IDS


def mark_news_as_sent(news_id: str):
    SENT_NEWS_IDS.add(news_id)
    if len(SENT_NEWS_IDS) > 500:
        SENT_NEWS_IDS.pop()