# bot.py

import asyncio
import io
import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from groq import AsyncGroq
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bourse_service import get_bourse_index, search_and_get_symbol_data
from database import (
    add_user_alert,
    close_poll_record,
    deactivate_alert,
    delete_user_alert,
    get_active_alerts,
    get_daily_summary,
    get_last_active_poll,
    get_upcoming_ipos,
    get_user_alerts,
    init_database,
    save_daily_poll,
    save_ipo_record,
    save_market_snapshot,
    update_ipo_notification,
)
from image_generator import generate_market_card
from market_data import get_market_data
from news_service import (
    fetch_latest_news,
    is_news_already_sent,
    mark_news_as_sent,
)

# =========================================================
# بارگذاری متغیرها
# =========================================================

env_path = Path(__file__).resolve().parent / "gemini-code.env"
load_dotenv(dotenv_path=env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN:
    raise ValueError("مقدار BOT_TOKEN در فایل gemini-code.env یافت نشد.")

if not GROQ_API_KEY:
    raise ValueError("مقدار GROQ_API_KEY در فایل gemini-code.env یافت نشد.")

CHANNEL_ID = "@Daneshjoojoor"
TEHRAN_TZ = ZoneInfo("Asia/Tehran")

groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# مدل‌های بهینه و با تاخیر پایین جهت پاسخ‌دهی آنی
AVAILABLE_MODELS = [
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
]

last_known_gold_price = None
ROUND_STEP = 500_000

BREAKING_KEYWORDS = [
    "فوری", "مهم", "سقوط", "جهش", "نرخ بهره", "حراج سکه", "بانک مرکزی",
    "افزایش قیمت", "کاهش قیمت", "تورم", "مرکز مبادله", "عرضه اولیه", "عرضه‌اولیه", "بورس",
    "شاخص کل", "توقف نماد", "دامنه نوسان", "کدال", "افشای اطلاعات", "افزایش سرمایه",
    "تجدید ارزیابی", "سود مجمع", "نرخ خوراک", "fed", "inflation", "war", "rate cut", "soar", "plunge"
]

MAIN_MENU_BUTTONS = [
    "📊 استعلام قیمت‌ها",
    "📈 استعلام نماد بورس",
    "🧮 ماشین‌حساب طلا",
    "📰 اخبار بازار و بورس",
    "⏰ تنظیم هشدار قیمت",
    "📋 هشدارهای من",
    "📈 تحلیل هوشمند بازار",
    "🔄 شروع مجدد"
]

CALC_TYPE, CALC_WEIGHT, CALC_WAGE = range(3)
ALERT_ASSET, ALERT_CONDITION, ALERT_PRICE = range(10, 13)
TSE_SYMBOL_SEARCH = 20

ASSET_NAMES = {
    "bourse": "شاخص کل بورس",
    "dollar": "دلار و ارز",
    "euro": "یورو",
    "tether": "تتر",
    "gold18": "طلا و مسکوکات",
    "gold24": "طلای ۲۴ عیار",
    "emami": "سکه امامی",
    "half": "نیم سکه",
    "quarter": "ربع سکه",
    "ounce": "اونس جهانی طلا",
    "oil": "نفت برنت",
    "bitcoin": "بیت‌کوین و کریپتو",
}


# =========================================================
# توابع کمکی
# =========================================================

def format_number(value):
    if value is None:
        return "---"
    try:
        value = float(value)
        return f"{int(value):,}" if value.is_integer() else f"{value:,.2f}"
    except (ValueError, TypeError):
        return "---"


def format_change(value):
    if value is None:
        return "---"
    try:
        value = float(value)
        return f"+{value:,.0f}" if value > 0 else f"{value:,.0f}"
    except (ValueError, TypeError):
        return "---"


def format_percent(value):
    if value is None:
        return "---"
    try:
        value = float(value)
        return f"+{value:.2f}%" if value > 0 else f"{value:.2f}%"
    except (ValueError, TypeError):
        return "---"


def get_direction_emoji(direction):
    if direction == "high":
        return "🟢"
    elif direction == "low":
        return "🔴"
    return "⚪"


def get_tehran_now():
    return datetime.now(TEHRAN_TZ)


def get_persian_date():
    import jdatetime
    now = get_tehran_now()
    jalali = jdatetime.datetime.fromgregorian(datetime=now.replace(tzinfo=None))
    months = {
        1: "فروردین", 2: "اردیبهشت", 3: "خرداد",
        4: "تیر", 5: "مرداد", 6: "شهریور",
        7: "مهر", 8: "آبان", 9: "آذر",
        10: "دی", 11: "بهمن", 12: "اسفند",
    }
    return f"{jalali.day} {months[jalali.month]} {jalali.year}"


def get_current_time():
    return get_tehran_now().strftime("%H:%M")


def seconds_until_next_hour():
    now = get_tehran_now()
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return (next_hour - now).total_seconds()


def calculate_gold18_bubble(dollar_price, ounce_price, gold18_market_price):
    if not dollar_price or not ounce_price or not gold18_market_price:
        return None, None
    try:
        intrinsic_value = ((ounce_price * dollar_price) / 31.1035) * (750 / 1000)
        bubble_toman = gold18_market_price - intrinsic_value
        bubble_percent = (bubble_toman / intrinsic_value) * 100
        return bubble_toman, bubble_percent
    except Exception:
        return None, None


async def fetch_complete_market_data():
    """تجمیع داده‌های بازار طلا و ارز با شاخص زنده بورس"""
    data = await asyncio.to_thread(get_market_data)
    if not data:
        data = {}
    bourse_data = await asyncio.to_thread(get_bourse_index)
    if bourse_data:
        data["bourse"] = bourse_data
    return data


# =========================================================
# کیبوردهای ربات
# =========================================================

def get_reply_keyboard():
    keyboard = [
        [KeyboardButton("📊 استعلام قیمت‌ها"), KeyboardButton("📈 استعلام نماد بورس")],
        [KeyboardButton("📰 اخبار بازار و بورس"), KeyboardButton("🧮 ماشین‌حساب طلا")],
        [KeyboardButton("⏰ تنظیم هشدار قیمت"), KeyboardButton("📋 هشدارهای من")],
        [KeyboardButton("📈 تحلیل هوشمند بازار"), KeyboardButton("🔄 شروع مجدد")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 بروزرسانی قیمت‌ها", callback_data="refresh_price"),
            InlineKeyboardButton("📈 استعلام نماد بورس", callback_data="start_tse_search"),
        ],
        [
            InlineKeyboardButton("📰 اخبار بازار و عرضه اولیه", callback_data="news_menu"),
            InlineKeyboardButton("🧮 ماشین‌حساب طلا", callback_data="start_calc"),
        ],
        [
            InlineKeyboardButton("⏰ تنظیم هشدار جدید", callback_data="start_alert"),
            InlineKeyboardButton("📋 هشدارهای فعال من", callback_data="list_my_alerts"),
        ],
        [
            InlineKeyboardButton("📈 تحلیل بازار با هوش مصنوعی", callback_data="run_analysis"),
            InlineKeyboardButton("🤖 راهنمای هوش مصنوعی", callback_data="ai_help"),
        ]
    ])


def get_news_filter_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 اخبار بورس و عرضه اولیه", callback_data="fetchnews_bourse"),
            InlineKeyboardButton("🥇 طلا و سکه", callback_data="fetchnews_gold18"),
        ],
        [
            InlineKeyboardButton("💵 دلار و ارز", callback_data="fetchnews_dollar"),
            InlineKeyboardButton("₿ بیت‌کوین و کریپتو", callback_data="fetchnews_bitcoin"),
        ],
        [
            InlineKeyboardButton("🛢 نفت و انرژی", callback_data="fetchnews_oil"),
            InlineKeyboardButton("🌐 همه اخبار امروز", callback_data="fetchnews_all"),
        ],
        [
            InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")
        ]
    ])


def get_calc_type_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💍 طلای زینتی (همراه با اجرت)", callback_data="calc_type_jewelry")],
        [InlineKeyboardButton("🧱 طلای آب‌شده / شمش (سرمایه‌گذاری)", callback_data="calc_type_melted")],
        [InlineKeyboardButton("❌ انصراف", callback_data="calc_cancel")]
    ])


def get_alert_assets_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🥇 طلای ۱۸", callback_data="alertasset_gold18"),
            InlineKeyboardButton("🪙 سکه امامی", callback_data="alertasset_emami"),
        ],
        [
            InlineKeyboardButton("💵 دلار", callback_data="alertasset_dollar"),
            InlineKeyboardButton("₮ تتر", callback_data="alertasset_tether"),
        ],
        [
            InlineKeyboardButton("🌎 اونس طلا", callback_data="alertasset_ounce"),
            InlineKeyboardButton("₿ بیت‌کوین", callback_data="alertasset_bitcoin"),
        ],
        [InlineKeyboardButton("❌ انصراف", callback_data="alert_cancel")]
    ])


def get_alert_condition_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 بالاتر رفتن از این قیمت (سقف)", callback_data="alertcond_above")],
        [InlineKeyboardButton("📉 پایین‌تر آمدن از این قیمت (کف)", callback_data="alertcond_below")],
        [InlineKeyboardButton("❌ انصراف", callback_data="alert_cancel")]
    ])


# =========================================================
# موتور هوش مصنوعی ناهمگام
# =========================================================

async def ask_gemini(prompt: str) -> str:
    for model_id in AVAILABLE_MODELS:
        try:
            chat_completion = await asyncio.wait_for(
                groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "شما تحلیلگر ارشد بازارهای مالی، بورس تهران، طلا و ارز هستید. "
                                "پاسخ‌ها را کامل، دقیق، شیوا و ساختاریافته به زبان فارسی بنویسید."
                            )
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    model=model_id,
                    temperature=0.3,
                    max_tokens=1500,
                ),
                timeout=18.0
            )
            text = chat_completion.choices[0].message.content
            if text:
                return text.strip()
        except Exception as e:
            print(f"⚠️ تلاش با {model_id} ناموفق بود ({e}). بررسی مدل بعدی...")
            continue

    return ""


# =========================================================
# موتور اختصاصی پایش و اطلاع‌رسانی عرضه‌های اولیه
# =========================================================

async def process_and_alert_ipo(context: ContextTypes.DEFAULT_TYPE, title: str, summary: str):
    """بررسی خبر با هوش مصنوعی جهت تشخیص، استخراج و انتشار مشخصات عرضه اولیه جدید"""
    prompt = f"""
خبر زیر را بررسی کن:
عنوان: {title}
متن: {summary}

آیا این خبر به طور قطعی مربوط به یک «عرضه اولیه جدید» پیش‌رو در بورس یا فرابورس است؟
اگر بله، مشخصات آن را استخراج کن و صرفاً در قالب یک JSON معتبر (بدون هیچ توضیح اضافه و بدون مارک‌داون) به این شکل بازگردان:
{{
    "is_ipo": true,
    "symbol": "نام نماد (مثلا بیوتیک)",
    "company": "نام شرکت",
    "days_left": 2,
    "exact_date": "تاریخ دقیق عرضه (مثلا سه‌شنبه ۲۵ اردیبهشت)",
    "price_range": "سقف قیمت یا دامنه قیمت (مثلا ۱۲,۴۰۰ ریال)",
    "max_shares": "حداکثر سهمیه هر کد (مثلا ۵۰۰ سهم)",
    "estimated_cash": "نقدینگی تخمینی مورد نیاز (مثلا ۶۲۰ هزار تومان)"
}}

اگر خبر تحلیل عمومی است یا مربوط به عرضه اولیه جدیدی نیست:
{{"is_ipo": false}}
"""
    raw_ai = await ask_gemini(prompt)
    if not raw_ai or "{" not in raw_ai:
        return

    try:
        clean_json = raw_ai[raw_ai.find("{"):raw_ai.rfind("}") + 1]
        ipo_data = json.loads(clean_json)

        if ipo_data.get("is_ipo") and ipo_data.get("symbol"):
            symbol = ipo_data.get("symbol")
            company = ipo_data.get("company", symbol)
            exact_date = ipo_data.get("exact_date", "به‌زودی")
            days_left = ipo_data.get("days_left", 2)
            price_range = ipo_data.get("price_range", "اعلام نشده")
            max_shares = ipo_data.get("max_shares", "نامشخص")
            cash = ipo_data.get("estimated_cash", "مشخص نشده")

            is_new = await asyncio.to_thread(
                save_ipo_record, symbol, company, exact_date, price_range, max_shares, cash
            )

            if is_new:
                countdown_text = f"⏳ <b>فقط {days_left} روز مانده تا عرضه!</b>" if days_left and days_left > 0 else "🚨 <b>عرضه اولیه همین هفته!</b>"
                ipo_post = (
                    "🔔📢 <b>اطلاعیه رسمی عرضه اولیه جدید در بورس!</b>\n"
                    f"{countdown_text}\n\n"
                    f"🏢 <b>شرکت:</b> {company}\n"
                    f"📌 <b>نماد معاملاتی:</b> <code>{symbol}</code>\n"
                    f"📅 <b>زمان دقیق عرضه:</b> <b>{exact_date}</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 <b>سقف قیمت:</b> {price_range}\n"
                    f"📦 <b>حداکثر سهمیه هر کد:</b> {max_shares}\n"
                    f"💳 <b>نقدینگی تخمینی مورد نیاز:</b> <b>{cash}</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "💡 <i>لطفاً تا قبل از روز عرضه، حساب کارگزاری خود را شارژ فرمایید.</i>\n\n"
                    f"📢 {CHANNEL_ID}"
                )
                await context.bot.send_message(chat_id=CHANNEL_ID, text=ipo_post, parse_mode="HTML")
                print(f"[{get_current_time()}] 🚀 اطلاعیه عرضه اولیه نماد {symbol} در کانال منتشر شد.")
    except Exception as e:
        print(f"Error parsing IPO JSON: {e}")


# =========================================================
# پایش بلادرنگ اخبار اثرگذار بر سود و زیان بازار
# =========================================================

async def check_and_broadcast_breaking_news(context: ContextTypes.DEFAULT_TYPE):
    """پایش سریع و بلادرنگ رویدادهای سرنوشت‌ساز، سودآور یا زیان‌بار بازار"""
    try:
        latest = await asyncio.to_thread(fetch_latest_news, "all", 10, 36)
        if not latest:
            return

        for item in latest:
            news_id = item["id"]
            if is_news_already_sent(news_id):
                continue

            title = item.get("title", "")
            summary = item.get("summary", "")
            combined_text = f"{title} {summary}".lower()

            # ۱. عرضه‌های اولیه فوری و بدون معطلی منتشر می‌شوند
            if "عرضه اولیه" in combined_text or "عرضه‌اولیه" in combined_text:
                await process_and_alert_ipo(context, title, summary)
                mark_news_as_sent(news_id)
                continue

            # ۲. فیلتر سریع رویدادهای بااهمیت بازار
            is_urgent_keyword = any(k in combined_text for k in BREAKING_KEYWORDS)
            is_bourse_official = item.get("source_name") in ["سنا (بازار سرمایه)", "بورس‌پرس", "بورس‌نیوز", "نبض بورس"]

            if not (is_urgent_keyword or is_bourse_official):
                mark_news_as_sent(news_id)
                continue

            # ۳. ارزیابی فوری اثر سود و زیان خبر توسط AI
            prompt = f"""
رویداد خبری زیر از بازار مخابره شده است:
منبع: {item.get('source_name', '')}
عنوان: {title}
متن: {summary}

آیا این رویداد بر روند قیمت دارایی‌ها (بورس، سهام خاص، دلار، طلا، سکه یا نفت) تاثیر ملموس دارد و باعث سود یا ضرر سهامداران/معامله‌گران می‌شود؟
- اگر خبر خنثی، تکراری یا کم‌اثر است: صرفاً بنویسید IGNORE
- اگر اثرگذار است، دقیقاً با قالب زیر و بدون هیچ مقدمه‌ای بنویسید:

⚡️ <b>{title}</b>

🌐 <b>منبع رسمی:</b> {item.get('source_name', '')}
🎯 <b>دارایی / نماد متاثر:</b> [نام نماد، صنعت یا ارز]
⚖️ <b>برآورد اثر سود و زیان:</b> [🟢 پتانسیل رشد و سودآوری / 🔴 ریسک ریزش و زیان / ⚪ نوسانی و خنثی]
📝 <b>علت و پیامد معاملاتی:</b> [در ۲ جمله روان بگویید چرا این خبر باعث سود یا زیان این دارایی می‌شود]
"""
            res = await ask_gemini(prompt)

            if res and "IGNORE" not in res and len(res) > 30:
                post = (
                    "🚨 <b>فوری | خبر اثرگذار بر قیمت‌ها</b> 🚨\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"{res.strip()}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"🕐 زمان مخابره: <b>{get_current_time()}</b> | 📅 {get_persian_date()}\n"
                    f"📢 {CHANNEL_ID}"
                )
                await context.bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode="HTML")
                print(f"[{get_current_time()}] 📢 خبر اثرگذار در لحظه مخابره شد: {title[:45]}...")

            mark_news_as_sent(news_id)
            await asyncio.sleep(1)

    except Exception as e:
        print(f"Realtime Breaking News Error: {e}")


# =========================================================
# ساخت پیام بازار (نمایش تفکیک‌شده شاخص بورس)
# =========================================================

def build_market_message(data):
    asset_icons = {
        "bourse": "📈", "dollar": "💵", "euro": "💶", "tether": "₮",
        "gold18": "🥇", "gold24": "🥇", "emami": "🪙", "half": "🪙",
        "quarter": "🪙", "ounce": "🌎", "oil": "🛢", "bitcoin": "₿",
    }
    asset_order = [
        "bourse", "dollar", "euro", "tether", "gold18", "gold24",
        "emami", "half", "quarter", "ounce", "oil", "bitcoin",
    ]

    lines = [
        "📊 <b>قیمت لحظه‌ای بازار و بورس</b>",
        f"📅 {get_persian_date()}",
        f"🕐 {get_current_time()}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    dollar_price = data.get("dollar", {}).get("price")
    ounce_price = data.get("ounce", {}).get("price")

    for asset in asset_order:
        item = data.get(asset)
        if not item or item.get("price") is None:
            continue

        name = ASSET_NAMES.get(asset, asset)
        icon = asset_icons.get(asset, "📌")
        price = item.get("price")
        change = item.get("change")
        change_percent = item.get("change_percent")
        direction_emoji = get_direction_emoji(item.get("direction"))

        unit_str = " واحد" if asset == "bourse" else (" دلار" if asset in ["ounce", "oil", "bitcoin"] else " تومان")
        label_val = "مقدار شاخص" if asset == "bourse" else "قیمت"

        lines.append(f"{icon} <b>{name}</b> {direction_emoji}")
        lines.append(f"💰 {label_val}: <b>{format_number(price)}{unit_str}</b>")
        lines.append(f"📈 تغییر: {format_change(change)}")
        lines.append(f"📊 درصد تغییر: {format_percent(change_percent)}")

        if asset == "gold18":
            bubble_toman, bubble_pct = calculate_gold18_bubble(dollar_price, ounce_price, price)
            if bubble_toman is not None:
                bubble_sign = "+" if bubble_toman > 0 else ""
                bubble_emoji = "🫧" if bubble_toman > 0 else "📉"
                lines.append(
                    f"   └ {bubble_emoji} حباب: <b>{bubble_sign}{format_number(bubble_toman)} تومان</b> ({bubble_sign}{bubble_pct:.1f}%)"
                )

        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("📌 <b>آخرین قیمت طلا، ارز، رمزارز و بورس تهران</b>")
    lines.append(f"📢 {CHANNEL_ID}")
    return "\n".join(lines)


def build_gemini_market_data(data):
    lines = [
        "داده‌های لحظه‌ای امروز بازار:",
        f"تاریخ: {get_persian_date()}",
        f"ساعت: {get_current_time()}\n",
    ]
    for asset, item in data.items():
        if not item or item.get("price") is None:
            continue
        name = ASSET_NAMES.get(asset, asset)
        lines.append(
            f"{name}: قیمت/مقدار={item.get('price')}, "
            f"تغییر={item.get('change')}, "
            f"درصد تغییر={item.get('change_percent')}, "
            f"جهت={item.get('direction')}"
        )
    return "\n".join(lines)


async def check_round_level_alert(context: ContextTypes.DEFAULT_TYPE, current_gold_price: float):
    global last_known_gold_price

    if last_known_gold_price is None:
        last_known_gold_price = current_gold_price
        return

    prev_level = int(last_known_gold_price // ROUND_STEP)
    curr_level = int(current_gold_price // ROUND_STEP)

    if curr_level > prev_level:
        crossed_level = curr_level * ROUND_STEP
        alert_msg = (
            f"🚨🔥 <b>فوری / شکست مرز رُند طلا رو به بالا!</b> 🔥🚨\n\n"
            f"⚡️ طلای ۱۸ عیار سقف جدید زد و از کانال <b>{format_number(crossed_level)} تومان</b> عبور کرد!\n\n"
            f"💰 قیمت فعلی: <b>{format_number(current_gold_price)} تومان</b>\n"
            f"📈 وضعیت بازار: <b>صعودی پرقدرت 🟢🚀</b>\n"
            f"🕐 ساعت: {get_current_time()}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 {CHANNEL_ID}"
        )
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=alert_msg, parse_mode="HTML")
        except Exception as e:
            print(f"خطا در ارسال هشدار صعود: {e}")

    elif curr_level < prev_level:
        crossed_level = prev_level * ROUND_STEP
        alert_msg = (
            f"⚠️🩸 <b>فوری / سقوط قیمت طلا به زیر سطح رُند!</b> 🩸⚠️\n\n"
            f"⚡️ طلای ۱۸ عیار به زیر سطح <b>{format_number(crossed_level)} تومان</b> ریزش کرد!\n\n"
            f"💰 قیمت فعلی: <b>{format_number(current_gold_price)} تومان</b>\n"
            f"📉 وضعیت بازار: <b>فشار فروش و نزولی 🔴🔻</b>\n"
            f"🕐 ساعت: {get_current_time()}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 {CHANNEL_ID}"
        )
        try:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=alert_msg, parse_mode="HTML")
        except Exception as e:
            print(f"خطا در ارسال هشدار نزول: {e}")

    last_known_gold_price = current_gold_price


async def check_user_target_alerts(context: ContextTypes.DEFAULT_TYPE, market_data: dict):
    alerts = await asyncio.to_thread(get_active_alerts)
    if not alerts:
        return

    for alert in alerts:
        alert_id, user_id, asset, target_price, condition, created_at = alert
        asset_info = market_data.get(asset)
        if not asset_info or asset_info.get("price") is None:
            continue

        current_price = float(asset_info["price"])
        triggered = False

        if condition == "above" and current_price >= target_price:
            triggered = True
        elif condition == "below" and current_price <= target_price:
            triggered = True

        if triggered:
            await asyncio.to_thread(deactivate_alert, alert_id)
            asset_fa = ASSET_NAMES.get(asset, asset)
            cond_fa = "بالاتر رفتن از" if condition == "above" else "پایین‌تر آمدن از"
            cond_icon = "🟢 🚀" if condition == "above" else "🔴 🔻"

            alert_text = (
                f"🔔 <b>تارگت قیمتی شما فعال شد!</b> {cond_icon}\n\n"
                f"📌 دارایی: <b>{asset_fa}</b>\n"
                f"🎯 هدف تعیین‌شده: <b>{cond_fa} {format_number(target_price)}</b>\n"
                f"💰 قیمت لحظه‌ای فعلی: <b>{format_number(current_price)}</b>\n"
                f"🕐 زمان تحقق: <b>{get_current_time()} ({get_persian_date()})</b>\n\n"
                "✅ <i>این هشدار با موفقیت شلیک و از لیست فعال شما خارج شد.</i>"
            )

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=alert_text,
                    parse_mode="HTML",
                    reply_markup=get_main_keyboard(),
                )
            except Exception as e:
                print(f"خطا در ارسال پیام هشدار به کاربر {user_id}: {e}")


# =========================================================
# بخش استعلام تابلوی نمادهای بورس (ConversationHandler)
# =========================================================

async def start_tse_search_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = (
        "📈 <b>مرکز استعلام و تابلوی زنده بورس تهران</b>\n\n"
        "لطفاً <b>نماد یا نام شرکت</b> مورد نظر خود را تایپ و ارسال کنید:\n"
        "<i>(مثال: فولاد، خودرو، فملی، اهرم، خساپا، فاسمین)</i>"
    )
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="tse_cancel")]])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg_text, reply_markup=cancel_kb, parse_mode="HTML")
    else:
        await update.message.reply_text(msg_text, reply_markup=cancel_kb, parse_mode="HTML")
    return TSE_SYMBOL_SEARCH


async def tse_symbol_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()

    # خروج آنی از جستجوی بورس در صورت فشرده شدن دکمه‌های منوی اصلی
    if query_text in MAIN_MENU_BUTTONS:
        await handle_reply_keyboard_text(update, context)
        return ConversationHandler.END

    wait_msg = await update.message.reply_text(f"⏳ در حال استعلام تابلوی <b>{query_text}</b> از بورس تهران...", parse_mode="HTML")

    data = await asyncio.to_thread(search_and_get_symbol_data, query_text)
    try:
        await wait_msg.delete()
    except Exception:
        pass

    if not data:
        await update.message.reply_text(
            f"❌ نمادی با عنوان «<b>{query_text}</b>» یافت نشد یا ارتباط با سرور بورس با تاخیر مواجه است.\n"
            "لطفاً مجدداً نام نماد را بررسی و ارسال فرمایید یا دکمه انصراف را بزنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="tse_cancel")]]),
            parse_mode="HTML",
        )
        return TSE_SYMBOL_SEARCH

    pct = data["change_pct"]
    icon = "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")
    sign = "+" if pct > 0 else ""

    # فرمت خوانای حجم صف (میلیاردی، میلیونی و عددی)
    q_vol = data.get("queue_volume", 0)
    q_status = data.get("queue_status", "متعادل / بدون صف")
    if q_vol >= 1_000_000_000:
        vol_str_formatted = f"({q_vol / 1_000_000_000:.2f} میلیارد سهم)"
    elif q_vol >= 1_000_000:
        vol_str_formatted = f"({q_vol / 1_000_000:.1f} میلیون سهم)"
    elif q_vol > 0:
        vol_str_formatted = f"({q_vol:,} سهم)"
    else:
        vol_str_formatted = ""

    queue_display = f"<b>{q_status}</b> {vol_str_formatted}".strip()

    # فرمت حجم و ارزش معاملات
    total_vol = data["volume"]
    total_vol_str = f"{total_vol / 1_000_000_000:.2f} میلیارد" if total_vol >= 1_000_000_000 else f"{total_vol:,}"
    val_toman = data["value"] / 10_000_000_000
    val_str = f"{val_toman:,.2f} میلیارد تومان" if val_toman > 0 else "---"

    msg = (
        f"📊 <b>تابلوی معاملاتی نماد {data['symbol']}</b>\n"
        f"🏢 شرکت: <b>{data['name']}</b>\n"
        f"📅 {get_persian_date()} | 🕐 {get_current_time()}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 آخرین معامله: <b>{data['last_price']:,} ریال</b> ({sign}{pct:.2f}% {icon})\n"
        f"📌 قیمت پایانی: <b>{data['close_price']:,} ریال</b>\n"
        f"🔻 نرخ دیروز: {data['yesterday_price']:,} | بازه مجاز: {data['min_day']:,} - {data['max_day']:,}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 حجم معاملات: <b>{total_vol_str}</b> برگ سهم\n"
        f"💳 ارزش معاملات: <b>{val_str}</b>\n"
        f"🔄 تعداد معاملات: <b>{data['trades_count']:,}</b>\n"
        f"⚖️ وضعیت سفارشات: {queue_display}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <a href='https://tsetmc.com/instInfo/{data['ins_code']}'>مشاهده تابلوی کامل در TSETMC</a>\n"
        f"📢 {CHANNEL_ID}"
    )

    tse_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 استعلام نماد دیگر", callback_data="start_tse_search"),
            InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main"),
        ]
    ])

    await update.message.reply_text(msg, reply_markup=tse_keyboard, parse_mode="HTML", disable_web_page_preview=True)
    return ConversationHandler.END


async def tse_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ جستجوی نماد لغو شد.", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("❌ جستجوی نماد لغو شد.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


# =========================================================
# جاب‌های زمان‌بندی‌شده
# =========================================================

async def send_hourly_market_price(context: ContextTypes.DEFAULT_TYPE):
    try:
        data = await fetch_complete_market_data()
        if not data:
            return

        await asyncio.to_thread(save_market_snapshot, data)

        gold18_price = data.get("gold18", {}).get("price")
        if gold18_price:
            await check_round_level_alert(context, gold18_price)

        await check_user_target_alerts(context, data)

        date_str = get_persian_date()
        time_str = get_current_time()
        message = build_market_message(data)

        try:
            image_stream = await asyncio.to_thread(generate_market_card, data, date_str, time_str)
            await context.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=image_stream,
                caption=message,
                parse_mode="HTML",
            )
        except Exception as img_err:
            print(f"ارسال تصویر ناموفق بود ({img_err})؛ پیام متنی ارسال می‌شود.")
            await context.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="HTML")

        print(f"[{get_current_time()}] ✅ ارسال ساعتی همراه با شاخص بورس انجام شد.")
    except Exception as e:
        print(f"[{get_current_time()}] ❌ خطا در ارسال ساعتی: {e}")


async def daily_ipo_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """یادآوری خودکار روزشمار برای عرضه‌های اولیه‌ای که به روز عرضه نزدیک می‌شوند"""
    try:
        ipos = await asyncio.to_thread(get_upcoming_ipos)
        for ipo in ipos:
            rec_id, symbol, company, ipo_date, p_range, max_s, cash, notified = ipo

            prompt = f"""
تاریخ امروز: {get_persian_date()}
تاریخ عرضه نماد {symbol}: {ipo_date}

آیا موعد عرضه هنوز فرا نرسیده است؟ دقیقاً چند روز تا روز عرضه باقی مانده است؟
صرفاً یک عدد صحیح برگردان (مثلاً 2 یا 1 یا 0 اگر همین امروز است، یا -1 اگر تاریخ گذشته است):
"""
            ans = await ask_gemini(prompt)
            try:
                days = int("".join(filter(lambda x: x.isdigit() or x == "-", ans)))
                day_tag = f"day_{days}"

                if days in [0, 1, 2, 3] and day_tag not in notified:
                    if days == 0:
                        tag_fa = "🚨 امروز موعد عرضه اولیه است!"
                    elif days == 1:
                        tag_fa = "⏳ فردا عرضه اولیه داریم!"
                    else:
                        tag_fa = f"⏳ فقط {days} روز مانده به عرضه اولیه!"

                    reminder_msg = (
                        f"🔔 <b>{tag_fa}</b>\n\n"
                        f"🏢 شرکت: <b>{company}</b>\n"
                        f"📌 نماد: <code>{symbol}</code>\n"
                        f"📅 تاریخ عرضه: <b>{ipo_date}</b>\n"
                        f"💰 سقف قیمت: {p_range}\n"
                        f"📦 حداکثر سهمیه: {max_s}\n"
                        f"💳 نقدینگی تخمینی: <b>{cash}</b>\n\n"
                        "⚠️ <i>لطفاً نسبت به بررسی مانده و شارژ حساب کارگزاری خود اقدام فرمایید.</i>\n\n"
                        f"📢 {CHANNEL_ID}"
                    )
                    await context.bot.send_message(chat_id=CHANNEL_ID, text=reminder_msg, parse_mode="HTML")
                    await asyncio.to_thread(update_ipo_notification, rec_id, day_tag)
                    print(f"[{get_current_time()}] ⏰ یادآوری عرضه اولیه {symbol} ارسال شد.")
            except Exception:
                continue
    except Exception as e:
        print(f"IPO Reminder Error: {e}")


async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """تولید گزارش جامع شبانه با قالب ساختاریافته و تحلیل عمیق بازار"""
    try:
        today_str = get_tehran_now().strftime("%Y-%m-%d")
        summary = await asyncio.to_thread(get_daily_summary, today_str)

        if not summary or summary.get("snapshot_count", 0) == 0:
            return

        asset_performances = []
        for asset_key, metrics in summary["assets"].items():
            if metrics["start"] is not None and metrics["change_percent"] is not None:
                fa_name = ASSET_NAMES.get(asset_key, asset_key)
                asset_performances.append({
                    "key": asset_key,
                    "name": fa_name,
                    "return": metrics["change_percent"],
                    "start": metrics["start"],
                    "end": metrics["end"],
                })

        asset_performances.sort(key=lambda x: x["return"], reverse=True)
        winner = asset_performances[0] if asset_performances else None

        poll_eval_text = ""
        last_poll = await asyncio.to_thread(get_last_active_poll)
        if last_poll and winner:
            rec_id, poll_id, msg_id, chat_id, p_date = last_poll
            try:
                stopped_poll = await context.bot.stop_poll(chat_id=chat_id, message_id=msg_id)
                await asyncio.to_thread(close_poll_record, rec_id)

                options = stopped_poll.options
                top_voted_option = max(options, key=lambda o: o.voter_count)
                total_votes = stopped_poll.total_voter_count

                if total_votes > 0:
                    pct = (top_voted_option.voter_count / total_votes) * 100
                    user_pick = top_voted_option.text

                    if winner["name"] in user_pick or any(w in user_pick for w in winner["name"].split()):
                        poll_eval_text = (
                            f"🎯 <b>پیش‌بینی کاربران درست بود!</b>\n"
                            f"🔹 {pct:.0f}٪ از اعضا به‌درستی پیش‌بینی کرده بودند که <b>{winner['name']}</b> بیشترین بازدهی را ثبت خواهد کرد."
                        )
                    else:
                        poll_eval_text = (
                            f"⚠️ <b>غافلگیری بازار نسبت به پیش‌بینی کاربران!</b>\n"
                            f"🔹 در نظرسنجی دیشب بیشترین آرا ({pct:.0f}٪) به <b>{user_pick}</b> اختصاص داشت؛ اما <b>{winner['name']}</b> با بازدهی <b>{winner['return']:+.2f}%</b> پیشتاز معاملات شد."
                        )
            except Exception as e:
                print(f"خطا در ارزیابی نظرسنجی: {e}")

        today_news = await asyncio.to_thread(fetch_latest_news, "all", 8, 36)
        news_summary_prompt = "\n".join([f"- [{n.get('source_name')}] {n['title']}: {n['summary'][:120]}" for n in today_news]) if today_news else "خبر عمده‌ای ثبت نشد."

        data_digest = "\n".join([f"• {a['name']}: {a['return']:+.2f}% (پایانی: {format_number(a['end'])})" for a in asset_performances])

        prompt = f"""
شما تحلیلگر ارشد بازارهای مالی و بورس تهران هستید.
کارنامه عملکرد معاملات امروز:
{data_digest}

گزیده اخبار روز:
{news_summary_prompt}

متن گزارش پایانی را دقیقاً در قالب این ۳ بخش مشخص با تگ‌های تمیز HTML بنویسید (بدون هیچ مقدمه یا سلام):

📌 <b>دیده‌بان و ارزیابی تحولات روز:</b>
• <b>بورس تهران:</b> (در ۲ جمله: رفتار شاخص کل، ارزش معاملات و نمادهای پیشران)
• <b>طلا و مسکوکات:</b> (در ۲ جمله: وضعیت حباب و همبستگی با انس جهانی و دلار)
• <b>بازار ارز و تتر:</b> (در ۱ الی ۲ جمله: فشار عرضه/تقاضا و اثر نیما)
• <b>بازارهای جهانی و نفت:</b> (در ۱ جمله: وضعیت نفت برنت و رمزارزها)

🔮 <b>سطوح حساس و چشم‌انداز ۲۴ ساعت آینده:</b>
• <b>شاخص کل بورس:</b> (مهم‌ترین سطح حمایتی/مقاومتی مورد انتظار فردا)
• <b>طلای ۱۸ و سکه:</b> (کانال حساس قیمت و رفتار خریداران)
• <b>دلار آزاد:</b> (محدوده نوسان کلیدی فردا)

💡 <b>جمع‌بندی تحلیلی برای فعالان بازار:</b>
(یک بند تحلیلی ۳۰ کلمه‌ای درباره ریسک‌ها و فرصت‌های معاملاتی روز کاری بعد)
"""
        ai_analysis = await ask_gemini(prompt)

        performance_lines = "\n".join([
            f"{'🟢' if a['return'] >= 0 else '🔴'} <b>{a['name']}:</b> <code>{a['return']:+.2f}%</code> | {format_number(a['end'])}"
            for a in asset_performances
        ])

        report_message = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 <b>پرونده تحلیلی و کارنامه جامع بازار</b>\n"
            f"📅 تاریخ: <b>{get_persian_date()}</b> | ساعت ۲۳:۵۸\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
        )
        if poll_eval_text:
            report_message += f"{poll_eval_text}\n━━━━━━━━━━━━━━━━━━━━\n"

        report_message += (
            "📈 <b>کارنامه رسمی بازدهی دارایی‌ها:</b>\n\n"
            f"{performance_lines}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        if ai_analysis:
            report_message += f"{ai_analysis}\n\n━━━━━━━━━━━━━━━━━━━━\n"

        report_message += f"📢 {CHANNEL_ID}"

        for i in range(0, len(report_message), 4000):
            await context.bot.send_message(chat_id=CHANNEL_ID, text=report_message[i:i + 4000], parse_mode="HTML")

        # نظرسنجی ۲۴ ساعته روزانه
        poll_question = f"🗳 پیش‌بینی بازار ({get_persian_date()}):\nبه نظر شما کدام دارایی تا ۲۴ ساعت آینده بیشترین بازدهی را خواهد داشت؟"
        poll_options = [
            "📈 شاخص کل بورس تهران",
            "🥇 طلای ۱۸ عیار / سکه",
            "💵 دلار بازار آزاد",
            "₮ تتر (USDT)",
            "₿ بیت‌کوین (BTC)",
            "⚪ بازار بدون نوسان خاص (رِنج)",
        ]

        poll_msg = await context.bot.send_poll(
            chat_id=CHANNEL_ID,
            question=poll_question,
            options=poll_options,
            is_anonymous=True,
            allows_multiple_answers=False,
        )

        await asyncio.to_thread(
            save_daily_poll,
            poll_msg.poll.id,
            poll_msg.message_id,
            CHANNEL_ID,
            today_str,
        )

        print(f"[{get_current_time()}] ✅ گزارش جامع و نظرسنجی ۲۴ ساعته ارسال شد.")

    except Exception as e:
        print(f"[{get_current_time()}] ❌ خطا در ارسال پرونده شبانه: {e}")


# =========================================================
# فرآیند نمایش و فیلتر اخبار
# =========================================================

async def show_news_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📰 <b>مرکز پایش اخبار اقتصادی، بورس، کدال و عرضه‌های اولیه</b>\n\n"
        "لطفاً حوزه خبری مورد نظر خود را انتخاب کنید:"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=get_news_filter_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=get_news_filter_keyboard(), parse_mode="HTML")


async def fetch_news_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    asset_key = query.data.replace("fetchnews_", "")
    asset_fa = ASSET_NAMES.get(asset_key, "همه بازارها")

    await query.edit_message_text(f"⏳ در حال استخراج تازه‌ترین اخبار <b>{asset_fa}</b>...", parse_mode="HTML")

    news_items = await asyncio.to_thread(fetch_latest_news, asset_key, 6, 36)

    if not news_items:
        await query.message.reply_text(
            f"❌ خبری در حال حاضر برای {asset_fa} یافت نشد.",
            reply_markup=get_news_filter_keyboard(),
        )
        return

    if "cached_news" not in context.user_data:
        context.user_data["cached_news"] = {}

    await query.message.reply_text(
        f"📋 <b>تازه‌ترین اخبار تاثیرگذار بر {asset_fa}:</b>",
        parse_mode="HTML",
    )

    for idx, item in enumerate(news_items, 1):
        news_ref_id = f"n_{hash(item['title']) % 1000000}"
        context.user_data["cached_news"][news_ref_id] = item

        item_asset_fa = ASSET_NAMES.get(item["asset"], "بازارهای مالی")
        source_badge = "🇮🇷 داخلی" if item.get("source_type") == "داخلی" else "🌎 بین‌المللی"

        news_text = (
            f"<b>{idx}. {item['title']}</b>\n\n"
            f"📌 منبع: <b>{source_badge} ({item.get('source_name', '')})</b> | حوزه: <b>{item_asset_fa}</b>\n"
            f"📝 خلاصه خبر: <i>{item['summary']}</i>"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🤖 تحلیل اثر بر سهم و بازار", callback_data=f"ai_trans_{news_ref_id}"),
                InlineKeyboardButton("🔗 منبع خبر", url=item["link"]),
            ]
        ])

        await query.message.reply_text(news_text, reply_markup=keyboard, parse_mode="HTML")


async def ai_translate_news_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحلیل بنیادی و حرفه‌ای خبر، صنایع تحت تأثیر و پیامد آن بر آینده قیمت سهم و دارایی‌ها"""
    query = update.callback_query
    await query.answer()

    news_ref_id = query.data.replace("ai_trans_", "")
    item = context.user_data.get("cached_news", {}).get(news_ref_id)

    if not item:
        await query.message.reply_text("❌ متن خبر منقضی شده است. مجدداً از منو خبر را انتخاب کنید.")
        return

    wait_msg = await query.message.reply_text("🤖 در حال تحلیل بنیادی و ارزیابی اثر این رویداد بر آینده سهام و دارایی‌ها...")

    prompt = f"""
شما تحلیلگر ارشد بازار سرمایه ایران و بازارهای مالی هستید. رویداد خبری زیر را بررسی و تحلیل کنید:
منبع خبر: {item.get('source_name', '')}
عنوان خبر: {item['title']}
متن خلاصه: {item['summary']}

پاسخ را دقیقاً در قالب این ۳ بخش مشخص و بدون مقدمه اضافی ارائه دهید:

📌 <b>مفهوم و خلاصه رویداد:</b>
(در ۱ الی ۲ جمله روان و ساده توضیح دهید اصل اتفاق چه بوده است)

🎯 <b>صنایع، شرکت‌ها و نمادهای تحت تاثیر:</b>
(دقیقاً نام ببرید کدام شرکت‌ها، نمادها، یا کدام دارایی مثل دلار/طلا متاثر می‌شوند)

📊 <b>تحلیل اثر و چشم‌انداز آینده سهم/دارایی:</b>
(توضیح دهید اثر این خبر بر سودآوری، عرضه و تقاضا، یا جریان پولی مثبت است یا منفی؟ سیگنال نهایی: صعودی 🟢 / نزولی 🔴 / خنثی ⚪)
"""
    answer = await ask_gemini(prompt)

    try:
        await wait_msg.delete()
    except Exception:
        pass

    if not answer:
        answer = "⚠️ در حال حاضر امکان تحلیل خودکار این خبر مقدور نمی‌باشد."

    final_text = (
        "🤖 <b>تحلیل بنیادی و ارزیابی اثرگذاری خبر:</b>\n\n"
        f"{answer}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 {CHANNEL_ID}"
    )
    await query.message.reply_text(final_text, parse_mode="HTML")


# =========================================================
# ثبت هشدار شخصی قیمت (ConversationHandler)
# =========================================================

async def start_alert_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⏰ <b>تنظیم هشدار اختصاصی قیمت (Target Price)</b>\n\n"
        "👇 لطفاً <b>دارایی مورد نظر</b> خود را انتخاب کنید:"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=get_alert_assets_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(text=text, reply_markup=get_alert_assets_keyboard(), parse_mode="HTML")
    return ALERT_ASSET


async def alert_asset_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "alert_cancel":
        await query.edit_message_text("❌ تنظیم هشدار لغو گردید.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    asset_key = query.data.replace("alertasset_", "")
    context.user_data["alert_asset"] = asset_key
    asset_fa = ASSET_NAMES.get(asset_key, asset_key)

    await query.edit_message_text(
        f"دارایی انتخاب‌شده: <b>{asset_fa}</b>\n\n"
        "🎯 تمایل دارید در چه حالتی به شما هشدار داده شود؟",
        reply_markup=get_alert_condition_keyboard(),
        parse_mode="HTML",
    )
    return ALERT_CONDITION


async def alert_condition_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "alert_cancel":
        await query.edit_message_text("❌ تنظیم هشدار لغو گردید.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    condition = query.data.replace("alertcond_", "")
    context.user_data["alert_condition"] = condition

    asset_key = context.user_data.get("alert_asset")
    asset_fa = ASSET_NAMES.get(asset_key, asset_key)
    cond_text = "بالاتر رفتن از" if condition == "above" else "پایین‌تر آمدن از"

    data = await fetch_complete_market_data()
    current_price = data.get(asset_key, {}).get("price")
    curr_str = f"{format_number(current_price)}" if current_price else "---"

    await query.edit_message_text(
        f"📌 دارایی: <b>{asset_fa}</b>\n"
        f"شرط: <b>{cond_text}</b>\n"
        f"💰 قیمت لحظه‌ای فعلی: <b>{curr_str}</b>\n\n"
        "🔢 لطفاً <b>قیمت هدف (تارگت)</b> خود را به صورت عدد تایپ و ارسال فرمایید:\n"
        "(مثال: <code>24000000</code> یا <code>95000</code>)",
        parse_mode="HTML",
    )
    return ALERT_PRICE


async def alert_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text.replace(",", "").replace("،", "").replace(" ", "").strip()
    try:
        target_price = float(msg_text)
        if target_price <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text(
            "⚠️ لطفاً قیمت هدف را به صورت یک عدد معتبر بزرگتر از صفر ارسال کنید (مثال: <code>24500000</code>):",
            parse_mode="HTML",
        )
        return ALERT_PRICE

    user_id = update.effective_user.id
    asset_key = context.user_data.get("alert_asset")
    condition = context.user_data.get("alert_condition")

    await asyncio.to_thread(add_user_alert, user_id, asset_key, target_price, condition)

    asset_fa = ASSET_NAMES.get(asset_key, asset_key)
    cond_fa = "بالاتر رفتن از" if condition == "above" else "پایین‌تر آمدن از"

    success_msg = (
        "✅ <b>هشدار شما با موفقیت ذخیره و فعال شد!</b>\n\n"
        f"📌 دارایی: <b>{asset_fa}</b>\n"
        f"🎯 شرط اخطار: <b>{cond_fa} {format_number(target_price)}</b>\n\n"
        "⚡️ به محض اینکه قیمت بازار به این عدد برسد، فوراً پیام دریافت خواهید کرد."
    )

    context.user_data.clear()
    await update.message.reply_text(success_msg, reply_markup=get_main_keyboard(), parse_mode="HTML")
    return ConversationHandler.END


async def alert_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ تنظیم هشدار لغو گردید.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


async def show_my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    alerts = await asyncio.to_thread(get_user_alerts, user_id)

    if not alerts:
        msg = "📭 شما در حال حاضر هیچ هشدار قیمت فعالی ندارید."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏰ ثبت هشدار جدید", callback_data="start_alert")]
        ])
    else:
        msg = "📋 <b>لیست هشدارهای فعال شما:</b>\n\n"
        buttons = []
        for a in alerts:
            aid, asset, target, cond, ctime = a
            afa = ASSET_NAMES.get(asset, asset)
            cfa = "بالای" if cond == "above" else "زیر"
            msg += f"• <b>{afa}</b>: {cfa} <code>{format_number(target)}</code> (ثبت: {ctime})\n"
            buttons.append([InlineKeyboardButton(f"🗑 حذف هشدار {afa} ({format_number(target)})", callback_data=f"delalert_{aid}")])

        buttons.append([InlineKeyboardButton("➕ افزودن هشدار جدید", callback_data="start_alert")])
        keyboard = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(msg, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await context.bot.send_message(chat_id=user_id, text=msg, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, reply_markup=keyboard, parse_mode="HTML")


async def delete_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    alert_id = int(query.data.replace("delalert_", ""))
    user_id = update.effective_user.id

    await asyncio.to_thread(delete_user_alert, alert_id, user_id)
    await query.message.reply_text("🗑 هشدار مورد نظر با موفقیت حذف گردید.")
    await show_my_alerts(update, context)


# =========================================================
# ماشین‌حساب طلا (ConversationHandler)
# =========================================================

async def start_calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🧮 <b>ماشین‌حساب هوشمند محاسبه فاکتور طلا</b>\n\n"
        "لطفاً نوع خرید خود را انتخاب کنید:\n\n"
        "💍 <b>طلای زینتی:</b> همراه با اجرت ساخت، ۷٪ سود طلافروش و ۱۰٪ مالیات بر اجرت/سود\n"
        "🧱 <b>طلای آب‌شده / شمش:</b> با عیار ۷۵۰ (بدون اجرت و مالیات، صرفاً با ۱٪ سود فروش)"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=get_calc_type_keyboard(), parse_mode="HTML")
    else:
        await update.message.reply_text(text=text, reply_markup=get_calc_type_keyboard(), parse_mode="HTML")
    return CALC_TYPE


async def calc_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "calc_cancel":
        await query.edit_message_text("❌ عملیات محاسبه لغو شد.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    gold_type = "jewelry" if query.data == "calc_type_jewelry" else "melted"
    context.user_data["calc_gold_type"] = gold_type

    type_title = "طلای زینتی" if gold_type == "jewelry" else "طلای آب‌شده / شمش"
    await query.edit_message_text(
        f"📌 شما <b>{type_title}</b> را انتخاب کردید.\n\n"
        "⚖️ لطفاً <b>وزن طلا به گرم</b> را ارسال کنید (مثال: <code>4.25</code> یا <code>10</code>):",
        parse_mode="HTML",
    )
    return CALC_WEIGHT


async def calc_weight_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text.replace("،", ".").replace(" ", "").strip()
    try:
        weight = float(msg_text)
        if weight <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("⚠️ لطفاً وزن را به‌صورت یک عدد معتبر بزرگتر از صفر وارد کنید (مثال: <code>5.5</code>):", parse_mode="HTML")
        return CALC_WEIGHT

    context.user_data["calc_weight"] = weight
    gold_type = context.user_data.get("calc_gold_type")

    if gold_type == "melted":
        return await finalize_gold_calculation(update, context, wage_percent=0.0)

    await update.message.reply_text(
        f"✅ وزن ثبت شد: <b>{weight} گرم</b>\n\n"
        "🔨 حالا لطفاً <b>درصد اجرت ساخت طلا</b> را بفرستید (مثال: برای ۱۵ درصد عدد <code>15</code> را بنویسید):",
        parse_mode="HTML",
    )
    return CALC_WAGE


async def calc_wage_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text.replace("%", "").replace("،", ".").replace(" ", "").strip()
    try:
        wage = float(msg_text)
        if wage < 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("⚠️ لطفاً درصد اجرت را به‌صورت یک عدد صحیح یا اعشاری وارد کنید (مثال: <code>18</code>):", parse_mode="HTML")
        return CALC_WAGE

    return await finalize_gold_calculation(update, context, wage_percent=wage)


async def finalize_gold_calculation(update: Update, context: ContextTypes.DEFAULT_TYPE, wage_percent: float):
    weight = context.user_data.get("calc_weight", 0)
    gold_type = context.user_data.get("calc_gold_type")

    data = await asyncio.to_thread(get_market_data)
    gold18_price = data.get("gold18", {}).get("price")

    if not gold18_price:
        await update.message.reply_text("❌ خطا در استعلام نرخ لحظه‌ای طلای ۱۸ عیار از تابلو. لطفاً مجدداً امتحان کنید.")
        return ConversationHandler.END

    raw_gold_price = weight * gold18_price

    if gold_type == "jewelry":
        wage_amount = raw_gold_price * (wage_percent / 100)
        seller_profit = (raw_gold_price + wage_amount) * 0.07
        tax_amount = (wage_amount + seller_profit) * 0.10
        total_price = raw_gold_price + wage_amount + seller_profit + tax_amount

        invoice = (
            "🧾 <b>فاکتور رسمی خرید طلای زینتی (۱۸ عیار)</b>\n"
            f"📅 تاریخ: {get_persian_date()} | 🕐 ساعت: {get_current_time()}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🥇 نرخ تابلو طلای ۱۸ عیار: <b>{format_number(gold18_price)} تومان</b>\n"
            f"⚖️ وزن طلای خریداری‌شده: <b>{weight:,.3f} گرم</b>\n"
            f"💰 قیمت طلای خام: <b>{format_number(raw_gold_price)} تومان</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🔨 اجرت ساخت ({wage_percent}%): <b>{format_number(wage_amount)} تومان</b>\n"
            f"🏪 سود فروشنده (۷٪): <b>{format_number(seller_profit)} تومان</b>\n"
            f"🏛 مالیات بر ارزش افزوده (۱۰٪ روی اجرت و سود): <b>{format_number(tax_amount)} تومان</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 <b>مبلغ نهایی و تمام‌شده فاکتور:</b>\n"
            f"👉 <b>{format_number(total_price)} تومان</b>\n\n"
            f"💡 <i>قیمت تمام‌شده هر گرم برای شما: {format_number(total_price / weight)} تومان</i>"
        )
    else:
        seller_profit = raw_gold_price * 0.01
        total_price = raw_gold_price + seller_profit

        invoice = (
            "🧾 <b>فاکتور خرید طلای آب‌شده / شمش (سرمایه‌گذاری)</b>\n"
            f"📅 تاریخ: {get_persian_date()} | 🕐 ساعت: {get_current_time()}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🥇 نرخ تابلو طلای ۱۸ عیار: <b>{format_number(gold18_price)} تومان</b>\n"
            f"⚖️ وزن: <b>{weight:,.3f} گرم</b>\n"
            f"💰 ارزش طلای خام: <b>{format_number(raw_gold_price)} تومان</b>\n"
            f"🏪 سود و کارمزد معامله (۱٪): <b>{format_number(seller_profit)} تومان</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 <b>مبلغ نهایی قابل پرداخت:</b>\n"
            f"👉 <b>{format_number(total_price)} تومان</b>\n\n"
            "✅ <i>خرید آب‌شده معاف از اجرت ساخت و مالیات است.</i>"
        )

    await update.message.reply_text(invoice, reply_markup=get_main_keyboard(), parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END


async def calc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ عملیات محاسبه لغو شد.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


# =========================================================
# دستورات عمومی و تحلیل زنده بازار (داشبورد هوشمند)
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    await update.message.reply_text(
        "👋 <b>درود! به ربات هوشمند Azar Market خوش آمدید.</b>\n\n"
        "قابلیت‌ها:\n"
        "• نرخ زنده ارز، طلا، سکه، نفت و کریپتو همراه با پوستر تصویری\n"
        "• استعلام آنلاین تابلوی نمادهای بورس و شاخص کل\n"
        "• مرکز اخبار بازارها، کدال و عرضه‌های اولیه\n"
        "• ماشین‌حساب فاکتور رسمی طلا و طلای آب‌شده\n"
        "• سیستم هشدار شخصی قیمت (Target Alert)\n"
        "• تحلیل هوشمند تحولات بازار با هوش مصنوعی\n\n"
        "از دکمه‌های زیر استفاده فرمایید:",
        reply_markup=get_reply_keyboard(),
        parse_mode="HTML",
    )
    await update.message.reply_text("منوی عملیات سریع:", reply_markup=get_main_keyboard())


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    data = await fetch_complete_market_data()
    if not data:
        await update.message.reply_text("❌ خطا در استعلام قیمت‌ها.")
        return

    date_str = get_persian_date()
    time_str = get_current_time()
    caption_text = build_market_message(data)

    try:
        image_stream = await asyncio.to_thread(generate_market_card, data, date_str, time_str)
        await update.message.reply_photo(
            photo=image_stream,
            caption=caption_text,
            reply_markup=get_main_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"ارسال تصویر ناموفق بود: {e}")
        await update.message.reply_text(caption_text, reply_markup=get_main_keyboard(), parse_mode="HTML")


async def analysis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحلیل ساختاریافته داشبوردی برای کاربر در پی‌وی"""
    if not update.message:
        return

    wait_msg = await update.message.reply_text("📊 در حال تجمیع داده‌ها و نگارش داشبورد تحلیل هوشمند بازار...")
    try:
        data = await fetch_complete_market_data()
        if not data:
            await wait_msg.delete()
            await update.message.reply_text("❌ خطا در دریافت اطلاعات.")
            return

        market_text = build_gemini_market_data(data)
        prompt = f"""
داده‌های لحظه‌ای تابلوی بازار:
{market_text}

شما تحلیلگر ارشد بازارهای مالی هستید. این داده‌ها را به شکل یک داشبورد معاملاتی حرفه‌ای و تمیز با تگ‌های HTML قالب‌بندی کن (هیچ مقدمه یا سلام ننویس):

🧭 <b>نبض لحظه‌ای و اتمسفر بازار:</b>
(یک جمله روان و شفاف از کلیت جو حاکم بر بازارها)

📊 <b>تفکیک وضعیت بازارها:</b>
🔹 <b>بورس تهران:</b> (بررسی جریان معاملات و کشش نمادها در ۱ جمله)
🔹 <b>طلا و مسکوکات:</b> (وضعیت تقاضا و حباب در ۱ جمله)
🔹 <b>دلار و ارز:</b> (محدوده نوسان و فشار بازارساز در ۱ جمله)
🔹 <b>کریپتو و نفت:</b> (سیگنال‌های بازار جهانی در ۱ جمله)

⚖️ <b>جهت جریان نقدینگی (Smart Money):</b>
(نقدینگی هوشمند در حال حاضر بیشتر به کدام سمت جذب می‌شود؟ طلا، بورس، صندوق‌های درآمد ثابت یا ارز؟)

🎯 <b>رویکرد مدیریت ریسک:</b>
(یک توصیه معاملاتی محتاطانه بدون پیشنهاد مستقیم خرید/فروش)
"""
        analysis = await ask_gemini(prompt)
        await wait_msg.delete()

        if not analysis:
            analysis = "⚠️ در حال حاضر امکان انجام تحلیل وجود ندارد. لطفاً دقایقی دیگر مجدداً تلاش فرمایید."

        final_reply = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 <b>داشبورد تحلیل هوشمند بازار</b>\n"
            f"📅 {get_persian_date()} | 🕐 {get_current_time()}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{analysis}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <i>این تحلیل صرفاً جنبه بررسی داده‌ها را دارد و پیشنهاد خرید یا فروش نیست.</i>"
        )

        for i in range(0, len(final_reply), 4000):
            await update.message.reply_text(final_reply[i:i + 4000], reply_markup=get_main_keyboard(), parse_mode="HTML")

    except Exception as e:
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ خطا در پردازش تحلیل: {e}")


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پاسخ ساخت‌یافته و گلوله‌ای به پرسش‌های آزاد کاربران"""
    if not update.message:
        return

    if not context.args:
        await update.message.reply_text(
            "لطفاً سوال خود را بنویسید:\nمثال:\n<code>/ai تاثیر نرخ بهره آمریکا بر طلا چیست؟</code>",
            parse_mode="HTML",
        )
        return

    question = " ".join(context.args)
    wait_msg = await update.message.reply_text("🤖 در حال نگارش پاسخ تحلیلی...")

    prompt = f"""
سوال کاربر: {question}

دستورالعمل نگارش:
- کاملاً ساختاریافته، دقیق و خوانا به فارسی بنویس.
- از پاراگراف‌های طولانی و خسته‌کننده دوری کن و نکات کلیدی را با بولت‌پوینت (•) مشخص کن.
- پاسخ نهایتاً در ۲ الی ۳ بند مفید باشد و حتماً با تگ‌های ساده HTML مثل <b>bold</b> فرمت شود.
"""
    try:
        answer = await ask_gemini(prompt)
        await wait_msg.delete()
        if not answer:
            answer = "⚠️ در حال حاضر ارتباط با سرور هوش مصنوعی برقرار نشد."

        formatted_answer = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💬 <b>پاسخ تحلیلی هوش مصنوعی:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{answer}\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        for i in range(0, len(formatted_answer), 4000):
            await update.message.reply_text(formatted_answer[i:i + 4000], parse_mode="HTML")
    except Exception as e:
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ خطا: {e}")


async def handle_reply_keyboard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📊 استعلام قیمت‌ها":
        await price_command(update, context)
    elif text == "📈 استعلام نماد بورس":
        await start_tse_search_flow(update, context)
    elif text == "🧮 ماشین‌حساب طلا":
        await start_calc_command(update, context)
    elif text == "📰 اخبار بازار و بورس":
        await show_news_menu(update, context)
    elif text == "⏰ تنظیم هشدار قیمت":
        await start_alert_flow(update, context)
    elif text == "📋 هشدارهای من":
        await show_my_alerts(update, context)
    elif text == "📈 تحلیل هوشمند بازار":
        await analysis_command(update, context)
    elif text == "🔄 شروع مجدد":
        await start(update, context)


# =========================================================
# پردازش دکمه‌های شیشه‌ای
# =========================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    data_payload = query.data

    if data_payload == "refresh_price":
        try:
            await query.answer("در حال دریافت جدیدترین نرخ‌ها و تولید کارت...")
        except Exception:
            pass
        data = await fetch_complete_market_data()
        if data:
            date_str = get_persian_date()
            time_str = get_current_time()
            caption_text = build_market_message(data)
            try:
                image_stream = await asyncio.to_thread(generate_market_card, data, date_str, time_str)
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=image_stream,
                    caption=caption_text,
                    reply_markup=get_main_keyboard(),
                    parse_mode="HTML",
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=caption_text,
                    reply_markup=get_main_keyboard(),
                    parse_mode="HTML",
                )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ دریافت نرخ‌ها موفق نبود.",
                reply_markup=get_main_keyboard(),
            )

    elif data_payload == "run_analysis":
        try:
            await query.edit_message_text("⏳ در حال تجمیع داده‌ها و نگارش داشبورد تحلیل هوشمند بازار...")
        except Exception:
            pass
        data = await fetch_complete_market_data()
        if data:
            market_text = build_gemini_market_data(data)
            prompt = f"""
داده‌های لحظه‌ای تابلوی بازار:
{market_text}

شما تحلیلگر ارشد بازارهای مالی هستید. این داده‌ها را به شکل یک داشبورد معاملاتی حرفه‌ای و تمیز با تگ‌های HTML قالب‌بندی کن (هیچ مقدمه یا سلام ننویس):

🧭 <b>نبض لحظه‌ای و اتمسفر بازار:</b>
(یک جمله روان و شفاف از کلیت جو حاکم بر بازارها)

📊 <b>تفکیک وضعیت بازارها:</b>
🔹 <b>بورس تهران:</b> (بررسی جریان معاملات و کشش نمادها در ۱ جمله)
🔹 <b>طلا و مسکوکات:</b> (وضعیت تقاضا و حباب در ۱ جمله)
🔹 <b>دلار و ارز:</b> (محدوده نوسان و فشار بازارساز در ۱ جمله)
🔹 <b>کریپتو و نفت:</b> (سیگنال‌های بازار جهانی در ۱ جمله)

⚖️ <b>جهت جریان نقدینگی (Smart Money):</b>
(نقدینگی هوشمند در حال حاضر بیشتر به کدام سمت جذب می‌شود؟ طلا، بورس، صندوق‌های درآمد ثابت یا ارز؟)

🎯 <b>رویکرد مدیریت ریسک:</b>
(یک توصیه معاملاتی محتاطانه بدون پیشنهاد مستقیم خرید/فروش)
"""
            analysis = await ask_gemini(prompt)
            if not analysis:
                analysis = "⚠️ در حال حاضر ارتباط با هوش مصنوعی مقدور نمی‌باشد."

            final_reply = (
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📊 <b>داشبورد تحلیل هوشمند بازار</b>\n"
                f"📅 {get_persian_date()} | 🕐 {get_current_time()}\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{analysis}\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ <i>این تحلیل صرفاً جنبه بررسی داده‌ها را دارد و پیشنهاد خرید یا فروش نیست.</i>"
            )

            try:
                await query.edit_message_text(
                    final_reply,
                    reply_markup=get_main_keyboard(),
                    parse_mode="HTML",
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=final_reply,
                    reply_markup=get_main_keyboard(),
                    parse_mode="HTML",
                )
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ خطا در تحلیل.", reply_markup=get_main_keyboard())

    elif data_payload == "start_tse_search":
        await start_tse_search_flow(update, context)

    elif data_payload == "news_menu":
        await show_news_menu(update, context)

    elif data_payload.startswith("fetchnews_"):
        await fetch_news_callback(update, context)

    elif data_payload.startswith("ai_trans_"):
        await ai_translate_news_callback(update, context)

    elif data_payload == "list_my_alerts":
        await show_my_alerts(update, context)

    elif data_payload.startswith("delalert_"):
        await delete_alert_callback(update, context)

    elif data_payload == "back_to_main":
        await query.edit_message_text(
            "👋 <b>منوی اصلی ربات:</b>\n\nیکی از گزینه‌های زیر را انتخاب نمایید:",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML",
        )

    elif data_payload == "ai_help":
        help_text = (
            "💡 <b>راهنمای گفتگو با هوش مصنوعی:</b>\n\n"
            "کافی است دستور <code>/ai</code> را به همراه سوال بفرستید.\n"
            "مثال:\n"
            "<code>/ai علت نوسان امروز شاخص کل چیست؟</code>"
        )
        await query.message.reply_text(help_text, parse_mode="HTML")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ خطای شبکه یا تلگرام: {context.error}")


# =========================================================
# اجرای اصلی
# =========================================================

async def post_init(application: Application):
    commands = [
        BotCommand("start", "شروع ربات و منوی اصلی"),
        BotCommand("price", "قیمت لحظه‌ای بازار و شاخص بورس"),
        BotCommand("tse", "استعلام تابلوی آنلاین نماد بورسی"),
        BotCommand("news", "اخبار اقتصادی، بورس و عرضه اولیه"),
        BotCommand("calc", "ماشین‌حساب فاکتور رسمی طلا"),
        BotCommand("alert", "ثبت هشدار اختصاصی قیمت"),
        BotCommand("myalerts", "مشاهده و مدیریت هشدارهای من"),
        BotCommand("analysis", "تحلیل بازار با هوش مصنوعی"),
        BotCommand("ai", "پرسش آزاد از هوش مصنوعی"),
    ]
    try:
        await application.bot.set_my_commands(commands)
    except Exception as e:
        print(f"Set Commands Warning: {e}")


def main():
    init_database()

    print("========================================")
    print("       Telegram Market Price Bot")
    print("========================================")
    print(f"🕐 Tehran Time: {get_current_time()}")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connection_pool_size(100)
        .pool_timeout(30.0)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .get_updates_connect_timeout(30.0)
        .get_updates_read_timeout(30.0)
        .post_init(post_init)
        .build()
    )

    tse_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("tse", start_tse_search_flow),
            CommandHandler("bourse", start_tse_search_flow),
            CallbackQueryHandler(start_tse_search_flow, pattern="^start_tse_search$"),
            MessageHandler(filters.Regex("^📈 استعلام نماد بورس$"), start_tse_search_flow),
        ],
        states={
            TSE_SYMBOL_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, tse_symbol_received),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", tse_cancel),
            CallbackQueryHandler(tse_cancel, pattern="^tse_cancel$"),
        ],
        per_chat=True,
        per_user=True,
        per_message=False,
    )
    application.add_handler(tse_conv_handler)

    calc_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("calc", start_calc_command),
            CallbackQueryHandler(start_calc_command, pattern="^start_calc$"),
        ],
        states={
            CALC_TYPE: [
                CallbackQueryHandler(calc_type_callback, pattern="^calc_type_"),
                CallbackQueryHandler(calc_type_callback, pattern="^calc_cancel$"),
            ],
            CALC_WEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_weight_received),
            ],
            CALC_WAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_wage_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", calc_cancel)],
        per_chat=True,
        per_user=True,
        per_message=False,
    )
    application.add_handler(calc_conv_handler)

    alert_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("alert", start_alert_flow),
            CallbackQueryHandler(start_alert_flow, pattern="^start_alert$"),
        ],
        states={
            ALERT_ASSET: [
                CallbackQueryHandler(alert_asset_selected, pattern="^alertasset_"),
                CallbackQueryHandler(alert_asset_selected, pattern="^alert_cancel$"),
            ],
            ALERT_CONDITION: [
                CallbackQueryHandler(alert_condition_selected, pattern="^alertcond_"),
                CallbackQueryHandler(alert_condition_selected, pattern="^alert_cancel$"),
            ],
            ALERT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, alert_price_received),
            ],
        },
        fallbacks=[CommandHandler("cancel", alert_cancel)],
        per_chat=True,
        per_user=True,
        per_message=False,
    )
    application.add_handler(alert_conv_handler)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("news", show_news_menu))
    application.add_handler(CommandHandler("myalerts", show_my_alerts))
    application.add_handler(CommandHandler("analysis", analysis_command))
    application.add_handler(CommandHandler("ai", ai_command))

    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex("^(📊 استعلام قیمت‌ها|📈 استعلام نماد بورس|🧮 ماشین‌حساب طلا|📰 اخبار بازار و بورس|⏰ تنظیم هشدار قیمت|📋 هشدارهای من|📈 تحلیل هوشمند بازار|🔄 شروع مجدد)$"),
            handle_reply_keyboard_text,
        )
    )

    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    first_run_seconds = seconds_until_next_hour()
    print(f"⏳ اولین ارسال ساعتی تا {first_run_seconds / 60:.1f} دقیقه دیگر انجام می‌شود.")
    application.job_queue.run_repeating(
        send_hourly_market_price,
        interval=3600,
        first=first_run_seconds,
    )

    # پایش لحظه‌ای و بلادرنگ اخبار مهم، سود/زیان و عرضه‌های اولیه (هر ۶۰ ثانیه یک‌بار)
    application.job_queue.run_repeating(
        check_and_broadcast_breaking_news,
        interval=60,
        first=5,
    )

    # یادآوری خودکار روزشمار عرضه‌های اولیه هر روز ساعت ۰۸:۳۰ صبح
    application.job_queue.run_daily(
        daily_ipo_reminder_job,
        time=time(hour=8, minute=30, tzinfo=TEHRAN_TZ),
    )

    # گزارش کارنامه جامع شبانه و نظرسنجی روزانه ساعت ۲۳:۵۸
    application.job_queue.run_daily(
        daily_summary_job,
        time=time(hour=23, minute=58, tzinfo=TEHRAN_TZ),
    )

    print("🤖 ربات Azar Market با سامانه پایش لحظه‌ای اخبار و بورس فعال شد.")
    application.run_polling()


if __name__ == "__main__":
    main()