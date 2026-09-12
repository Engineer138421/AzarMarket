# bourse_service.py

import json
import ssl
import urllib.parse
import urllib.request

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Connection": "close",
}

TOP_SYMBOLS = {
    "فولاد": "46348559193224090",
    "خودرو": "65883838195688438",
    "فملی": "35425587644337450",
    "شستا": "2400322364771558",
    "خساپا": "35366681030756042",
    "شپنا": "48000010189958364",
    "شبندر": "38435132646394236",
    "شتران": "63917421733089886",
    "وبملت": "700973099950420",
    "وتجارت": "64506306090442384",
    "صبا": "67375210959062331",
    "اهرم": "37750849313271789",
    "توان": "40209503460777503",
    "موج": "39943564023772874",
    "فاسمین": "18408906660144577",
    "ذوب": "44891419799274092",
}


def get_bourse_index():
    """استعلام شاخص کل بورس"""
    try:
        url_tgju = "https://call.tgju.org/ajax.json"
        req = urllib.request.Request(url_tgju, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=3.5, context=ssl_ctx) as response:
            raw = json.loads(response.read().decode("utf-8"))
            bourse_node = raw.get("current", {}).get("bourse")
            if bourse_node:
                p_str = str(bourse_node.get("p", "0")).replace(",", "")
                d_str = str(bourse_node.get("d", "0")).replace(",", "")
                dp_str = str(bourse_node.get("dp", "0")).replace(",", "")
                dt = bourse_node.get("dt", "neutral")
                return {
                    "price": float(p_str),
                    "change": float(d_str),
                    "change_percent": float(dp_str),
                    "direction": "high" if dt == "high" else ("low" if dt == "low" else "neutral"),
                }
    except Exception:
        pass

    try:
        url_tse = "http://cdn.tsetmc.com/api/MarketData/GetMarketOverview/1"
        req = urllib.request.Request(url_tse, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=3.5, context=ssl_ctx) as response:
            data = json.loads(response.read().decode("utf-8"))
            overview = data.get("marketOverview", {})
            val = overview.get("indexLastValue")
            chg = overview.get("indexChange")
            if val is not None and chg is not None:
                base = val - chg
                pct = (chg / base) * 100 if base != 0 else 0
                return {
                    "price": float(val),
                    "change": float(chg),
                    "change_percent": float(pct),
                    "direction": "high" if chg > 0 else ("low" if chg < 0 else "neutral"),
                }
    except Exception:
        pass

    return None


def search_and_get_symbol_data(query: str):
    """استخراج دقیق و بدون نقص تابلوی معاملات، صف‌ها و درصد تغییرات"""
    q_clean = query.strip()
    ins_code = TOP_SYMBOLS.get(q_clean)
    symbol_name = q_clean
    company_name = ""

    # ۱. جستجوی کد نماد در صورت نبود در کش
    if not ins_code:
        encoded = urllib.parse.quote(q_clean)
        search_urls = [
            f"http://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{encoded}",
            f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{encoded}",
        ]
        for s_url in search_urls:
            try:
                req = urllib.request.Request(s_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=3.5, context=ssl_ctx) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    instruments = res.get("instrumentSearch", [])
                    if instruments:
                        ins_code = instruments[0].get("insCode")
                        symbol_name = instruments[0].get("lVal18AFC", q_clean).strip()
                        company_name = instruments[0].get("lVal30", "").strip()
                        break
            except Exception:
                continue

    if not ins_code:
        return None

    # ۲. استعلام تابلوی قیمت پایانی، آخرین قیمت و سقف/کف مجاز
    p_data = {}
    price_urls = [
        f"http://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{ins_code}",
        f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{ins_code}",
    ]

    for p_url in price_urls:
        try:
            req_p = urllib.request.Request(p_url, headers=HEADERS)
            with urllib.request.urlopen(req_p, timeout=3.5, context=ssl_ctx) as resp:
                p_data = json.loads(resp.read().decode("utf-8")).get("closingPriceInfo", {})
                if p_data:
                    break
        except Exception:
            continue

    if not p_data:
        return None

    last_p = p_data.get("pDrCotVal", 0)
    close_p = p_data.get("pClosing", 0)
    yest_p = p_data.get("priceYesterday", 0)
    price_max = p_data.get("priceMax", 0)  # سقف قیمت مجاز روز
    price_min = p_data.get("priceMin", 0)  # کف قیمت مجاز روز

    # محاسبه ریاضی درصد تغییر بر اساس قیمت دیروز
    change_pct = 0.0
    if yest_p > 0 and last_p > 0:
        change_pct = ((last_p - yest_p) / yest_p) * 100
    elif p_data.get("yesterdayClosingPriceChangePercent"):
        change_pct = float(p_data.get("yesterdayClosingPriceChangePercent"))

    # ۳. استعلام صف‌ها از اندپوینت BestLimits
    best_limits = []
    order_urls = [
        f"http://cdn.tsetmc.com/api/BestLimits/{ins_code}",
        f"https://cdn.tsetmc.com/api/BestLimits/{ins_code}",
    ]
    for o_url in order_urls:
        try:
            req_o = urllib.request.Request(o_url, headers=HEADERS)
            with urllib.request.urlopen(req_o, timeout=3, context=ssl_ctx) as resp:
                best_limits = json.loads(resp.read().decode("utf-8")).get("bestLimits", [])
                if best_limits:
                    break
        except Exception:
            continue

    # تحلیل صف خرید و فروش
    queue_status = "متعادل / بدون صف"
    queue_volume = 0

    if best_limits:
        # مرتب‌سازی سطرهای سفارش بر اساس شماره ردیف (order number)
        sorted_limits = sorted(best_limits, key=lambda x: x.get("number", 1))
        first_row = sorted_limits[0]

        buy_vol = first_row.get("qTitMeBuy", 0)
        sell_vol = first_row.get("qTitMeSell", 0)
        buy_price = first_row.get("pMeBuy", 0)
        sell_price = first_row.get("pMeSell", 0)

        # اگر سمت فروش خالی بود و قیمت خرید در سقف مجاز روز بود -> صف خرید
        if (sell_vol == 0 or sell_price == 0) and buy_vol > 0:
            queue_status = "صف خرید 🟢"
            queue_volume = buy_vol
        # اگر سمت خرید خالی بود و قیمت فروش در کف مجاز روز بود -> صف فروش
        elif (buy_vol == 0 or buy_price == 0) and sell_vol > 0:
            queue_status = "صف فروش 🔴"
            queue_volume = sell_vol
        elif buy_price == price_max and buy_vol > sell_vol * 3:
            queue_status = "صف خرید 🟢"
            queue_volume = buy_vol
        elif sell_price == price_min and sell_vol > buy_vol * 3:
            queue_status = "صف فروش 🔴"
            queue_volume = sell_vol

    return {
        "ins_code": str(ins_code),
        "symbol": symbol_name,
        "name": company_name or symbol_name,
        "last_price": int(last_p),
        "close_price": int(close_p),
        "yesterday_price": int(yest_p),
        "change_pct": round(change_pct, 2),
        "trades_count": int(p_data.get("zTotTran", 0)),
        "volume": int(p_data.get("qTotTran5J", 0)),
        "value": int(p_data.get("qTotCap", 0)),
        "min_day": int(price_min),
        "max_day": int(price_max),
        "queue_status": queue_status,
        "queue_volume": queue_volume,
        "best_limits": best_limits,
    }