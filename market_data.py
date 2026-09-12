# market_data.py

import requests
from datetime import datetime, timedelta

TGJU_API_URL = "https://api.tgju.org/v1/widget/tmp"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/coins"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,text/plain,*/*",
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
}

TIMEOUT = 15

session = requests.Session()
session.headers.update(HEADERS)

TGJU_ASSETS = {
    "dollar": {"key": "price_dollar_rl", "symbol": "price_dollar_rl", "name": "دلار", "unit": "تومان", "rial": True},
    "euro": {"key": "price_eur", "symbol": "price_eur", "name": "یورو", "unit": "تومان", "rial": True},
    "tether": {"key": "crypto-usdt-irr", "symbol": "crypto-usdt-irr", "name": "تتر", "unit": "تومان", "rial": True},
    "gold18": {"key": "geram18", "symbol": "geram18", "name": "طلای 18 عیار", "unit": "تومان", "rial": True},
    "gold24": {"key": "geram24", "symbol": "geram24", "name": "طلای 24 عیار", "unit": "تومان", "rial": True},
    "emami": {"key": "sekee", "symbol": "sekee", "name": "سکه امامی", "unit": "تومان", "rial": True},
    "half": {"key": "nim", "symbol": "nim", "name": "نیم سکه", "unit": "تومان", "rial": True},
    "quarter": {"key": "rob", "symbol": "rob", "name": "ربع سکه", "unit": "تومان", "rial": True},
    "ounce": {"key": "ons", "symbol": "ons", "name": "اونس طلا", "unit": "دلار", "rial": False},
    "oil": {"key": "oil_brent", "symbol": "oil_brent", "name": "نفت برنت", "unit": "دلار", "rial": False},
}


def normalize_digits(value):
    if value is None:
        return ""
    value = str(value)
    translation_table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )
    return value.translate(translation_table)


def clean_number(value):
    if value is None:
        return None
    value = normalize_digits(value)
    value = (
        value.replace(",", "")
        .replace("٬", "")
        .replace(" ", "")
        .replace("\u200c", "")
        .strip()
    )
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def calculate_change_percent(change, open_price):
    if change is None or open_price is None or open_price == 0:
        return None
    return (change / open_price) * 100


def get_tgju_data():
    keys = ",".join(asset["key"] for asset in TGJU_ASSETS.values())
    try:
        response = session.get(
            TGJU_API_URL,
            params={"keys": keys},
            headers={"Referer": "https://www.tgju.org/"},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        indicators = data.get("response", {}).get("indicators", [])
        if not indicators:
            return {}
        return {item["name"]: item for item in indicators if item.get("name")}
    except Exception as e:
        print(f"TGJU Fetch Error: {e}")
        return {}


def process_tgju_asset(asset_id, config, raw_data):
    item = raw_data.get(config["key"])
    if not item:
        return {
            "id": asset_id, "name": config["name"], "price": None,
            "change": None, "change_percent": None, "high": None,
            "low": None, "open": None, "time": None, "updated_at": None,
            "direction": None, "unit": config["unit"],
        }

    price = clean_number(item.get("p"))
    high = clean_number(item.get("h"))
    low = clean_number(item.get("l"))
    open_price = clean_number(item.get("o"))
    change = clean_number(item.get("d"))

    if config["rial"]:
        if price is not None: price /= 10
        if high is not None: high /= 10
        if low is not None: low /= 10
        if open_price is not None: open_price /= 10
        if change is not None: change /= 10

    change_percent = calculate_change_percent(change, open_price)
    direction = "high" if change and change > 0 else ("low" if change and change < 0 else "neutral")

    return {
        "id": asset_id,
        "name": config["name"],
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "high": high,
        "low": low,
        "open": open_price,
        "time": item.get("t"),
        "updated_at": item.get("updated_at"),
        "direction": direction,
        "unit": config["unit"],
    }


def get_bitcoin_data():
    try:
        url = f"{COINGECKO_BASE_URL}/bitcoin?localization=false&tickers=false&community_data=false&developer_data=false"
        response = session.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        market_data = response.json().get("market_data", {})

        price = clean_number(market_data.get("current_price", {}).get("usd"))
        change = clean_number(market_data.get("price_change_24h_in_currency", {}).get("usd"))
        change_percent = clean_number(market_data.get("price_change_percentage_24h"))
        high = clean_number(market_data.get("high_24h", {}).get("usd"))
        low = clean_number(market_data.get("low_24h", {}).get("usd"))
        direction = "high" if change and change > 0 else ("low" if change and change < 0 else "neutral")

        return {
            "id": "bitcoin",
            "name": "بیت‌کوین",
            "price": price,
            "change": change,
            "change_percent": change_percent,
            "high": high,
            "low": low,
            "open": None,
            "time": None,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "direction": direction,
            "unit": "دلار",
        }
    except Exception as e:
        print(f"CoinGecko Bitcoin Fetch Error: {e}")
        return {
            "id": "bitcoin", "name": "بیت‌کوین", "price": None,
            "change": None, "change_percent": None, "high": None,
            "low": None, "open": None, "time": None,
            "updated_at": None, "direction": None, "unit": "دلار",
        }


def get_market_data():
    market_data = {}
    tgju_raw = get_tgju_data()

    for asset_id, config in TGJU_ASSETS.items():
        market_data[asset_id] = process_tgju_asset(asset_id, config, tgju_raw)

    market_data["bitcoin"] = get_bitcoin_data()
    return market_data


# ============================================================
# استخراج زنده تاریخچه قیمت مستقیماً از وب‌سایت‌های مرجع
# ============================================================

def get_asset_history_points(asset_id: str, days: str = "1"):
    """
    دریافت نقاط زمانی و قیمتی مستقیم از سایت مرجع (بدون نیاز به دیتابیس ربات)
    """
    try:
        # ۱. رمزارزها (بیت‌کوین و تتر)
        if asset_id in ["bitcoin", "tether"]:
            coin = "bitcoin" if asset_id == "bitcoin" else "tether"
            url = f"{COINGECKO_BASE_URL}/{coin}/market_chart?vs_currency=usd&days={days}"
            res = session.get(url, timeout=TIMEOUT)
            if res.status_code == 200:
                raw_prices = res.json().get("prices", [])
                points = []
                for p in raw_prices:
                    points.append({
                        "time": datetime.fromtimestamp(p[0] / 1000),
                        "price": float(p[1])
                    })
                return points

        # ۲. اونس جهانی طلا
        if asset_id == "ounce":
            url = f"{COINGECKO_BASE_URL}/tether-gold/market_chart?vs_currency=usd&days={days}"
            res = session.get(url, timeout=TIMEOUT)
            if res.status_code == 200:
                raw_prices = res.json().get("prices", [])
                return [{"time": datetime.fromtimestamp(p[0] / 1000), "price": float(p[1])} for p in raw_prices]

        # ۳. نفت برنت (از وب‌سرویس عمومی کالاها)
        if asset_id == "oil":
            # درخواست تاریخچه مستقیم نفت
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?range={days}d&interval=60m"
            res = session.get(url, timeout=TIMEOUT)
            if res.status_code == 200:
                chart_data = res.json().get("chart", {}).get("result", [{}])[0]
                timestamps = chart_data.get("timestamp", [])
                closes = chart_data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                points = []
                for t, c in zip(timestamps, closes):
                    if c is not None:
                        points.append({
                            "time": datetime.fromtimestamp(t),
                            "price": float(c)
                        })
                if points:
                    return points

        # ۴. دارایی‌های داخلی (دلار، یورو، طلای ۱۸، سکه امامی و...)
        cfg = TGJU_ASSETS.get(asset_id)
        if cfg:
            symbol = cfg["symbol"]
            factor = 0.1 if cfg["rial"] else 1.0

            # درخواست تاریخچه کندلی/خطی مستقیم از منبع سایت TGJU
            url = f"https://api.tgju.org/v1/chart/chart/history?symbol={symbol}&resolution=D&countback=365"
            res = session.get(url, headers={"Referer": "https://www.tgju.org/"}, timeout=TIMEOUT)
            if res.status_code == 200:
                data = res.json()
                times = data.get("t", [])
                closes = data.get("c", [])

                if times and closes:
                    num_days = int(days)
                    cutoff_time = datetime.now() - timedelta(days=num_days)
                    points = []
                    for t, c in zip(times, closes):
                        point_time = datetime.fromtimestamp(t)
                        if point_time >= cutoff_time:
                            points.append({
                                "time": point_time,
                                "price": float(c) * factor
                            })
                    # اگر برای ۲۴ ساعت تنها یک یا دو کندل روزانه وجود داشت، داده‌های تکمیلی ساعت جاری را اضافه می‌کند
                    if len(points) < 2:
                        points.append({
                            "time": datetime.now(),
                            "price": float(closes[-1]) * factor
                        })
                    return points

    except Exception as e:
        print(f"Error fetching live external points for {asset_id} (days={days}): {e}")

    return None