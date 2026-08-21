import telebot
from telebot import types
import sqlite3
import time
import random
import string
import threading
import re
import requests
from datetime import datetime, timedelta
import json
import os

TOKEN = os.getenv("BOT_TOKEN", "8943109859:AAFO07OxwDND2yrz7oSSNrTSm0tEgQ0stoI").strip()
if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Add your Telegram bot token as an environment variable."
    )

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "6040546032"))
except ValueError:
    raise RuntimeError("ADMIN_ID must be a valid integer.")

bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    last_daily INTEGER DEFAULT 0,
    referred_by INTEGER,
    ref_count INTEGER DEFAULT 0,
    warnings INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    is_premium INTEGER DEFAULT 0,
    premium_until INTEGER DEFAULT 0,
    joined_at INTEGER DEFAULT 0,
    username TEXT,
    language TEXT DEFAULT 'ar'
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    price INTEGER,
    original_price INTEGER,
    stock INTEGER,
    sold INTEGER DEFAULT 0,
    delivery_type TEXT,
    content TEXT,
    category TEXT,
    image_id TEXT,
    is_active INTEGER DEFAULT 1,
    added_at INTEGER,
    discount_percent INTEGER DEFAULT 0
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS links (
    code TEXT PRIMARY KEY,
    points INTEGER,
    max_uses INTEGER,
    used_count INTEGER DEFAULT 0,
    expire_at INTEGER,
    created_by INTEGER,
    created_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    product_id INTEGER,
    product_name TEXT,
    price INTEGER,
    delivery_type TEXT,
    content TEXT,
    status TEXT DEFAULT 'completed',
    purchased_at INTEGER,
    admin_note TEXT
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    is_read INTEGER DEFAULT 0,
    created_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS coupons (
    code TEXT PRIMARY KEY,
    discount_percent INTEGER,
    max_uses INTEGER,
    used_count INTEGER DEFAULT 0,
    expire_at INTEGER,
    min_purchase INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    subject TEXT,
    status TEXT DEFAULT 'open',
    created_at INTEGER,
    closed_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    product_id INTEGER,
    rating INTEGER,
    comment TEXT,
    created_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    method TEXT,
    details TEXT,
    status TEXT DEFAULT 'pending',
    created_at INTEGER,
    processed_at INTEGER
)""")

# أكواد خاصة تعطي نقاط: كل كود يعمل فقط للمستخدمين اللي الأدمن صرّح لهم صراحة
# (عبر أمر /grant) - يعني وجود الكود لوحده لا يكفي لاستخدامه.
cur.execute("""CREATE TABLE IF NOT EXISTS special_codes (
    code TEXT PRIMARY KEY,
    points INTEGER,
    is_active INTEGER DEFAULT 1,
    created_at INTEGER
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS special_code_access (
    code TEXT,
    user_id INTEGER,
    used INTEGER DEFAULT 0,
    granted_at INTEGER,
    used_at INTEGER,
    PRIMARY KEY (code, user_id)
)""")

conn.commit()

def _seed_special_codes():
    now = int(time.time())
    for code, pts in (("BLACK6002", 600), ("BLACKWEB", 100000)):
        cur.execute("INSERT OR IGNORE INTO special_codes (code, points, is_active, created_at) VALUES (?, ?, 1, ?)",
                    (code, pts, now))
    conn.commit()

_seed_special_codes()

EMOJI_CROWN = "5017184459347199280"
EMOJI_ROCKET = "5017341470466639017"
EMOJI_FIRE = "5019401809228202926"
EMOJI_SHIELD = "5019584761950110887"
EMOJI_STAR = "5017218054581388213"
EMOJI_SPARKLES = "5019656878745978138"
EMOJI_MAIL = "5019765756166931507"
EMOJI_SUCCESS = "5019651033295487811"
EMOJI_FAIL = "5017073954133640188"
EMOJI_WARNING = "5019401809228202926"
EMOJI_TARGET = "5019759644428469277"
EMOJI_LIST = "5017098860648989669"
EMOJI_KEY = "5019569849823659365"
EMOJI_GLOBE = "5017154574964753399"
EMOJI_HEART = "5017351305941746807"
EMOJI_DIAMOND = "5017181010488460393"
EMOJI_TIME = "5017497085721708142"
EMOJI_MONEY = "5019759644428469277"
EMOJI_GIFT = "5019656878745978138"
EMOJI_SETTINGS = "5017558392084890552"

DEVELOPER_USERNAME = "tiba629"
BOT_USERNAME = bot.get_me().username
PREMIUM_PRICE = 500
PREMIUM_DURATION = 30

CHAT_BONUS_URL = "https://t.me/blacke13"
CHAT_BONUS_CHANNEL = "@blacke13"
CHAT_BONUS_AMOUNT = 300
WEBSITE_URL = "https://black-hub-central.lovable.app/"

user_states = {}

def _init_cfg():
    defaults = {
        "daily_status": "on",
        "daily_points": "25",
        "ref_points": "25",
        "min_withdraw": "200",
        "withdraw_status": "on",
        "maintenance_mode": "off",
        "bot_name": "بلاك ويب",
        "support_username": "Fp_h9",
        "channel_username": "blackdgm",
        "force_join": "on",
        "payment_methods": "فودافون كاش,تحويل بنكي,شام كاش,نجوم",
        "welcome_bonus": "50",
        "max_warnings": "3",
        "currency": "💎",
        "transfer_fee": "0"
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()

_init_cfg()

def _ensure_chat_bonus_column():
    try:
        cur.execute("ALTER TABLE users ADD COLUMN chat_bonus_claimed INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()

_ensure_chat_bonus_column()

def _seed_initial_products():
    try:
        cur.execute("SELECT COUNT(*) FROM products")
        if cur.fetchone()[0] > 0:
            return
    except Exception:
        return
    now = int(time.time())
    initial_products = [
        # (name, description, price, original_price, stock, content, category)
        ("اشتراك تلكرام بريميوم - 3 أشهر", "اشتراك رسمي لمدة 3 أشهر مع كل المزايا: تحويلات بدون حدود، ملصقات حصرية، ردود خاصة، سرعة مضاعفة، رفع ملفات حتى 4GB. تسليم تلقائي.", 1200, 1500, 30, "TG-PREM-3M-X9K", "اشتراكات"),
        ("اشتراك تلكرام بريميوم - شهر", "اشتراك رسمي لمدة شهر كامل مع كل المزايا الحصرية. تسليم تلقائي وفوري.", 500, 600, 50, "TG-PREM-1M-Z7A", "اشتراكات"),
        ("1000 نجمة تيليجرام", "رصيد تيليجرام ستارز 1000 نجمة جاهز للشحن المباشر. تسليم تلقائي فوري.", 8000, 10000, 40, "TG-STARS-1000", "نجوم تلكرام"),
        ("500 نجمة تيليجرام", "رصيد 500 نجمة تيليجرام لتحويلها لقناتك أو لبوتاتك. تسليم تلقائي.", 4500, 5500, 50, "TG-STARS-500", "نجوم تلكرام"),
        ("100 نجمة تيليجرام", "رصيد 100 نجمة تيليجرام، مثالي للهدايا السريعة. تسليم تلقائي.", 1000, 1300, 100, "TG-STARS-100", "نجوم تلكرام"),
        ("حزمة ملصقات حصرية - 100 ملصق", "مجموعة ملصقات نادرة وحصرية لإضفاء طابع مميز على محادثاتك.", 150, 200, 75, "STICKERS-PACK-VIP", "ملصقات"),
        ("ثيمات مميزة تلكرام", "ثيمات فاخرة بتصاميم راقية لقنواتك ومحادثاتك.", 200, 250, 30, "THEME-PREMIUM-V2", "ثيمات"),
        ("بوت إدارة قنوات احترافي", "بوت متكامل لإدارة قنواتك: ترحيب تلقائي، حذف سبام، إحصائيات، أوامر إدارية متقدمة.", 1800, 2500, 10, "ADMIN-BOT-XL", "بوتات"),
        ("بوت مبيعات ومتجر إلكتروني", "بوت متجر متكامل بميزات الإدارة والمنتجات والدفع والمخزون والكوبونات.", 2200, 3000, 8, "STORE-BOT-PRO", "بوتات"),
        ("اسم مستخدم تيليجرام مميز", "اسم مستخدم تيليجرام قصير ومميز للبيع أو المزاد أو العلامة التجارية.", 3500, 5000, 5, "USERNAME-PREMIUM", "حسابات"),
        ("خدمة تصميم شعار لقناة/بوت", "تصميم شعار احترافي لقناتك أو بوتك بصيغة PNG عالية الدقة.", 800, 1200, 20, "LOGO-SERVICE", "خدمات رقمية"),
        ("اشتراك بريميوم 6 أشهر + هدايا", "اشتراك بريميوم لمدة 6 أشهر كاملة مع بونص 200 نجمة هدبة.", 2200, 2800, 15, "PREM-6M-BONUS", "اشتراكات"),
        ("باقة بلاك الذهبية - عرض حصري", "حزمة متكاملة: بريميوم 3 أشهر + 500 نجمة + ملصقات حصرية + ثيم مميز بـ 2400 بدل 3200.", 2400, 3200, 20, "BLACK-GOLD-BUNDLE", "عروض بلاك"),
        ("باقة بلاك الفضية", "بريميوم شهر + 100 نجمة + مؤسسة ملصقات بـ 850 بدل 1200.", 850, 1200, 35, "BLACK-SILVER-BUNDLE", "عروض بلاك"),
        ("حزمة نجوم كبار - 5000 نجمة", "رصيد 5000 نجمة تيليجرام بسعر مخفض. شحن فوري لقناتك.", 35000, 45000, 10, "TG-STARS-5000", "نجوم تلكرام"),
        ("عرض دخول دردشة 𝑩𝑳𝑨𝑪𝑲 VIP", "انضم لدردشة بلاك VIP عبر الرابط https://t.me/blacke13 واحصل على محتوى حصري ومكافآت يومية.", 0, 0, 9999, "https://t.me/blacke13", "عروض حصرية"),
    ]
    for name, desc, price, oprice, stock, content, cat in initial_products:
        disc = 0
        if oprice > price and oprice > 0:
            disc = int((1 - price / oprice) * 100)
        cur.execute("""INSERT INTO products (name, description, price, original_price, stock, delivery_type, content, category, added_at, discount_percent, is_active)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (name, desc, price, oprice, stock, "auto", content, cat, now, disc))
    conn.commit()

_seed_initial_products()

def _cfg(k):
    cur.execute("SELECT value FROM settings WHERE key = ?", (k,))
    r = cur.fetchone()
    return r[0] if r else None

def _set_cfg(k, v):
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()

def is_admin(uid):
    return uid == ADMIN_ID

def is_banned(uid):
    cur.execute("SELECT is_banned FROM users WHERE user_id = ?", (uid,))
    r = cur.fetchone()
    return r and r[0] == 1

def is_premium(uid):
    cur.execute("SELECT is_premium, premium_until FROM users WHERE user_id = ?", (uid,))
    r = cur.fetchone()
    if r and r[0] == 1:
        if r[1] > int(time.time()):
            return True
        else:
            cur.execute("UPDATE users SET is_premium = 0 WHERE user_id = ?", (uid,))
            conn.commit()
    return False

def get_user_rank(uid):
    cur.execute("SELECT total_spent FROM users WHERE user_id = ?", (uid,))
    r = cur.fetchone()
    if not r:
        return "جديد"
    spent = r[0]
    if spent >= 5000:
        return "الأسطوري"
    elif spent >= 3000:
        return "الماسي"
    elif spent >= 1500:
        return "الذهبي"
    elif spent >= 500:
        return "الفضي"
    elif spent >= 100:
        return "البرونزي"
    return "جديد"

def add_notification(uid, message):
    cur.execute("INSERT INTO notifications (user_id, message, created_at) VALUES (?, ?, ?)",
                (uid, message, int(time.time())))
    conn.commit()

def format_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

def get_user_stats(uid):
    cur.execute("SELECT balance, total_earned, total_spent, ref_count FROM users WHERE user_id = ?", (uid,))
    r = cur.fetchone()
    if r:
        return {"balance": r[0], "total_earned": r[1], "total_spent": r[2], "ref_count": r[3]}
    return {"balance": 0, "total_earned": 0, "total_spent": 0, "ref_count": 0}

def check_force_join(uid):
    if _cfg("force_join") != "on":
        return True
    channel = _cfg("channel_username")
    if not channel:
        return True
    try:
        member = bot.get_chat_member(f"@{channel}", uid)
        return member.status not in ['left', 'kicked']
    except:
        return True

def get_force_join_kb():
    channel = _cfg("channel_username")
    keyboard = []
    if channel:
        keyboard.append([{"text": "القناة الرسمية", "url": f"https://t.me/{channel}"}])
    keyboard.append([{"text": "تحقق من الانضمام", "callback_data": "check_join"}])
    return keyboard

def _main_kb():
    keyboard = [
        [
            {"text": "المتجر", "callback_data": "shop"},
            {"text": "رصيدي", "callback_data": "balance"}
        ],
        [
            {"text": "المكافآت", "callback_data": "rewards_menu"},
            {"text": "الإحالات", "callback_data": "refs"}
        ],
        [
            {"text": "المميزات", "callback_data": "premium_info"},
            {"text": "كوبون خصم", "callback_data": "coupon_menu"}
        ],
        [
            {"text": "الإحصائيات", "callback_data": "my_stats"},
            {"text": "الدعم الفني", "callback_data": "support"}
        ]
    ]
    return keyboard

def _admin_kb():
    keyboard = [
        [
            {"text": "إضافة سلعة", "callback_data": "add_product"},
            {"text": "إدارة السلع", "callback_data": "manage_products"}
        ],
        [
            {"text": "إدارة الجوائز", "callback_data": "rewards_admin"},
            {"text": "إدارة المستخدمين", "callback_data": "users_admin"}
        ],
        [
            {"text": "إدارة الروابط", "callback_data": "links_admin"},
            {"text": "إدارة الكوبونات", "callback_data": "coupons_admin"}
        ],
        [
            {"text": "طلبات السحب", "callback_data": "withdrawals_admin"},
            {"text": "التذاكر", "callback_data": "tickets_admin"}
        ],
        [
            {"text": "بث شامل", "callback_data": "broadcast"},
            {"text": "الإحصائيات", "callback_data": "stats"}
        ],
        [
            {"text": "الإعدادات المتقدمة", "callback_data": "advanced_settings"},
            {"text": "بحث عن مستخدم", "callback_data": "search_user"}
        ],
        [
            {"text": "إعادة تشغيل", "callback_data": "restart_bot"}
        ]
    ]
    return keyboard

def _ensure_user(uid, uname=None, ref=None):
    now = int(time.time())
    cur.execute("SELECT 1 FROM users WHERE user_id = ?", (uid,))
    if not cur.fetchone():
        welcome_bonus = int(_cfg("welcome_bonus"))
        cur.execute("""INSERT INTO users (user_id, balance, total_earned, referred_by, joined_at, username) 
                     VALUES (?, ?, ?, ?, ?, ?)""",
                    (uid, welcome_bonus, welcome_bonus, ref, now, uname))
        conn.commit()
        if ref and ref != uid and not is_banned(ref):
            rp = int(_cfg("ref_points"))
            cur.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ?, ref_count = ref_count + 1 WHERE user_id = ?",
                        (rp, rp, ref))
            conn.commit()
            try:
                bot.send_message(ref, f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎉</tg-emoji> <b>مبروك! شخص جديد دخل من رابطك!</b>\n<blockquote>حصلت على {rp} {_cfg("currency")}\nالعضو: {uname or "بدون اسم"}</blockquote>', parse_mode='HTML')
                add_notification(ref, f"عضو جديد انضم عبر رابطك! +{rp} {_cfg('currency')}")
            except:
                pass
        try:
            bot.send_message(ADMIN_ID, f'<tg-emoji emoji-id="{EMOJI_HEART}">👤</tg-emoji> <b>عضو جديد</b>\n<blockquote expandable>\nالاسم: {uname or "بدون اسم"}\nID: <code>{uid}</code>\nالمكافأة: {welcome_bonus} {_cfg("currency")}\n</blockquote>', parse_mode='HTML')
        except:
            pass
    else:
        cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (uname, uid))
        conn.commit()

@bot.message_handler(commands=["start"])
def _cmd_start(msg):
    uid = msg.from_user.id
    uname = msg.from_user.username
    if is_banned(uid):
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_FAIL}">🚫</tg-emoji> <b>لقد تم حظرك من استخدام البوت</b>\n<blockquote>للتواصل مع الدعم: @{DEVELOPER_USERNAME}</blockquote>', parse_mode='HTML')
        return
    if not check_force_join(uid):
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_WARNING}">⚠️</tg-emoji> <b>يجب عليك الانضمام إلى قناتنا الرسمية أولاً</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": get_force_join_kb()}))
        return
    parts = msg.text.split()
    ref = None
    if len(parts) > 1:
        param = parts[1]
        cur.execute("SELECT points, max_uses, used_count, expire_at FROM links WHERE code = ?", (param,))
        link = cur.fetchone()
        if link:
            pts, mx, used, exp = link
            now = int(time.time())
            if used >= mx or now > exp:
                bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>عذراً، هذا الرابط منتهي الصلاحية</b>', parse_mode='HTML')
            else:
                cur.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?",
                            (pts, pts, uid))
                cur.execute("UPDATE links SET used_count = used_count + 1 WHERE code = ?", (param,))
                conn.commit()
                bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎁</tg-emoji> <b>تمت إضافة {pts} {_cfg("currency")} إلى رصيدك!</b>', parse_mode='HTML')
            _ensure_user(uid, uname)
            bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_CROWN}">👋</tg-emoji> <b>أهلاً بك في {_cfg("bot_name")}!</b>\n<blockquote expandable>\nرصيدك: {get_user_stats(uid)["balance"]} {_cfg("currency")}\nرتبتك: {get_user_rank(uid)}\n</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
            return
        else:
            ref = int(param) if param.isdigit() else None
    _ensure_user(uid, uname, ref)
    welcome_text = (
        f'<tg-emoji emoji-id="{EMOJI_CROWN}">🌟</tg-emoji> <b>أهلاً بك في {_cfg("bot_name")}</b>\n'
        f'<blockquote expandable>\n'
        f'🛒 تصفح المنتجات واشتري بسهولة\n'
        f'🎁 انضم لدردشة بلاك واحصل على {CHAT_BONUS_AMOUNT} {_cfg("currency")} مجاناً\n'
        f'👥 اربح من نظام الإحالات\n'
        f'⭐ عضوية مميزة بمزايا حصرية\n'
        f'🎫 كوبونات خصم وتخفيضات\n'
        f'</blockquote>\n'
        f'<tg-emoji emoji-id="{EMOJI_DIAMOND}">👨‍💻</tg-emoji> <b>المطور:</b> @{DEVELOPER_USERNAME}\n'
        f'<tg-emoji emoji-id="{EMOJI_GLOBE}">🌐</tg-emoji> <b>موقعنا:</b> {WEBSITE_URL}'
    )
    bot.send_message(uid, welcome_text, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))

@bot.callback_query_handler(func=lambda c: True)
def _cb_handler(call):
    uid = call.from_user.id
    uname = call.from_user.username
    data = call.data
    
    if is_banned(uid):
        bot.answer_callback_query(call.id, "محظور")
        return
    
    if not check_force_join(uid) and data != "check_join":
        bot.answer_callback_query(call.id, "انضم للقناة أولاً", show_alert=True)
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_WARNING}">⚠️</tg-emoji> <b>يجب عليك الانضمام إلى قناتنا الرسمية أولاً</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": get_force_join_kb()}))
        return
    
    if data == "check_join":
        if check_force_join(uid):
            bot.answer_callback_query(call.id, "تم التحقق بنجاح!")
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم التحقق! أهلاً بك</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
        else:
            bot.answer_callback_query(call.id, "لم تنضم بعد!", show_alert=True)
        return
    
    if data == "back_main":
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_CROWN}">🏠</tg-emoji> <b>القائمة الرئيسية</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
    
    elif data == "shop":
        cur.execute("SELECT DISTINCT category FROM products WHERE is_active = 1 AND stock > 0")
        cats = cur.fetchall()
        keyboard = []
        if cats:
            for cat in cats:
                if cat[0]:
                    keyboard.append([{"text": f"📂 {cat[0]}", "callback_data": f"cat_{cat[0]}"}])
        keyboard.append([{"text": "كل المنتجات", "callback_data": "all_products"}])
        keyboard.append([{"text": "بحث", "callback_data": "search_product"}])
        keyboard.append([{"text": "رجوع", "callback_data": "back_main"}])
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_DIAMOND}">🛒</tg-emoji> <b>المتجر</b>\n<blockquote>اختر التصنيف أو تصفح كل المنتجات</blockquote>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("cat_"):
        cat = data[4:]
        cur.execute("SELECT id, name, price, original_price, stock, discount_percent FROM products WHERE is_active = 1 AND stock > 0 AND category = ?", (cat,))
        prods = cur.fetchall()
        if prods:
            keyboard = []
            for pid, name, price, oprice, stock, disc in prods:
                price_text = f"{price}"
                if disc > 0:
                    price_text = f"{oprice}->{price} (-{disc}%)"
                keyboard.append([{"text": f"{name} | {price_text} | {stock}قطعة", "callback_data": f"view_{pid}"}])
            keyboard.append([{"text": "تصنيفات", "callback_data": "shop"}])
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_LIST}">📂</tg-emoji> <b>{cat}</b>\n<blockquote>اختر منتجاً</blockquote>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
        else:
            keyboard = [[{"text": "رجوع", "callback_data": "shop"}]]
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>لا توجد منتجات في هذا التصنيف</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "all_products":
        cur.execute("SELECT id, name, price, original_price, stock, discount_percent, category FROM products WHERE is_active = 1 AND stock > 0 ORDER BY id DESC LIMIT 20")
        prods = cur.fetchall()
        if prods:
            for pid, name, price, oprice, stock, disc, cat in prods:
                price_text = f"{price}"
                if disc > 0:
                    price_text = f"<s>{oprice}</s> {price} (-{disc}%)"
                keyboard = [
                    [
                        {"text": "شراء", "callback_data": f"buy_{pid}"},
                        {"text": "عرض", "callback_data": f"view_{pid}"}
                    ]
                ]
                product_text = f'<tg-emoji emoji-id="{EMOJI_DIAMOND}">📦</tg-emoji> <b>{name}</b>\n<blockquote expandable>\nالسعر: {price_text} {_cfg("currency")}\nالمخزون: {stock}\nالتصنيف: {cat or "بدون تصنيف"}\n</blockquote>'
                bot.send_message(uid, product_text, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
            keyboard2 = [[{"text": "تصنيفات", "callback_data": "shop"}]]
            bot.send_message(uid, "••••••••••••••••••", reply_markup=json.dumps({"inline_keyboard": keyboard2}))
        else:
            keyboard = [[{"text": "رجوع", "callback_data": "shop"}]]
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>لا توجد منتجات متاحة</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("view_"):
        pid = int(data[5:])
        cur.execute("SELECT * FROM products WHERE id = ?", (pid,))
        p = cur.fetchone()
        if p:
            _, name, desc, price, oprice, stock, sold, delivery, content, cat, img, active, added, disc = p
            keyboard = [
                [
                    {"text": "شراء", "callback_data": f"buy_{pid}"},
                    {"text": "تقييم", "callback_data": f"review_{pid}"}
                ],
                [{"text": "رجوع", "callback_data": "shop"}]
            ]
            price_text = f"{price} {_cfg('currency')}"
            if disc > 0:
                price_text = f"<s>{oprice}</s> <b>{price}</b> {_cfg('currency')} خصم {disc}%"
            text = (
                f'<tg-emoji emoji-id="{EMOJI_DIAMOND}">📦</tg-emoji> <b>{name}</b>\n'
                f'<blockquote expandable>\n'
                f'الوصف: {desc or "لا يوجد"}\n'
                f'السعر: {price_text}\n'
                f'المخزون: {stock}\n'
                f'تم البيع: {sold}\n'
                f'التصنيف: {cat or "عام"}\n'
                f'التوصيل: {"تلقائي" if delivery == "auto" else "يدوي"}\n'
                f'الحالة: {"متاح" if active else "غير متاح"}\n'
                f'</blockquote>'
            )
            if img:
                try:
                    bot.send_photo(uid, img, caption=text, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
                    return
                except:
                    pass
            bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("buy_"):
        pid = int(data.split("_")[1])
        cur.execute("SELECT * FROM products WHERE id = ? AND is_active = 1 AND stock > 0", (pid,))
        p = cur.fetchone()
        if not p:
            bot.answer_callback_query(call.id, "المنتج غير متاح", show_alert=True)
            return
        _, name, desc, price, oprice, stock, sold, delivery, content, cat, img, active, added, disc = p
        
        if stock <= 0:
            bot.answer_callback_query(call.id, "نفذ المخزون", show_alert=True)
            return
        
        final_price = price
        user_premium = is_premium(uid)
        if user_premium:
            final_price = int(price * 0.9)
        
        keyboard = [
            [{"text": "تأكيد الشراء", "callback_data": f"confirm_buy_{pid}"}],
            [{"text": "استخدام كوبون", "callback_data": f"use_coupon_{pid}"}],
            [{"text": "رجوع", "callback_data": f"view_{pid}"}]
        ]
        
        text = (
            f'<tg-emoji emoji-id="{EMOJI_MONEY}">🛒</tg-emoji> <b>تأكيد الشراء</b>\n'
            f'<blockquote expandable>\n'
            f'المنتج: {name}\n'
            f'السعر: {final_price} {_cfg("currency")}\n'
            f'{"خصم العضوية المميزة 10%" if user_premium else ""}\n'
            f'التوصيل: {"تلقائي" if delivery == "auto" else "يدوي"}\n'
            f'</blockquote>\n'
            f'<b>هل تريد تأكيد الشراء؟</b>'
        )
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("confirm_buy_"):
        pid = int(data.split("_")[2])
        if uid in user_states and "coupon" in user_states[uid]:
            coupon_code = user_states[uid]["coupon"]
            del user_states[uid]
            process_purchase(uid, pid, call.message, coupon_code)
        else:
            process_purchase(uid, pid, call.message)
    
    elif data.startswith("use_coupon_"):
        pid = int(data.split("_")[2])
        user_states[uid] = {"action": "buy_with_coupon", "product_id": pid}
        msg = bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_KEY}">🎫</tg-emoji> <b>أرسل كود الكوبون</b>', uid, call.message.message_id, parse_mode='HTML')
        bot.register_next_step_handler(msg, _handle_coupon_input)
    
    elif data == "balance":
        stats = get_user_stats(uid)
        rank = get_user_rank(uid)
        premium = is_premium(uid)
        text = (
            f'<tg-emoji emoji-id="{EMOJI_MONEY}">💰</tg-emoji> <b>رصيدي</b>\n'
            f'<blockquote expandable>\n'
            f'الرصيد: {stats["balance"]} {_cfg("currency")}\n'
            f'الإيرادات: {stats["total_earned"]} {_cfg("currency")}\n'
            f'المشتريات: {stats["total_spent"]} {_cfg("currency")}\n'
            f'الإحالات: {stats["ref_count"]}\n'
            f'الرتبة: {rank}\n'
            f'عضوية مميزة: {"مفعلة" if premium else "غير مفعلة"}\n'
            f'</blockquote>'
        )
        keyboard = [
            [
                {"text": "سحب", "callback_data": "withdraw"},
                {"text": "تفاصيل", "callback_data": "my_stats"}
            ],
            [{"text": "رجوع", "callback_data": "back_main"}]
        ]
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "rewards_menu":
        keyboard = [
            [{"text": "الجائزة اليومية", "callback_data": "daily"}],
            [{"text": f"انضم لدردشة بلاك - {CHAT_BONUS_AMOUNT}💎", "callback_data": "chat_bonus"}],
            [{"text": "تفعيل كوبون", "callback_data": "activate_coupon"}],
            [{"text": "روابط النقاط", "callback_data": "points_links"}],
            [{"text": "🔑 كود خاص", "callback_data": "special_code_menu"}],
            [{"text": "🌐 موقع بلاك ويب", "url": WEBSITE_URL}, {"text": "رجوع", "callback_data": "back_main"}]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎁</tg-emoji> <b>المكافآت والجوائز</b>\n<blockquote expandable>\n🎁 جائزة يومية\n👑 انضم لدردشة بلاك واحصل على {CHAT_BONUS_AMOUNT} {_cfg("currency")} هدية\n🎫 كوبونات خصم\n🔗 روابط نقاط\n🔑 كود خاص\n</blockquote>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "special_code_menu":
        msg = bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_KEY}">🔑</tg-emoji> <b>أرسل الكود الخاص</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "rewards_menu"}]]}))
        user_states[uid] = {"action": "special_code"}
        bot.register_next_step_handler(msg, _handle_special_code_input)
    
    elif data == "daily":
        st = _cfg("daily_status")
        if st == "off":
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">🚫</tg-emoji> <b>الجائزة اليومية مغلقة حالياً</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "rewards_menu"}]]}))
            return
        cur.execute("SELECT last_daily FROM users WHERE user_id = ?", (uid,))
        last = cur.fetchone()[0]
        now = int(time.time())
        if now - last < 86400:
            remaining = 86400 - (now - last)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_TIME}">⏰</tg-emoji> <b>استلمت جائزتك اليوم!</b>\n<blockquote>عودة بعد: {hours}h {minutes}m</blockquote>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "rewards_menu"}]]}))
        else:
            pts = int(_cfg("daily_points"))
            if is_premium(uid):
                pts = int(pts * 1.5)
            cur.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ?, last_daily = ? WHERE user_id = ?",
                        (pts, pts, now, uid))
            conn.commit()
            add_notification(uid, f"حصلت على الجائزة اليومية: {pts} {_cfg('currency')}")
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎉</tg-emoji> <b>مبروك! حصلت على {pts} {_cfg("currency")}</b>\n{":star: +50% مكافأة العضوية المميزة" if is_premium(uid) else ""}', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "rewards_menu"}]]}))
    
    elif data == "activate_coupon":
        msg = bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_KEY}">🎫</tg-emoji> <b>أرسل كود الكوبون</b>', uid, call.message.message_id, parse_mode='HTML')
        user_states[uid] = {"action": "activate_coupon"}
        bot.register_next_step_handler(msg, _handle_coupon_activation)
    
    elif data == "points_links":
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_MAIL}">🔗</tg-emoji> <b>أرسل كود رابط النقاط</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "rewards_menu"}]]}))
        user_states[uid] = {"action": "use_points_link"}
    
    elif data == "refs":
        link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        stats = get_user_stats(uid)
        text = (
            f'<tg-emoji emoji-id="{EMOJI_HEART}">👥</tg-emoji> <b>نظام الإحالات</b>\n'
            f'<blockquote expandable>\n'
            f'رابطك: <code>{link}</code>\n\n'
            f'عدد المدعوين: {stats["ref_count"]}\n'
            f'أرباح الإحالات: {stats["ref_count"] * int(_cfg("ref_points"))} {_cfg("currency")}\n'
            f'المكافأة: {_cfg("ref_points")} {_cfg("currency")} لكل دعوة\n'
            f'</blockquote>'
        )
        keyboard = [
            [
                {"text": "مشاركة", "url": f"https://t.me/share/url?url={link}&text=انضم%20لأفضل%20متجر"},
                {"text": "نسخ", "callback_data": f"copy_ref_{uid}"}
            ],
            [{"text": "رجوع", "callback_data": "back_main"}]
        ]
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("copy_ref_"):
        bot.answer_callback_query(call.id, "تم نسخ الرابط في الرسالة أعلاه")
    
    elif data == "premium_info":
        premium = is_premium(uid)
        if premium:
            cur.execute("SELECT premium_until FROM users WHERE user_id = ?", (uid,))
            until = cur.fetchone()[0]
            text = (
                f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐</tg-emoji> <b>العضوية المميزة</b>\n'
                f'<blockquote expandable>\n'
                f'حالتك: مفعلة\n'
                f'تنتهي: {format_time(until)}\n\n'
                f'مزاياك:\n'
                f'• خصم 10% على المشتريات\n'
                f'• زيادة 50% في الجائزة اليومية\n'
                f'• أولوية في الدعم الفني\n'
                f'• شارة مميزة في حسابك\n'
                f'</blockquote>'
            )
        else:
            text = (
                f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐</tg-emoji> <b>العضوية المميزة</b>\n'
                f'<blockquote expandable>\n'
                f'السعر: {PREMIUM_PRICE} {_cfg("currency")}\n'
                f'المدة: {PREMIUM_DURATION} يوم\n\n'
                f'المزايا:\n'
                f'• خصم 10% على جميع المشتريات\n'
                f'• زيادة 50% في الجائزة اليومية\n'
                f'• أولوية في الدعم الفني\n'
                f'• شارة مميزة\n'
                f'</blockquote>'
            )
        keyboard = []
        if not premium:
            keyboard.append([{"text": "شراء العضوية", "callback_data": "buy_premium"}])
        keyboard.append([{"text": "رجوع", "callback_data": "back_main"}])
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "buy_premium":
        stats = get_user_stats(uid)
        if stats['balance'] < PREMIUM_PRICE:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رصيدك غير كافٍ</b>\n<blockquote>تحتاج {PREMIUM_PRICE} {_cfg("currency")}</blockquote>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "premium_info"}]]}))
            return
        keyboard = [
            [
                {"text": "تأكيد", "callback_data": "confirm_premium"},
                {"text": "إلغاء", "callback_data": "premium_info"}
            ]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_MONEY}">🛒</tg-emoji> <b>تأكيد شراء العضوية المميزة بـ {PREMIUM_PRICE} {_cfg("currency")}؟</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "confirm_premium":
        stats = get_user_stats(uid)
        if stats['balance'] < PREMIUM_PRICE:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رصيد غير كافٍ</b>', uid, call.message.message_id, parse_mode='HTML')
            return
        cur.execute("UPDATE users SET balance = balance - ?, total_spent = total_spent + ?, is_premium = 1, premium_until = ? WHERE user_id = ?",
                    (PREMIUM_PRICE, PREMIUM_PRICE, int(time.time()) + PREMIUM_DURATION * 86400, uid))
        conn.commit()
        add_notification(uid, "تم تفعيل العضوية المميزة بنجاح!")
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎉</tg-emoji> <b>مبروك! تم تفعيل العضوية المميزة بنجاح!</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "back_main"}]]}))
        try:
            bot.send_message(ADMIN_ID, f'<tg-emoji emoji-id="{EMOJI_MONEY}">💰</tg-emoji> <b>شراء عضوية مميزة</b>\n<blockquote>المستخدم: <code>{uid}</code>\nالمبلغ: {PREMIUM_PRICE} {_cfg("currency")}</blockquote>', parse_mode='HTML')
        except:
            pass
    
    elif data == "coupon_menu":
        keyboard = [
            [{"text": "تفعيل كوبون", "callback_data": "activate_coupon"}],
            [{"text": "رجوع", "callback_data": "back_main"}]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_KEY}">🎫</tg-emoji> <b>الكوبونات</b>\n<blockquote>يمكنك تفعيل كوبون الخصم للحصول على تخفيض</blockquote>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "my_stats":
        stats = get_user_stats(uid)
        rank = get_user_rank(uid)
        premium = is_premium(uid)
        cur.execute("SELECT COUNT(*) FROM purchases WHERE user_id = ?", (uid,))
        purchases = cur.fetchone()[0]
        text = (
            f'<tg-emoji emoji-id="{EMOJI_LIST}">📊</tg-emoji> <b>إحصائياتي</b>\n'
            f'<blockquote expandable>\n'
            f'ID: <code>{uid}</code>\n'
            f'الرتبة: {rank}\n'
            f'مميز: {"✅" if premium else "❌"}\n'
            f'الرصيد: {stats["balance"]} {_cfg("currency")}\n'
            f'الإيرادات: {stats["total_earned"]} {_cfg("currency")}\n'
            f'المشتريات: {stats["total_spent"]} {_cfg("currency")}\n'
            f'عدد المشتريات: {purchases}\n'
            f'الإحالات: {stats["ref_count"]}\n'
            f'</blockquote>'
        )
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "back_main"}]]}))
    
    elif data == "support":
        keyboard = [
            [{"text": "فتح تذكرة", "callback_data": "open_ticket"}],
            [{"text": "المطور", "url": f"https://t.me/{DEVELOPER_USERNAME}"}],
            [{"text": "رجوع", "callback_data": "back_main"}]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SHIELD}">💬</tg-emoji> <b>الدعم الفني</b>\n<blockquote>للدعم تواصل مع المطور أو افتح تذكرة</blockquote>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "open_ticket":
        msg = bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_MAIL}">📩</tg-emoji> <b>أرسل موضوع التذكرة</b>', uid, call.message.message_id, parse_mode='HTML')
        user_states[uid] = {"action": "open_ticket"}
        bot.register_next_step_handler(msg, _handle_ticket_subject)
    
    elif data == "withdraw":
        if _cfg("withdraw_status") == "off":
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">🚫</tg-emoji> <b>السحب مغلق حالياً</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "balance"}]]}))
            return
        min_withdraw = int(_cfg("min_withdraw"))
        stats = get_user_stats(uid)
        if stats['balance'] < min_withdraw:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>الحد الأدنى للسحب: {min_withdraw} {_cfg("currency")}</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "balance"}]]}))
            return
        payment_methods = _cfg("payment_methods").split(",")
        keyboard = []
        for method in payment_methods:
            keyboard.append([{"text": f"💳 {method.strip()}", "callback_data": f"withdraw_method_{method.strip()}"}])
        keyboard.append([{"text": "رجوع", "callback_data": "balance"}])
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_MONEY}">💸</tg-emoji> <b>سحب الرصيد</b>\n<blockquote>رصيدك: {stats["balance"]} {_cfg("currency")}\nاختر طريقة الدفع</blockquote>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("withdraw_method_"):
        method = data[16:]
        user_states[uid] = {"action": "withdraw", "method": method}
        msg = bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_MONEY}">💳</tg-emoji> <b>الطريقة: {method}</b>\n<blockquote>أرسل تفاصيل الحساب</blockquote>', uid, call.message.message_id, parse_mode='HTML')
        bot.register_next_step_handler(msg, _handle_withdraw_details)
    
    elif data.startswith("review_"):
        pid = int(data[7:])
        cur.execute("SELECT id FROM purchases WHERE user_id = ? AND product_id = ?", (uid, pid))
        if not cur.fetchone():
            bot.answer_callback_query(call.id, "يجب شراء المنتج أولاً", show_alert=True)
            return
        user_states[uid] = {"action": "review", "product_id": pid}
        keyboard = []
        row = []
        for i in range(1, 6):
            row.append({"text": f"{i}⭐", "callback_data": f"rate_{pid}_{i}"})
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐</tg-emoji> <b>قيم المنتج من 1 إلى 5</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("rate_"):
        _, pid, rating = data.split("_")
        pid, rating = int(pid), int(rating)
        user_states[uid] = {"action": "review_comment", "product_id": pid, "rating": rating}
        msg = bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_STAR}">⭐</tg-emoji> <b>تقييم {rating}/5</b>\n<blockquote>أرسل تعليقك (أو أرسل "تخطي")</blockquote>', uid, call.message.message_id, parse_mode='HTML')
        bot.register_next_step_handler(msg, _handle_review_comment)
    
    elif data == "search_product":
        msg = bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_TARGET}">🔍</tg-emoji> <b>أرسل اسم المنتج للبحث عنه</b>', uid, call.message.message_id, parse_mode='HTML')
        user_states[uid] = {"action": "search_product"}
        bot.register_next_step_handler(msg, _handle_search_product)

    elif data == "chat_bonus":
        cur.execute("SELECT chat_bonus_claimed FROM users WHERE user_id = ?", (uid,))
        r = cur.fetchone()
        if not r:
            bot.answer_callback_query(call.id, "أرسل /start أولاً", show_alert=True)
            return
        if r[0] == 1:
            bot.edit_message_text(
                f'<tg-emoji emoji-id="{EMOJI_HEART}">✅</tg-emoji> <b>لقد استلمت مكافأة الدردشة سابقاً!</b>\n'
                f'<blockquote>انضم للدردشة VIP للاستفادة من المحتوى الحصري.</blockquote>',
                uid, call.message.message_id, parse_mode='HTML',
                reply_markup=json.dumps({"inline_keyboard": [
                    [{"text": "👑 دردشة بلاك", "url": CHAT_BONUS_URL}, {"text": "🌐 موقع بلاك ويب", "url": WEBSITE_URL}],
                    [{"text": "رجوع", "callback_data": "rewards_menu"}]
                ]}))
            return
        keyboard = [
            [{"text": "👑 انضم لدردشة بلاك VIP", "url": CHAT_BONUS_URL}],
            [{"text": "✅ تحققت من الانضمام", "callback_data": "verify_chat_join"}],
            [{"text": "🌐 زيارة موقع بلاك ويب", "url": WEBSITE_URL}],
            [{"text": "رجوع", "callback_data": "rewards_menu"}]
        ]
        bot.edit_message_text(
            f'<tg-emoji emoji-id="{EMOJI_HEART}">🎁</tg-emoji> <b>مكافأة {CHAT_BONUS_AMOUNT} {_cfg("currency")} - دردشة بلاك</b>\n'
            f'<blockquote expandable>\n'
            f'انضم لدردشة بلاك VIP عبر الرابط:\n{CHAT_BONUS_URL}\n\n'
            f'بعد الانضمام ارجع واضغط زر التحقق لاستلام {CHAT_BONUS_AMOUNT} {_cfg("currency")} فوراً.\n'
            f'</blockquote>',
            uid, call.message.message_id, parse_mode='HTML',
            reply_markup=json.dumps({"inline_keyboard": keyboard}))

    elif data == "verify_chat_join":
        cur.execute("SELECT chat_bonus_claimed FROM users WHERE user_id = ?", (uid,))
        r = cur.fetchone()
        if not r:
            bot.answer_callback_query(call.id, "ابدأ البوت أولاً عبر /start", show_alert=True)
            return
        if r[0] == 1:
            bot.answer_callback_query(call.id, "تم استلام المكافأة مسبقاً", show_alert=True)
            return
        try:
            m = bot.get_chat_member(CHAT_BONUS_CHANNEL, uid)
            if m.status in ['left', 'kicked']:
                bot.answer_callback_query(call.id, "لم تنضم بعد! انضم أولاً", show_alert=True)
                bot.edit_message_text(
                    f'<tg-emoji emoji-id="{EMOJI_WARNING}">⚠️</tg-emoji> <b>لم ينضم حسابك بعد!</b>\n'
                    f'<blockquote>انضم لـ {CHAT_BONUS_URL} ثم ارجع واضغط التحقق مرة أخرى.</blockquote>',
                    uid, call.message.message_id, parse_mode='HTML',
                    reply_markup=json.dumps({"inline_keyboard": [
                        [{"text": "👑 انضم الآن", "url": CHAT_BONUS_URL}],
                        [{"text": "✅ تحقق مجدداً", "callback_data": "verify_chat_join"}],
                        [{"text": "رجوع", "callback_data": "rewards_menu"}]
                    ]}))
                return
            cur.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ?, chat_bonus_claimed = 1 WHERE user_id = ?",
                        (CHAT_BONUS_AMOUNT, CHAT_BONUS_AMOUNT, uid))
            conn.commit()
            add_notification(uid, f"🎁 مكافأة دردشة بلاك: +{CHAT_BONUS_AMOUNT} {_cfg('currency')}")
            bot.edit_message_text(
                f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎉</tg-emoji> <b>مبروك! حصلت على {CHAT_BONUS_AMOUNT} {_cfg("currency")}</b>\n'
                f'<blockquote expandable>\nتمت إضافة الرصيد لحسابك.\nشكراً لانضمامك لدردشة بلاك VIP.\n\n'
                f'👑 الدردشة: {CHAT_BONUS_URL}\n'
                f'🌐 الموقع: {WEBSITE_URL}\n'
                f'</blockquote>',
                uid, call.message.message_id, parse_mode='HTML',
                reply_markup=json.dumps({"inline_keyboard": [
                    [{"text": "👑 الدردشة", "url": CHAT_BONUS_URL}, {"text": "🌐 موقع بلاك", "url": WEBSITE_URL}],
                    [{"text": "القائمة الرئيسية", "callback_data": "back_main"}]
                ]}))
            try:
                bot.send_message(ADMIN_ID, f'<tg-emoji emoji-id="{EMOJI_HEART}">🎁</tg-emoji> <b>مكافأة دردشة مُستلَمة</b>\n<blockquote>المستخدم: <code>{uid}</code>\nالمبلغ: {CHAT_BONUS_AMOUNT} {_cfg("currency")}</blockquote>', parse_mode='HTML')
            except Exception:
                pass
        except Exception as e:
            bot.answer_callback_query(call.id, f"تعذر التحقق، حاول لاحقاً ({str(e)[:30]})", show_alert=True)

    elif uid == ADMIN_ID:
        _admin_handlers(call, uid)

def process_purchase(uid, pid, msg, coupon_code=None):
    try:
        cur.execute("SELECT * FROM products WHERE id = ? AND is_active = 1 AND stock > 0", (pid,))
        p = cur.fetchone()
        if not p:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>المنتج غير متاح</b>', uid, msg.message_id, parse_mode='HTML')
            return
        
        _, name, desc, price, oprice, stock, sold, delivery, content, cat, img, active, added, disc = p
        final_price = price
        
        if coupon_code:
            cur.execute("SELECT discount_percent, max_uses, used_count, expire_at, min_purchase, is_active FROM coupons WHERE code = ?", (coupon_code,))
            coupon = cur.fetchone()
            if coupon:
                disc_percent, max_uses, used_count, expire_at, min_purchase, is_active = coupon
                if is_active and used_count < max_uses and int(time.time()) < expire_at and price >= min_purchase:
                    final_price = int(price * (1 - disc_percent / 100))
        
        if is_premium(uid):
            final_price = int(final_price * 0.9)
        
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        bal = cur.fetchone()[0]
        if bal < final_price:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رصيدك غير كافٍ</b>\n<blockquote>المطلوب: {final_price} {_cfg("currency")}</blockquote>', uid, msg.message_id, parse_mode='HTML')
            return
        
        cur.execute("UPDATE users SET balance = balance - ?, total_spent = total_spent + ? WHERE user_id = ?",
                    (final_price, final_price, uid))
        cur.execute("UPDATE products SET stock = stock - 1, sold = sold + 1 WHERE id = ?", (pid,))
        if coupon_code:
            cur.execute("UPDATE coupons SET used_count = used_count + 1 WHERE code = ? AND used_count < max_uses",
                        (coupon_code,))
        cur.execute("INSERT INTO purchases (user_id, product_id, product_name, price, delivery_type, content, purchased_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (uid, pid, name, final_price, delivery, content, int(time.time())))
        conn.commit()
        
        add_notification(uid, f"تم شراء {name} بنجاح!")
        
        if delivery == "auto":
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم الشراء بنجاح!</b>\n<blockquote expandable>\nالمنتج: {name}\nالسعر: {final_price} {_cfg("currency")}\nالمحتوى:\n<code>{content}</code>\n</blockquote>', uid, msg.message_id, parse_mode='HTML')
        else:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم تسجيل طلبك!</b>\n<blockquote expandable>\nالمنتج: {name}\nالسعر: {final_price} {_cfg("currency")}\nسيتواصل معك فريق الدعم قريباً\n</blockquote>', uid, msg.message_id, parse_mode='HTML')
        
        try:
            bot.send_message(ADMIN_ID, f'<tg-emoji emoji-id="{EMOJI_MONEY}">🔔</tg-emoji> <b>عملية شراء جديدة</b>\n<blockquote expandable>\nالمشتري: <code>{uid}</code>\nالمنتج: {name}\nالسعر: {final_price} {_cfg("currency")}\nالتوصيل: {delivery}\n</blockquote>', parse_mode='HTML')
        except:
            pass
    except Exception as e:
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>حدث خطأ</b>\n<blockquote>{e}</blockquote>', uid, msg.message_id, parse_mode='HTML')

def _admin_handlers(call, uid):
    data = call.data
    
    if data == "add_product":
        user_states[uid] = {"action": "add_product"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SPARKLES}">📝</tg-emoji> <b>أرسل اسم المنتج</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_add_product_name)
    
    elif data == "manage_products":
        cur.execute("SELECT id, name, price, stock, is_active, category FROM products ORDER BY id DESC LIMIT 20")
        prods = cur.fetchall()
        if prods:
            keyboard = []
            for pid, name, price, stock, active, cat in prods:
                status = "🟢" if active and stock > 0 else "🔴"
                keyboard.append([{"text": f"{status} {name} | {price}💎 | {stock}قطعة", "callback_data": f"admin_prod_{pid}"}])
            keyboard.append([{"text": "رجوع", "callback_data": "back_admin"}])
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_LIST}">📦</tg-emoji> <b>إدارة المنتجات</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
        else:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>لا توجد منتجات</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "back_admin"}]]}))
    
    elif data.startswith("admin_prod_"):
        pid = int(data[11:])
        cur.execute("SELECT * FROM products WHERE id = ?", (pid,))
        p = cur.fetchone()
        if p:
            _, name, desc, price, oprice, stock, sold, delivery, content, cat, img, active, added, disc = p
            keyboard = [
                [
                    {"text": "تعديل", "callback_data": f"edit_prod_{pid}"},
                    {"text": "حذف", "callback_data": f"del_prod_{pid}"}
                ],
                [
                    {"text": "تبديل الحالة", "callback_data": f"toggle_prod_{pid}"}
                ],
                [{"text": "رجوع", "callback_data": "manage_products"}]
            ]
            text = (
                f'<tg-emoji emoji-id="{EMOJI_DIAMOND}">📦</tg-emoji> <b>{name}</b>\n'
                f'<blockquote expandable>\n'
                f'السعر: {price} {_cfg("currency")}\n'
                f'المخزون: {stock} قطعة\n'
                f'التصنيف: {cat or "عام"}\n'
                f'الحالة: {"متاح" if active else "غير متاح"}\n'
                f'تم البيع: {sold}\n'
                f'</blockquote>'
            )
            bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("toggle_prod_"):
        pid = int(data[12:])
        cur.execute("SELECT is_active FROM products WHERE id = ?", (pid,))
        r = cur.fetchone()
        if r:
            new = 0 if r[0] == 1 else 1
            cur.execute("UPDATE products SET is_active = ? WHERE id = ?", (new, pid))
            conn.commit()
            bot.answer_callback_query(call.id, f"تم {'تفعيل' if new else 'تعطيل'} المنتج")
            _admin_handlers(call, uid)
    
    elif data.startswith("del_prod_"):
        pid = int(data[9:])
        keyboard = [
            [
                {"text": "نعم", "callback_data": f"confirm_del_{pid}"},
                {"text": "لا", "callback_data": f"admin_prod_{pid}"}
            ]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_WARNING}">⚠️</tg-emoji> <b>هل أنت متأكد من حذف المنتج؟</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("confirm_del_"):
        pid = int(data[12:])
        cur.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم حذف المنتج</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "manage_products"}]]}))
    
    elif data == "rewards_admin":
        keyboard = [
            [
                {"text": "فتح/غلق اليومية", "callback_data": "toggle_daily"},
                {"text": "نقاط اليومية", "callback_data": "set_daily_points"}
            ],
            [
                {"text": "نقاط الإحالة", "callback_data": "set_ref_points"},
                {"text": "مكافأة الترحيب", "callback_data": "set_welcome_bonus"}
            ],
            [{"text": "رجوع", "callback_data": "back_admin"}]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎁</tg-emoji> <b>إدارة الجوائز</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "toggle_daily":
        st = _cfg("daily_status")
        _set_cfg("daily_status", "off" if st == "on" else "on")
        bot.answer_callback_query(call.id, f"الجائزة {'مغلقة' if st == 'on' else 'مفتوحة'} الآن")
    
    elif data == "set_daily_points":
        user_states[uid] = {"action": "set_daily_points"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_STAR}">📝</tg-emoji> <b>أرسل عدد النقاط اليومية</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_set_daily_points)
    
    elif data == "set_ref_points":
        user_states[uid] = {"action": "set_ref_points"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_HEART}">📝</tg-emoji> <b>أرسل عدد نقاط الإحالة</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_set_ref_points)
    
    elif data == "set_welcome_bonus":
        user_states[uid] = {"action": "set_welcome_bonus"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SPARKLES}">📝</tg-emoji> <b>أرسل مكافأة الترحيب</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_set_welcome_bonus)
    
    elif data == "users_admin":
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]
        cur.execute("SELECT user_id, balance, username FROM users ORDER BY balance DESC LIMIT 5")
        top = cur.fetchall()
        text = (
            f'<tg-emoji emoji-id="{EMOJI_HEART}">👥</tg-emoji> <b>إدارة المستخدمين</b>\n'
            f'<blockquote expandable>\n'
            f'الكل: {total}\n'
            f'الأغنى:\n'
        )
        for u in top:
            text += f'• <code>{u[0]}</code> - {u[1]}💎\n'
        text += f'</blockquote>'
        keyboard = [
            [{"text": "رجوع", "callback_data": "back_admin"}]
        ]
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "links_admin":
        cur.execute("SELECT code, points, max_uses, used_count, expire_at FROM links ORDER BY expire_at DESC LIMIT 10")
        links = cur.fetchall()
        keyboard = []
        if links:
            for code, pts, mx, used, exp in links:
                status = "🟢" if used < mx and exp > int(time.time()) else "🔴"
                link_url = f"https://t.me/{BOT_USERNAME}?start={code}"
                keyboard.append([{"text": f"{status} {pts}💎 | {used}/{mx}", "url": link_url}])
        keyboard.append([{"text": "رابط جديد", "callback_data": "make_link"}])
        keyboard.append([{"text": "حذف المنتهية", "callback_data": "delete_expired_links"}])
        keyboard.append([{"text": "رجوع", "callback_data": "back_admin"}])
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_KEY}">🔗</tg-emoji> <b>الروابط النشطة</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "make_link":
        user_states[uid] = {"action": "make_link"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_KEY}">📝</tg-emoji> <b>أرسل: عدد_النقاط عدد_الاستخدامات عدد_الساعات</b>\n<blockquote>مثال: 50 10 24</blockquote>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_make_link)
    
    elif data == "delete_expired_links":
        cur.execute("DELETE FROM links WHERE expire_at < ? OR used_count >= max_uses", (int(time.time()),))
        conn.commit()
        bot.answer_callback_query(call.id, "تم حذف الروابط المنتهية")
    
    elif data == "coupons_admin":
        keyboard = [
            [{"text": "كوبون جديد", "callback_data": "add_coupon"}],
            [{"text": "رجوع", "callback_data": "back_admin"}]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_KEY}">🎫</tg-emoji> <b>إدارة الكوبونات</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "add_coupon":
        user_states[uid] = {"action": "add_coupon"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_KEY}">📝</tg-emoji> <b>أرسل: نسبة_الخصم الحد_الأقصى_للاستخدام المدة_بالساعات الحد_الأدنى_للشراء</b>\n<blockquote>مثال: 20 50 72 100</blockquote>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_add_coupon)
    
    elif data == "withdrawals_admin":
        cur.execute("SELECT id, user_id, amount, method, status, created_at FROM withdrawals ORDER BY created_at DESC LIMIT 10")
        withdrawals = cur.fetchall()
        if withdrawals:
            keyboard = []
            for wid, user_id, amount, method, status, created in withdrawals:
                status_emoji = "🟢" if status == "completed" else "🟡" if status == "pending" else "🔴"
                keyboard.append([{"text": f"{status_emoji} {amount}💎 | {user_id}", "callback_data": f"admin_withdraw_{wid}"}])
            keyboard.append([{"text": "رجوع", "callback_data": "back_admin"}])
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_MONEY}">💰</tg-emoji> <b>طلبات السحب</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
        else:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>لا توجد طلبات</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "back_admin"}]]}))
    
    elif data == "tickets_admin":
        cur.execute("SELECT id, user_id, subject, status FROM support_tickets WHERE status = 'open' ORDER BY created_at DESC LIMIT 10")
        tickets = cur.fetchall()
        if tickets:
            keyboard = []
            for tid, user_id, subject, status in tickets:
                keyboard.append([{"text": f"🟡 {user_id}: {subject[:20]}", "callback_data": f"admin_ticket_{tid}"}])
            keyboard.append([{"text": "رجوع", "callback_data": "back_admin"}])
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SHIELD}">💬</tg-emoji> <b>التذاكر المفتوحة</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
        else:
            bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>لا توجد تذاكر مفتوحة</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "back_admin"}]]}))
    
    elif data == "broadcast":
        keyboard = [
            [
                {"text": "للجميع", "callback_data": "bc_all"},
                {"text": "للمميزين", "callback_data": "bc_premium"}
            ],
            [{"text": "رجوع", "callback_data": "back_admin"}]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_ROCKET}">📢</tg-emoji> <b>اختر نوع البث</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data.startswith("bc_"):
        target = data[3:]
        user_states[uid] = {"action": "broadcast", "target": target}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_ROCKET}">📝</tg-emoji> <b>أرسل الرسالة للبث</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_broadcast)
    
    elif data == "stats":
        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM products")
        prods = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM purchases")
        purchases = cur.fetchone()[0]
        cur.execute("SELECT SUM(price) FROM purchases")
        total_sales = cur.fetchone()[0] or 0
        cur.execute("SELECT SUM(balance) FROM users")
        total_balance = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(*) FROM users WHERE joined_at > ?", (int(time.time()) - 86400,))
        new_today = cur.fetchone()[0]
        text = (
            f'<tg-emoji emoji-id="{EMOJI_STAR}">📊</tg-emoji> <b>الإحصائيات العامة</b>\n'
            f'<blockquote expandable>\n'
            f'المستخدمين: {users}\n'
            f'اليوم: {new_today}\n'
            f'المنتجات: {prods}\n'
            f'المبيعات: {purchases}\n'
            f'إجمالي المبيعات: {total_sales}💎\n'
            f'إجمالي الأرصدة: {total_balance}💎\n'
            f'</blockquote>'
        )
        bot.edit_message_text(text, uid, call.message.message_id, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "back_admin"}]]}))
    
    elif data == "advanced_settings":
        keyboard = [
            [
                {"text": "إدارة السحب", "callback_data": "toggle_withdraw"},
                {"text": "وضع الصيانة", "callback_data": "toggle_maintenance"}
            ],
            [
                {"text": "إعداد القناة", "callback_data": "set_channel"},
                {"text": "طرق الدفع", "callback_data": "set_payment_methods"}
            ],
            [{"text": "رجوع", "callback_data": "back_admin"}]
        ]
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SETTINGS}">⚙️</tg-emoji> <b>الإعدادات المتقدمة</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    
    elif data == "toggle_withdraw":
        st = _cfg("withdraw_status")
        _set_cfg("withdraw_status", "off" if st == "on" else "on")
        bot.answer_callback_query(call.id, f"السحب {'مغلق' if st == 'on' else 'مفتوح'} الآن")
    
    elif data == "toggle_maintenance":
        st = _cfg("maintenance_mode")
        _set_cfg("maintenance_mode", "off" if st == "on" else "on")
        bot.answer_callback_query(call.id, f"وضع الصيانة {'مغلق' if st == 'on' else 'مفتوح'} الآن")
    
    elif data == "set_channel":
        user_states[uid] = {"action": "set_channel"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_GLOBE}">📝</tg-emoji> <b>أرسل معرف القناة (@username)</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_set_channel)
    
    elif data == "set_payment_methods":
        user_states[uid] = {"action": "set_payment_methods"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_MAIL}">📝</tg-emoji> <b>أرسل طرق الدفع مفصولة بفواصل</b>\n<blockquote>مثال: فودافون كاش,تحويل بنكي,شام كاش,نجوم</blockquote>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_set_payment_methods)
    
    elif data == "search_user":
        user_states[uid] = {"action": "search_user"}
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_TARGET}">🔍</tg-emoji> <b>أرسل ID المستخدم</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_search_user)
    
    elif data == "restart_bot":
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>جاري إعادة التشغيل...</b>', uid, call.message.message_id, parse_mode='HTML')
        os._exit(0)
    
    elif data == "back_admin":
        bot.edit_message_text(f'<tg-emoji emoji-id="{EMOJI_SETTINGS}">⚙️</tg-emoji> <b>لوحة التحكم</b>', uid, call.message.message_id, parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))

def _handle_coupon_input(msg):
    uid = msg.from_user.id
    if uid in user_states and user_states[uid].get("action") == "buy_with_coupon":
        code = msg.text.strip()
        pid = user_states[uid]["product_id"]
        user_states[uid]["coupon"] = code
        process_purchase(uid, pid, msg, code)
    else:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>انتهت الجلسة</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))

def _handle_coupon_activation(msg):
    uid = msg.from_user.id
    code = msg.text.strip()
    cur.execute("SELECT * FROM coupons WHERE code = ?", (code,))
    coupon = cur.fetchone()
    if coupon:
        _, code, disc, mx, used, exp, min_p, active = coupon
        if active and used < mx and int(time.time()) < exp:
            bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>كوبون صالح!</b>\n<blockquote expandable>\nالخصم: {disc}%\nصالح حتى: {format_time(exp)}\nالحد الأدنى: {min_p} {_cfg("currency")}\nالمتبقي: {mx - used}\n</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
        else:
            bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>الكوبون منتهي</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
    else:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>كوبون غير صالح</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))

def _handle_special_code_input(msg):
    uid = msg.from_user.id
    code = msg.text.strip().upper()
    cur.execute("SELECT code, points, is_active FROM special_codes WHERE code = ?", (code,))
    row = cur.fetchone()
    if not row or not row[2]:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>كود غير صالح</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
        return
    _, points, _active = row
    # الكود صحيح لكن غير كافٍ لوحده: لازم يكون الأدمن صرّح لهذا المستخدم تحديداً
    # عبر أمر /grant، وإلا يُرفض حتى لو كان نص الكود صحيح.
    cur.execute("SELECT used FROM special_code_access WHERE code = ? AND user_id = ?", (code, uid))
    access = cur.fetchone()
    if not access:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">🚫</tg-emoji> <b>هذا الكود غير مصرّح لحسابك</b>\n<blockquote>تواصل مع @{DEVELOPER_USERNAME} إذا كنت تملك صلاحية استخدامه</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
        return
    if access[0]:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>سبق أن استخدمت هذا الكود</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
        return
    now = int(time.time())
    cur.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?", (points, points, uid))
    cur.execute("UPDATE special_code_access SET used = 1, used_at = ? WHERE code = ? AND user_id = ?", (now, code, uid))
    conn.commit()
    add_notification(uid, f"تم استخدام كود خاص: +{points} {_cfg('currency')}")
    bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_GIFT}">🎉</tg-emoji> <b>تم تفعيل الكود! حصلت على {points} {_cfg("currency")}</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
    try:
        bot.send_message(ADMIN_ID, f'<tg-emoji emoji-id="{EMOJI_KEY}">🔑</tg-emoji> <b>استخدام كود خاص</b>\n<blockquote>المستخدم: <code>{uid}</code>\nالكود: {code}\nالنقاط: {points}</blockquote>', parse_mode='HTML')
    except Exception:
        pass

def _handle_ticket_subject(msg):
    uid = msg.from_user.id
    subject = msg.text.strip()
    cur.execute("INSERT INTO support_tickets (user_id, subject, created_at) VALUES (?, ?, ?)", (uid, subject, int(time.time())))
    conn.commit()
    bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم فتح تذكرة الدعم</b>\n<blockquote>سنتواصل معك قريباً</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
    try:
        bot.send_message(ADMIN_ID, f'<tg-emoji emoji-id="{EMOJI_MAIL}">💬</tg-emoji> <b>تذكرة جديدة</b>\n<blockquote expandable>\nالمستخدم: <code>{uid}</code>\nالموضوع: {subject}\n</blockquote>', parse_mode='HTML')
    except:
        pass

def _handle_withdraw_details(msg):
    uid = msg.from_user.id
    details = msg.text.strip()
    if uid in user_states and user_states[uid].get("action") == "withdraw":
        method = user_states[uid]["method"]
        stats = get_user_stats(uid)
        min_withdraw = int(_cfg("min_withdraw"))
        amount = stats['balance']
        transfer_fee = int(_cfg("transfer_fee"))
        if transfer_fee > 0:
            amount -= transfer_fee
        if amount < min_withdraw:
            bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>المبلغ بعد الرسوم أقل من الحد الأدنى</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
            return
        cur.execute("INSERT INTO withdrawals (user_id, amount, method, details, created_at) VALUES (?, ?, ?, ?, ?)",
                    (uid, amount, method, details, int(time.time())))
        cur.execute("UPDATE users SET balance = 0 WHERE user_id = ?", (uid,))
        conn.commit()
        add_notification(uid, f"تم تقديم طلب سحب بقيمة {amount} {_cfg('currency')}")
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم تقديم طلب السحب!</b>\n<blockquote expandable>\nالمبلغ: {amount} {_cfg("currency")}\nالطريقة: {method}\nسنتواصل معك قريباً\n</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
        try:
            bot.send_message(ADMIN_ID, f'<tg-emoji emoji-id="{EMOJI_MONEY}">💰</tg-emoji> <b>طلب سحب جديد</b>\n<blockquote expandable>\nالمستخدم: <code>{uid}</code>\nالمبلغ: {amount} {_cfg("currency")}\nالطريقة: {method}\nالتفاصيل: {details}\n</blockquote>', parse_mode='HTML')
        except:
            pass
    user_states.pop(uid, None)

def _handle_review_comment(msg):
    uid = msg.from_user.id
    comment = msg.text.strip()
    if uid in user_states and user_states[uid].get("action") == "review_comment":
        pid = user_states[uid]["product_id"]
        rating = user_states[uid]["rating"]
        if comment == "تخطي":
            comment = ""
        cur.execute("INSERT INTO reviews (user_id, product_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                    (uid, pid, rating, comment, int(time.time())))
        conn.commit()
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_STAR}">✅</tg-emoji> <b>شكراً لتقييمك!</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _main_kb()}))
    user_states.pop(uid, None)

def _handle_search_product(msg):
    uid = msg.from_user.id
    query = msg.text.strip()
    cur.execute("SELECT id, name, price, stock FROM products WHERE is_active = 1 AND stock > 0 AND name LIKE ?", (f"%{query}%",))
    prods = cur.fetchall()
    if prods:
        keyboard = []
        for pid, name, price, stock in prods:
            keyboard.append([{"text": f"{name} | {price}💎 | {stock}قطعة", "callback_data": f"view_{pid}"}])
        keyboard.append([{"text": "رجوع", "callback_data": "shop"}])
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_TARGET}">🔍</tg-emoji> <b>نتائج البحث عن "{query}"</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    else:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>لا توجد نتائج</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": [[{"text": "رجوع", "callback_data": "shop"}]]}))

def _admin_add_product_name(msg):
    uid = msg.from_user.id
    name = msg.text.strip()
    user_states[uid] = {"action": "add_product", "name": name}
    msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SPARKLES}">📝</tg-emoji> <b>أرسل وصف المنتج</b>', parse_mode='HTML')
    bot.register_next_step_handler(msg, _admin_add_product_desc)

def _admin_add_product_desc(msg):
    uid = msg.from_user.id
    desc = msg.text.strip()
    user_states[uid]["desc"] = desc
    msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_MONEY}">💰</tg-emoji> <b>أرسل سعر المنتج</b>', parse_mode='HTML')
    bot.register_next_step_handler(msg, _admin_add_product_price)

def _admin_add_product_price(msg):
    uid = msg.from_user.id
    try:
        price = int(msg.text)
        user_states[uid]["price"] = price
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_MONEY}">💰</tg-emoji> <b>أرسل السعر الأصلي (أو 0)</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_add_product_original_price)
    except:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رقم غير صالح</b>', parse_mode='HTML')

def _admin_add_product_original_price(msg):
    uid = msg.from_user.id
    try:
        oprice = int(msg.text)
        user_states[uid]["oprice"] = oprice
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_LIST}">📦</tg-emoji> <b>أرسل الكمية</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_add_product_stock)
    except:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رقم غير صالح</b>', parse_mode='HTML')

def _admin_add_product_stock(msg):
    uid = msg.from_user.id
    try:
        stock = int(msg.text)
        user_states[uid]["stock"] = stock
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_LIST}">📂</tg-emoji> <b>أرسل التصنيف</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_add_product_category)
    except:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رقم غير صالح</b>', parse_mode='HTML')

def _admin_add_product_category(msg):
    uid = msg.from_user.id
    cat = msg.text.strip()
    user_states[uid]["category"] = cat
    keyboard = [
        [
            {"text": "تلقائي", "callback_data": "delivery_auto"},
            {"text": "يدوي", "callback_data": "delivery_manual"}
        ]
    ]
    msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_ROCKET}">🚚</tg-emoji> <b>اختر نوع التوصيل</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    user_states[uid]["msg_id"] = msg.message_id

@bot.callback_query_handler(func=lambda c: c.data.startswith("delivery_"))
def _admin_delivery_cb(call):
    uid = call.from_user.id
    if uid != ADMIN_ID:
        return
    delivery = "auto" if call.data == "delivery_auto" else "manual"
    user_states[uid]["delivery"] = delivery
    bot.delete_message(uid, call.message.message_id)
    if delivery == "auto":
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_MAIL}">📝</tg-emoji> <b>أرسل المحتوى الذي سيتم تسليمه</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_add_product_content)
    else:
        msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_MAIL}">🖼</tg-emoji> <b>أرسل صورة المنتج (أو تخطي)</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, _admin_add_product_image)

def _admin_add_product_content(msg):
    uid = msg.from_user.id
    content = msg.text.strip()
    user_states[uid]["content"] = content
    msg = bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_MAIL}">🖼</tg-emoji> <b>أرسل صورة المنتج (أو تخطي)</b>', parse_mode='HTML')
    bot.register_next_step_handler(msg, _admin_add_product_image)

def _admin_add_product_image(msg):
    uid = msg.from_user.id
    image_id = None
    if msg.photo:
        image_id = msg.photo[-1].file_id
    user_states[uid]["image_id"] = image_id
    data = user_states[uid]
    disc = 0
    if data["oprice"] > data["price"]:
        disc = int((1 - data["price"] / data["oprice"]) * 100)
    cur.execute("""INSERT INTO products (name, description, price, original_price, stock, delivery_type, content, category, image_id, added_at, discount_percent)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data["name"], data["desc"], data["price"], data["oprice"], data["stock"],
                 data["delivery"], data.get("content"), data["category"], data.get("image_id"),
                 int(time.time()), disc))
    conn.commit()
    bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم إضافة المنتج بنجاح!</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))
    user_states.pop(uid, None)

def _admin_set_daily_points(msg):
    try:
        v = int(msg.text)
        _set_cfg("daily_points", v)
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم التحديث</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))
    except:
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رقم غير صالح</b>', parse_mode='HTML')

def _admin_set_ref_points(msg):
    try:
        v = int(msg.text)
        _set_cfg("ref_points", v)
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم التحديث</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))
    except:
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رقم غير صالح</b>', parse_mode='HTML')

def _admin_set_welcome_bonus(msg):
    try:
        v = int(msg.text)
        _set_cfg("welcome_bonus", v)
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم التحديث</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))
    except:
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>رقم غير صالح</b>', parse_mode='HTML')

def _admin_make_link(msg):
    try:
        pts, uses, hours = map(int, msg.text.split())
        expire = int(time.time()) + hours * 3600
        code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        cur.execute("INSERT INTO links (code, points, max_uses, expire_at, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (code, pts, uses, expire, ADMIN_ID, int(time.time())))
        conn.commit()
        link = f"https://t.me/{BOT_USERNAME}?start={code}"
        keyboard = [[{"text": "الرابط", "url": link}]]
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم إنشاء الرابط</b>\n<blockquote>{link}</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": keyboard}))
    except:
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>صيغة خاطئة</b>', parse_mode='HTML')

def _admin_add_coupon(msg):
    try:
        disc, uses, hours, min_p = map(int, msg.text.split())
        expire = int(time.time()) + hours * 3600
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        cur.execute("INSERT INTO coupons (code, discount_percent, max_uses, expire_at, min_purchase) VALUES (?, ?, ?, ?, ?)",
                    (code, disc, uses, expire, min_p))
        conn.commit()
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>كوبون جديد</b>\n<blockquote expandable>\nالكود: <code>{code}</code>\nالخصم: {disc}%\nصالح: {hours} ساعة\nحد أدنى: {min_p}\n</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))
    except:
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>صيغة خاطئة</b>', parse_mode='HTML')

def _admin_broadcast(msg):
    uid = msg.from_user.id
    target = user_states[uid].get("target", "all")
    success, fail = 0, 0
    
    if target == "all":
        cur.execute("SELECT user_id FROM users")
    elif target == "premium":
        cur.execute("SELECT user_id FROM users WHERE is_premium = 1")
    else:
        cur.execute("SELECT user_id FROM users WHERE is_banned = 0")
    
    users = cur.fetchall()
    for u in users:
        try:
            if msg.photo:
                bot.send_photo(u[0], msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.video:
                bot.send_video(u[0], msg.video.file_id, caption=msg.caption or "")
            elif msg.text:
                bot.send_message(u[0], msg.text, parse_mode='HTML')
            success += 1
        except:
            fail += 1
    
    bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم البث</b>\n<blockquote expandable>\nنجح: {success}\nفشل: {fail}\n</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))
    del user_states[uid]

def _admin_set_channel(msg):
    channel = msg.text.strip().replace("@", "")
    _set_cfg("channel_username", channel)
    _set_cfg("force_join", "on")
    bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم تعيين القناة @{channel}</b>\n<blockquote>تم تفعيل الاشتراك الإجباري</blockquote>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))

def _admin_set_payment_methods(msg):
    methods = msg.text.strip()
    _set_cfg("payment_methods", methods)
    bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم تحديث طرق الدفع</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))

def _admin_search_user(msg):
    try:
        target_id = int(msg.text)
        cur.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
        user = cur.fetchone()
        if user:
            _, bal, earned, spent, last_daily, ref, ref_count, warnings, banned, premium, premium_until, joined, uname, lang = user
            text = (
                f'<tg-emoji emoji-id="{EMOJI_HEART}">👤</tg-emoji> <b>معلومات المستخدم</b>\n'
                f'<blockquote expandable>\n'
                f'ID: <code>{target_id}</code>\n'
                f'الرصيد: {bal}\n'
                f'الإيرادات: {earned}\n'
                f'المشتريات: {spent}\n'
                f'الإحالات: {ref_count}\n'
                f'مميز: {"✅" if premium else "❌"}\n'
                f'محظور: {"✅" if banned else "❌"}\n'
                f'انضم: {format_time(joined)}\n'
                f'</blockquote>'
            )
            keyboard = []
            if not banned:
                keyboard.append([{"text": "حظر", "callback_data": f"ban_user_{target_id}"}])
            else:
                keyboard.append([{"text": "فك حظر", "callback_data": f"unban_user_{target_id}"}])
            keyboard.append([{"text": "تعديل رصيد", "callback_data": f"edit_balance_{target_id}"}])
            keyboard.append([{"text": "رجوع", "callback_data": "back_admin"}])
            bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=json.dumps({"inline_keyboard": keyboard}))
        else:
            bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>المستخدم غير موجود</b>', parse_mode='HTML')
    except:
        bot.send_message(msg.chat.id, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>ID غير صالح</b>', parse_mode='HTML')

@bot.message_handler(commands=["shlhom"])
def _cmd_shlhom(msg):
    uid = msg.from_user.id
    if is_admin(uid):
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_SETTINGS}">⚙️</tg-emoji> <b>لوحة التحكم</b>', parse_mode='HTML', reply_markup=json.dumps({"inline_keyboard": _admin_kb()}))
    else:
        bot.send_message(uid, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>غير مصرح لك</b>', parse_mode='HTML')

@bot.message_handler(commands=["id"])
def _cmd_id(msg):
    bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_TARGET}">🆔</tg-emoji> <b>معرفك:</b> <code>{msg.from_user.id}</code>', parse_mode='HTML')

@bot.message_handler(commands=["grant"])
def _cmd_grant(msg):
    """تصريح مستخدم معيّن باستخدام كود خاص. الاستخدام: /grant <الكود> <آيدي المستخدم>"""
    uid = msg.from_user.id
    if not is_admin(uid):
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>غير مصرح لك</b>', parse_mode='HTML')
        return
    parts = msg.text.split()
    if len(parts) != 3:
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_WARNING}">⚠️</tg-emoji> <b>الاستخدام:</b>\n<code>/grant الكود آيدي_المستخدم</code>', parse_mode='HTML')
        return
    code = parts[1].strip().upper()
    try:
        target_id = int(parts[2].strip())
    except ValueError:
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>آيدي غير صالح</b>', parse_mode='HTML')
        return
    cur.execute("SELECT points FROM special_codes WHERE code = ?", (code,))
    row = cur.fetchone()
    if not row:
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>هذا الكود غير موجود</b>', parse_mode='HTML')
        return
    cur.execute("INSERT OR IGNORE INTO special_code_access (code, user_id, used, granted_at) VALUES (?, ?, 0, ?)",
                (code, target_id, int(time.time())))
    conn.commit()
    bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم التصريح</b>\n<blockquote>الكود: {code}\nالنقاط: {row[0]}\nالمستخدم: <code>{target_id}</code>\n</blockquote>\nيمكنه الآن إدخال الكود من قائمة المكافآت ← 🔑 كود خاص.', parse_mode='HTML')
    try:
        bot.send_message(target_id, f'<tg-emoji emoji-id="{EMOJI_KEY}">🔑</tg-emoji> <b>تم منحك صلاحية استخدام كود خاص!</b>\n<blockquote>ادخل قائمة المكافآت ← 🔑 كود خاص، وأرسل الكود الذي أعطاك إياه الأدمن.</blockquote>', parse_mode='HTML')
    except Exception:
        pass

@bot.message_handler(commands=["revoke"])
def _cmd_revoke(msg):
    """إلغاء تصريح مستخدم لكود خاص. الاستخدام: /revoke <الكود> <آيدي المستخدم>"""
    uid = msg.from_user.id
    if not is_admin(uid):
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>غير مصرح لك</b>', parse_mode='HTML')
        return
    parts = msg.text.split()
    if len(parts) != 3:
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_WARNING}">⚠️</tg-emoji> <b>الاستخدام:</b>\n<code>/revoke الكود آيدي_المستخدم</code>', parse_mode='HTML')
        return
    code = parts[1].strip().upper()
    try:
        target_id = int(parts[2].strip())
    except ValueError:
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>آيدي غير صالح</b>', parse_mode='HTML')
        return
    cur.execute("DELETE FROM special_code_access WHERE code = ? AND user_id = ?", (code, target_id))
    conn.commit()
    bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_SUCCESS}">✅</tg-emoji> <b>تم إلغاء تصريح</b> <code>{target_id}</code> <b>لكود</b> {code}', parse_mode='HTML')

@bot.message_handler(commands=["grants"])
def _cmd_grants(msg):
    """عرض المصرّح لهم بكود معيّن. الاستخدام: /grants <الكود>"""
    uid = msg.from_user.id
    if not is_admin(uid):
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_FAIL}">❌</tg-emoji> <b>غير مصرح لك</b>', parse_mode='HTML')
        return
    parts = msg.text.split()
    if len(parts) != 2:
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_WARNING}">⚠️</tg-emoji> <b>الاستخدام:</b>\n<code>/grants الكود</code>', parse_mode='HTML')
        return
    code = parts[1].strip().upper()
    cur.execute("SELECT user_id, used FROM special_code_access WHERE code = ? ORDER BY granted_at DESC LIMIT 50", (code,))
    rows = cur.fetchall()
    if not rows:
        bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_WARNING}">⚠️</tg-emoji> <b>لا يوجد مصرّح لهم بهذا الكود بعد</b>', parse_mode='HTML')
        return
    lines = "\n".join(f'• <code>{u}</code> - {"استخدمه" if used else "لم يستخدمه بعد"}' for u, used in rows)
    bot.reply_to(msg, f'<tg-emoji emoji-id="{EMOJI_KEY}">🔑</tg-emoji> <b>المصرّح لهم بكود {code}</b>\n<blockquote expandable>\n{lines}\n</blockquote>', parse_mode='HTML')

print(f"""
╔══════════════════════════════════════╗
║     🤖 {_cfg('bot_name')} قيد التشغيل...      ║
║     👨‍💻 المطور: @{DEVELOPER_USERNAME}       ║
║     📱 اليوزر: @{BOT_USERNAME}              ║
╚══════════════════════════════════════╝
""")

bot.infinity_polling()