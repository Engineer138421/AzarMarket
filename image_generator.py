# image_generator.py

import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

TEMPLATE_PATH = Path(__file__).resolve().parent / "template.png"

FONT_CANDIDATES = [
    "Vazirmatn-Bold.ttf", "Vazir.ttf", "B Nazanin.ttf", "IRANSans.ttf",
    "arial.ttf", "DejaVuSans-Bold.ttf", "tahoma.ttf"
]


def load_font(size):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def fix_text(text: str) -> str:
    """اصلاح نحوه نگارش حروف و جهت متون فارسی در Pillow"""
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)


def format_price(val):
    if val is None:
        return "---"
    try:
        val = float(val)
        return f"{int(val):,}" if val.is_integer() else f"{val:,.2f}"
    except Exception:
        return "---"


def format_pct(val):
    if val is None:
        return "0.0%"
    try:
        val = float(val)
        return f"+{val:.2f}%" if val > 0 else f"{val:.2f}%"
    except Exception:
        return "---"


def generate_market_card(market_data: dict, persian_date: str, current_time: str) -> io.BytesIO:
    """چاپ زنده جدول قیمت‌ها همراه با شاخص بورس، فونت درشت و ایموجی‌ها روی تصویر template.png"""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError("فایل template.png در کنار پروژه یافت نشد.")

    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    font_title = load_font(int(w * 0.054))
    font_subtitle = load_font(int(w * 0.032))
    font_row_name = load_font(int(w * 0.036))
    font_row_val = load_font(int(w * 0.038))
    font_pct = load_font(int(w * 0.030))

    # ۱. هدر برند و تاریخ
    draw.text((w // 2, int(h * 0.12)), fix_text("AZAR MARKET"), fill=(240, 205, 95, 255), font=font_title, anchor="mm")
    date_badge = f"{persian_date}  |  {current_time}"
    draw.text((w // 2, int(h * 0.165)), fix_text(date_badge), fill=(195, 215, 235, 240), font=font_subtitle, anchor="mm")

    # خط جداکننده زیر عنوان
    line_y = int(h * 0.195)
    draw.line([(int(w * 0.16), line_y), (int(w * 0.84), line_y)], fill=(215, 180, 60, 150), width=3)

    # ۲. فهرست دارایی‌ها (تتر حذف شده، شاخص بورس و اموجی‌ها فعال هستند)
    assets = [
        ("📈 شاخص بورس", "bourse"),
        ("🥇 طلای ۱۸ عیار", "gold18"),
        ("🪙 سکه امامی", "emami"),
        ("🪙 نیم سکه", "half"),
        ("🪙 ربع سکه", "quarter"),
        ("💵 دلار تهران", "dollar"),
        ("🌎 اونس جهانی", "ounce"),
        ("₿ بیت‌کوین", "bitcoin"),
        ("🛢 نفت برنت", "oil"),
    ]

    start_y = int(h * 0.235)
    step_y = int((h * 0.65) / len(assets))

    for idx, (fa_name, key) in enumerate(assets):
        item = market_data.get(key, {})
        price = format_price(item.get("price"))
        pct = format_pct(item.get("change_percent"))
        direction = item.get("direction")

        if direction == "high":
            color_pct = (85, 230, 110, 255)
            pct_text = f"▲ {pct}"
        elif direction == "low":
            color_pct = (255, 75, 65, 255)
            pct_text = f"▼ {pct}"
        else:
            color_pct = (210, 215, 225, 220)
            pct_text = f"• {pct}"

        cur_y = start_y + (idx * step_y)

        # نام دارایی
        draw.text((int(w * 0.82), cur_y), fix_text(fa_name), fill=(255, 255, 255, 255), font=font_row_name, anchor="rm")

        # مقدار یا قیمت
        draw.text((int(w * 0.46), cur_y), price, fill=(250, 250, 250, 255), font=font_row_val, anchor="mm")

        # درصد تغییرات
        draw.text((int(w * 0.17), cur_y), pct_text, fill=color_pct, font=font_pct, anchor="lm")

        # خط جداکننده افقی
        sep_y = cur_y + int(step_y * 0.50)
        if idx < len(assets) - 1:
            draw.line([(int(w * 0.16), sep_y), (int(w * 0.84), sep_y)], fill=(75, 95, 125, 90), width=1)

    # ۳. پاورقی
    draw.text((w // 2, int(h * 0.905)), fix_text("مرجع لحظه‌ای قیمت طلا، ارز و بورس تهران"), fill=(160, 175, 200, 220), font=font_subtitle, anchor="mm")

    output = io.BytesIO()
    img.convert("RGB").save(output, format="JPEG", quality=95)
    output.seek(0)
    return output