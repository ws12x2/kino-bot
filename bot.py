"""
Kod orqali post (video/rasm/matn) yuboruvchi Telegram bot.

ISHLASH PRINSIPI:

ADMIN uchun (/add):
    1) Botga /add buyrug'ini yuboring
    2) Bot "postni yuboring" deb so'raydi -> siz istalgan turdagi xabar
       yuborasiz: video, rasm, hujjat, yoki oddiy matn
    3) Bot "endi kodlarni yozing" deb so'raydi -> siz shu post uchun
       BIR NECHTA kodni vergul bilan ajratib yozasiz, masalan:
           12,avatar,avatr,avatar2
       (bir nechta kod yozish - foydalanuvchi imlo xatolarini hisobga olish
       uchun, masalan "avatar" ham, "avatr" ham shu postga olib kelishi uchun)
    4) Bot "endi tugma nomini yozing" deb so'raydi -> "🎬 Barcha postlar"
       ro'yxatida shu post qaysi nom bilan tugma sifatida chiqishini yozasiz,
       masalan: Avatar: Suvning yo'li (2022)
    5) Bot "✅ Saqlandi" deb javob beradi

    Bekor qilish uchun istalgan vaqtda /cancel yozing.

ADMIN PANEL (/admin):
    Botga /admin buyrug'ini yuborsangiz, quyidagi imkoniyatlarga ega
    inline tugmali panel chiqadi:
        ➕ Yangi post qo'shish  - /add bilan bir xil oqim, faqat tugma orqali
        ✏️ Postlarni tahrirlash - mavjud postlar ro'yxati chiqadi, har birini
                                   tanlab: kodlarini almashtirish, tugma
                                   nomini o'zgartirish yoki postni butunlay
                                   o'chirish mumkin

FOYDALANUVCHI uchun:
    Botga shunchaki kodni yozadi, masalan: avatar
    -> bot mos postni (qanday turda saqlangan bo'lishidan qat'i nazar -
       video, rasm yoki matn) topib, foydalanuvchiga yuboradi.

    ADMINDAN BOSHQA (oddiy) foydalanuvchilar bilan suhbatda, bot har safar
    xabar yuborgach, o'zidan oldingi xabarni EMAS, balki O'ZIDAN OLDINGI
    XABARDAN OLDINGI xabarni avtomatik o'chiradi - shu orqali har doim
    so'nggi 2 ta xabar (foydalanuvchining kodi + bot javobi) ko'rinishda
    qoladi, undan oldingi tarix esa tozalanadi. Pastdagi tugmalar har bir
    javobga qayta biriktiriladi, shuning uchun ular hech qachon yo'qolmaydi.

MUHIM: bot faylni hech qachon o'ziga yuklamaydi - faqat admin bilan bo'lgan
suhbatdagi asl xabarni Telegram serverlari orqali NUSXALAB (copy_message)
foydalanuvchiga yuboradi. Shu sababli fayl hajmi (hatto to'liq kino bo'lsa
ham) muammo qilmaydi.

O'RNATISH:
    pip install python-telegram-bot==21.6

ISHGA TUSHIRISH:
    1) BOT_TOKEN ni pastda o'z tokeningizga almashtiring (@BotFather dan oling)
    2) ADMIN_IDS ro'yxatiga o'z Telegram ID raqamingizni yozing
       (ID ni bilish uchun @userinfobot ga /start yuboring)
    3) python bot.py
"""

import asyncio
import http.server
import logging
import os
import sqlite3
import threading
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.error import ChatMigrated
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    filters,
)

# ============ SOZLAMALAR ============
# BOT_TOKEN va DB_PATH avval Railway/server "Variables" bo'limidan o'qiladi
# (agar bo'lmasa, pastdagi standart qiymat ishlatiladi - masalan kompyuterda
# sinab ko'rish uchun).
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8993809045:AAEDrdA1ZqqIl17LrC0rPvwWwv-NohkB4HY")
ADMIN_IDS = [5393636771]                    # Sizning Telegram user ID(lar)ingiz
DB_PATH = os.environ.get("DB_PATH", "movies.db")

# SAQLASH GURUHI (ixtiyoriy, lekin QATTIQ TAVSIYA ETILADI):
# Agar bu sozlansa, /add orqali qo'shilgan har bir post AVTOMATIK shu
# guruhga nusxalanadi va kelajakda o'sha yerdan yuboriladi - shuning uchun
# admin o'zining shaxsiy bot-chatini tozalab tashlasa ham, postlar
# GURUHDA xavfsiz qoladi. Sozlash uchun: guruh yarating, botni admin
# qilib qo'shing, guruhda /chatid buyrug'ini yuboring va chiqqan raqamni
# shu yerga (yoki STORAGE_CHAT_ID muhit o'zgaruvchisiga) yozing.
# Sozlanmasa - eski usul (postlar admin bilan shaxsiy chatda saqlanadi)
# davom etadi.
_storage_chat_id_raw = os.environ.get("STORAGE_CHAT_ID", "").strip()
STORAGE_CHAT_ID = int(_storage_chat_id_raw) if _storage_chat_id_raw.lstrip("-").isdigit() else None

BTN_KINOLAR = "🎬 Barcha postlar"
BTN_VIP = "⭐ VIP"
BTN_GAMES = "🎮 O'yinlar"
BTN_STATUS = "👤 Mening statusim"
VIP_CODE = "VIP"   # Admin qaysi postga shu kodni bersa ("vip" deb yozsa ham
                    # bo'ladi - kodlar avtomatik katta harfga o'giriladi),
                    # o'sha post ⭐ VIP tugmasi bosilganda yuboriladi.
VIP_WELCOME_CODE = "VIP1"  # Admin VIP status berganda, yangi VIP foydalanuvchiga
                            # avtomatik shu kodli post yuboriladi (masalan VIP
                            # kanaliga taklifnoma yoki tarif haqida batafsil post).
VIP_EXPIRED_CODE = "VIP2"  # VIP muddati tugaganda, foydalanuvchiga avtomatik
                            # shu kodli post yuboriladi (masalan qayta VIP
                            # olish haqida taklif/reklama posti).

CATEGORY_MOVIE = "movie"
CATEGORY_GAME = "game"
CATEGORY_SYSTEM = "system"  # VIP1/VIP2 kabi "tizim postlari" - hech qanday
                             # ro'yxatda yoki kod qidiruvida ko'rinmaydi,
                             # faqat bot avtomatik yuborganda ishlaydi.

VISIBILITY_ALL = "all"       # Hammaga ko'rinadi
VISIBILITY_VIP = "vip"       # Faqat VIP foydalanuvchilarga
VISIBILITY_ADMIN = "admin"   # Faqat adminlarga (boshqalarga butunlay "ko'rinmas")
VISIBILITY_LABELS = {
    VISIBILITY_ALL: "👥 Hammaga",
    VISIBILITY_VIP: "⭐ Faqat VIP'lar",
    VISIBILITY_ADMIN: "👑 Faqat adminlar",
}
# =====================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WAITING_POST, WAITING_CODES, WAITING_BUTTON_NAME, WAITING_EXTRA_LINK, WAITING_EXTRA_LINK_NAME, WAITING_VISIBILITY = range(6)
# ConversationHandler holatlari (/add oqimi uchun)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ============ BAZA ============

def _migrate_codes_table_if_needed(cur):
    """
    Eski versiyalarda 'codes' jadvalida 'id' ustuni bo'lmagan bo'lishi mumkin.
    Agar shunday bo'lsa, jadvalni ma'lumotlarni yo'qotmasdan yangi tuzilishga
    avtomatik o'tkazadi.
    """
    cur.execute("PRAGMA table_info(codes)")
    columns = [row[1] for row in cur.fetchall()]
    if not columns:
        return  # jadval hali umuman yaratilmagan - keyin normal yaratiladi
    if "id" in columns:
        return  # allaqachon yangi tuzilishda

    logger.info("Eski 'codes' jadvali topildi, yangi tuzilishga o'tkazilmoqda...")
    cur.execute("ALTER TABLE codes RENAME TO codes_old")
    cur.execute(
        """
        CREATE TABLE codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            post_id INTEGER NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts (post_id)
        )
        """
    )
    cur.execute("INSERT INTO codes (code, post_id) SELECT code, post_id FROM codes_old")
    cur.execute("DROP TABLE codes_old")
    logger.info("Migratsiya tugadi.")


def _migrate_users_table_if_needed(cur):
    """Eski 'users' jadvalida ba'zi ustunlar bo'lmasligi mumkin - qo'shamiz."""
    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]
    if not columns:
        return
    if "username" not in columns:
        logger.info("'users' jadvaliga 'username' ustuni qo'shilmoqda...")
        cur.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "vip_until" not in columns:
        logger.info("'users' jadvaliga 'vip_until' ustuni qo'shilmoqda...")
        cur.execute("ALTER TABLE users ADD COLUMN vip_until TIMESTAMP")
    if "vip_channel_removed" not in columns:
        logger.info("'users' jadvaliga 'vip_channel_removed' ustuni qo'shilmoqda...")
        cur.execute("ALTER TABLE users ADD COLUMN vip_channel_removed INTEGER DEFAULT 0")
    if "ads_excluded" not in columns:
        logger.info("'users' jadvaliga 'ads_excluded' ustuni qo'shilmoqda...")
        cur.execute("ALTER TABLE users ADD COLUMN ads_excluded INTEGER DEFAULT 0")


def _migrate_posts_table_if_needed(cur):
    """Eski 'posts' jadvalida ba'zi ustunlar bo'lmasligi mumkin - qo'shamiz."""
    cur.execute("PRAGMA table_info(posts)")
    columns = [row[1] for row in cur.fetchall()]
    if not columns:
        return
    if "button_name" not in columns:
        logger.info("'posts' jadvaliga 'button_name' ustuni qo'shilmoqda...")
        cur.execute("ALTER TABLE posts ADD COLUMN button_name TEXT")
    if "extra_button_text" not in columns:
        logger.info("'posts' jadvaliga 'extra_button_text' ustuni qo'shilmoqda...")
        cur.execute("ALTER TABLE posts ADD COLUMN extra_button_text TEXT")
    if "extra_button_url" not in columns:
        logger.info("'posts' jadvaliga 'extra_button_url' ustuni qo'shilmoqda...")
        cur.execute("ALTER TABLE posts ADD COLUMN extra_button_url TEXT")
    if "category" not in columns:
        logger.info("'posts' jadvaliga 'category' ustuni qo'shilmoqda...")
        # Standart qiymat 'movie' - eski postlarning barchasi "Barcha postlar"da qolishi uchun
        cur.execute("ALTER TABLE posts ADD COLUMN category TEXT DEFAULT 'movie'")
    if "visibility" not in columns:
        logger.info("'posts' jadvaliga 'visibility' ustuni qo'shilmoqda...")
        # Standart qiymat 'all' - eski postlar hammaga ko'rinishda qolishi uchun
        cur.execute("ALTER TABLE posts ADD COLUMN visibility TEXT DEFAULT 'all'")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            post_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            preview TEXT,
            button_name TEXT,
            extra_button_text TEXT,
            extra_button_url TEXT,
            category TEXT DEFAULT 'movie',
            visibility TEXT DEFAULT 'all',
            added_by INTEGER
        )
        """
    )
    _migrate_posts_table_if_needed(cur)
    _migrate_codes_table_if_needed(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            post_id INTEGER NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts (post_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            vip_until TIMESTAMP,
            vip_channel_removed INTEGER DEFAULT 0,
            ads_excluded INTEGER DEFAULT 0,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _migrate_users_table_if_needed(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            code TEXT,
            found INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcast_always (
            chat_id INTEGER PRIMARY KEY,
            label TEXT,
            kind TEXT DEFAULT 'user',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcast_always (
            chat_id INTEGER PRIMARY KEY,
            label TEXT,
            kind TEXT DEFAULT 'user',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def get_setting(key: str, default=None):
    """
    Sozlamani o'qiydi. Agar 'settings' jadvali hali yaratilmagan bo'lsa
    (masalan bot birinchi marta, hali init_db() chaqirilmasdan oldin,
    zaxiradan tiklashga urinayotganda) - xatoga uchramasdan shunchaki
    standart qiymatni qaytaradi.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO settings (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_storage_chat_id():
    """
    Baza (saqlash) guruhining chat_id'sini qaytaradi.
    Avval bazada admin panel orqali sozlangan qiymatni tekshiradi,
    topilmasa kod ichidagi STORAGE_CHAT_ID standart qiymatiga qaytadi.
    """
    value = get_setting("storage_chat_id")
    if value:
        try:
            return int(value)
        except ValueError:
            pass
    return STORAGE_CHAT_ID


def get_vip_channel_id():
    """VIP kanal sifatida sozlangan chat_id'ni qaytaradi (sozlanmagan bo'lsa None)."""
    value = get_setting("vip_channel_id")
    if value:
        try:
            return int(value)
        except ValueError:
            pass
    return None


def get_auto_accept_channel_id():
    """
    "Avto qo'shish" kanali sifatida sozlangan chat_id'ni qaytaradi
    (sozlanmagan bo'lsa None). Bu kanalga yuborilgan HAR QANDAY qo'shilish
    so'rovi - VIP statusidan qat'i nazar - avtomatik tasdiqlanadi, va
    (VIP kanaldan farqli o'laroq) hech kim keyinchalik avtomatik chiqarib
    yuborilmaydi.
    """
    value = get_setting("auto_accept_channel_id")
    if value:
        try:
            return int(value)
        except ValueError:
            pass
    return None


def save_post(
    chat_id: int,
    message_id: int,
    preview: str,
    button_name: str,
    added_by: int,
    extra_button_text: str = None,
    extra_button_url: str = None,
    category: str = CATEGORY_MOVIE,
    visibility: str = VISIBILITY_ALL,
) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO posts
           (chat_id, message_id, preview, button_name, extra_button_text, extra_button_url, category, visibility, added_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (chat_id, message_id, preview, button_name, extra_button_text, extra_button_url, category, visibility, added_by),
    )
    post_id = cur.lastrowid
    conn.commit()
    conn.close()
    return post_id


def save_codes(codes: list, post_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for code in codes:
        # Kod allaqachon mavjud bo'lsa - post_id'ni yangilaymiz (qayta bog'lash),
        # aks holda yangi qator qo'shamiz (insert tartibi id orqali saqlanadi).
        cur.execute(
            """INSERT INTO codes (code, post_id) VALUES (?, ?)
               ON CONFLICT(code) DO UPDATE SET post_id = excluded.post_id""",
            (code.strip().upper(), post_id),
        )
    conn.commit()
    conn.close()


def get_post_by_code(code: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """SELECT p.chat_id, p.message_id, p.preview, p.extra_button_text, p.extra_button_url,
                  COALESCE(p.category, 'movie'), COALESCE(p.visibility, 'all')
           FROM codes c JOIN posts p ON c.post_id = p.post_id
           WHERE c.code = ?""",
        (code.strip().upper(),),
    )
    row = cur.fetchone()
    conn.close()
    return row  # (chat_id, message_id, preview, extra_button_text, extra_button_url, category, visibility) yoki None


def delete_code(code: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM codes WHERE code = ?", (code.strip().upper(),))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def _post_sort_key(code: str, category: str, post_id: int):
    """
    Postlarni tartiblash uchun kalit hisoblaydi:
    - 'movie' kategoriyasida: kod TO'LIQ raqamdan iborat bo'lsa (masalan "1", "10"),
      o'sha raqam bo'yicha o'sish tartibida joylashadi (1, 2, ..., 10, ...).
    - 'game' kategoriyasida: kod "G" harfi bilan boshlanib, undan keyin raqam
      kelsa (masalan "G1", "G2", "G10"), o'sha raqam bo'yicha tartiblanadi.
    - Bu shartlarga mos kelmagan kodlar (masalan "avatar", "pubg") - RO'YXAT
      OXIRIGA tushadi, o'z orasida qo'shilgan tartibida (post_id bo'yicha) qoladi.
    """
    c = (code or "").strip().upper()
    if category == CATEGORY_GAME:
        if c.startswith("G") and c[1:].isdigit():
            return (0, int(c[1:]), post_id)
        return (1, 0, post_id)
    else:
        if c.isdigit():
            return (0, int(c), post_id)
        return (1, 0, post_id)


def list_all_codes(category: str = CATEGORY_MOVIE):
    """
    Berilgan kategoriyadagi ('movie' yoki 'game') har bir post uchun faqat
    BIRINCHI qo'shilgan kodni qaytaradi (soddalik uchun). Tugma matni
    sifatida admin kiritgan 'button_name' ishlatiladi; agar u kiritilmagan
    bo'lsa (eski postlar), avtomatik 'preview' ishlatiladi. 'visibility'
    ustuni ham qaytariladi - chaqiruvchi tomon buni ko'ruvchining
    huquqiga qarab filtrlashi kerak (filter_rows_by_visibility funksiyasi).

    Natija RAQAMLI KOD bo'yicha tartiblangan holda qaytariladi (pastdagi
    _post_sort_key izohiga qarang).
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """SELECT c.code, COALESCE(p.button_name, p.preview) AS label, p.post_id,
                  COALESCE(p.visibility, 'all')
           FROM codes c JOIN posts p ON c.post_id = p.post_id
           WHERE c.id = (SELECT MIN(id) FROM codes WHERE post_id = p.post_id)
             AND COALESCE(p.category, 'movie') = ?
           ORDER BY p.post_id""",
        (category,),
    )
    rows = cur.fetchall()
    conn.close()

    rows.sort(key=lambda row: _post_sort_key(row[0], category, row[2]))
    return rows


def filter_rows_by_visibility(rows, viewer_id: int):
    """
    list_all_codes() natijasini (code, label, post_id, visibility) ko'ruvchi
    huquqiga qarab filtrlaydi va (code, label, post_id) uchligini qaytaradi
    (build_posts_page_markup shu formatni kutadi).
    """
    if is_admin(viewer_id):
        allowed = {VISIBILITY_ALL, VISIBILITY_VIP, VISIBILITY_ADMIN}
    elif is_vip(viewer_id):
        allowed = {VISIBILITY_ALL, VISIBILITY_VIP}
    else:
        allowed = {VISIBILITY_ALL}

    return [(code, label, post_id) for code, label, post_id, vis in rows if vis in allowed]



    """Barcha postlarni (post_id, nom, kategoriya) ko'rinishida qaytaradi - admin panel uchun."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """SELECT post_id, COALESCE(button_name, preview) AS label, COALESCE(category, 'movie')
           FROM posts ORDER BY post_id"""
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_posts():
    """
    Barcha oddiy postlarni (post_id, nom, kategoriya) ko'rinishida qaytaradi -
    "Postlarni tahrirlash" admin bo'limi uchun. 'system' kategoriyasidagi
    postlar (VIP1/VIP2 kabi) BU YERGA QO'SHILMAYDI - ular faqat o'zlarining
    maxsus admin tugmalari (VIP boshlanish/tugash posti) orqali boshqariladi.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """SELECT post_id, COALESCE(button_name, preview) AS label, COALESCE(category, 'movie')
           FROM posts WHERE COALESCE(category, 'movie') != 'system' ORDER BY post_id"""
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_codes_for_post(post_id: int):
    """Berilgan post uchun barcha kodlarni ro'yxat sifatida qaytaradi."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT code FROM codes WHERE post_id = ? ORDER BY id", (post_id,))
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def replace_codes_for_post(post_id: int, codes: list):
    """Berilgan postning ESKI barcha kodlarini o'chirib, YANGI kodlar bilan almashtiradi."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM codes WHERE post_id = ?", (post_id,))
    conn.commit()
    conn.close()
    save_codes(codes, post_id)


def update_post_button_name(post_id: int, button_name: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE posts SET button_name = ? WHERE post_id = ?", (button_name, post_id))
    conn.commit()
    conn.close()


def update_post_link(post_id: int, extra_button_text, extra_button_url):
    """Postning link-tugmasini yangilaydi. None qiymatlar tugmani olib tashlaydi."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE posts SET extra_button_text = ?, extra_button_url = ? WHERE post_id = ?",
        (extra_button_text, extra_button_url, post_id),
    )
    conn.commit()
    conn.close()


def update_post_visibility(post_id: int, visibility: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE posts SET visibility = ? WHERE post_id = ?", (visibility, post_id))
    conn.commit()
    conn.close()


def get_post_details(post_id: int):
    """Bitta post haqida to'liq ma'lumot qaytaradi (admin tahrirlash paneli uchun)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """SELECT button_name, extra_button_text, extra_button_url,
                  COALESCE(visibility, 'all'), COALESCE(category, 'movie')
           FROM posts WHERE post_id = ?""",
        (post_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row  # (button_name, extra_button_text, extra_button_url, visibility, category) yoki None


def delete_post(post_id: int):
    """Postni va unga bog'liq BARCHA kodlarni butunlay o'chiradi."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM codes WHERE post_id = ?", (post_id,))
    cur.execute("DELETE FROM posts WHERE post_id = ?", (post_id,))
    conn.commit()
    conn.close()


def save_user(chat_id: int, username: str = None):
    """
    Botdan foydalangan har bir foydalanuvchini (reklama tarqatish va VIP
    berish uchun, username orqali qidirish uchun) eslab qoladi, shuningdek
    har bir murojaatni 'activity' jadvaliga yozib boradi (statistika/hisobot
    uchun - bugungi/oylik faol foydalanuvchilar sonini hisoblash uchun
    ishlatiladi).
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO users (chat_id, username) VALUES (?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET username = excluded.username""",
        (chat_id, username),
    )
    cur.execute(
        "INSERT INTO activity (chat_id, created_at) VALUES (?, CURRENT_TIMESTAMP)",
        (chat_id,),
    )
    conn.commit()
    conn.close()


def find_user_chat_id(identifier: str):
    """
    Admin kiritgan ID raqami yoki @username bo'yicha foydalanuvchining
    chat_id'sini topadi. Faqat botga kamida bir marta murojaat qilgan
    foydalanuvchilar orasidan qidiradi (chunki bot boshqa foydalanuvchi
    haqida hech narsa bilmaydi).
    """
    identifier = identifier.strip()
    if identifier.startswith("@"):
        identifier = identifier[1:]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if identifier.isdigit():
        cur.execute("SELECT chat_id FROM users WHERE chat_id = ?", (int(identifier),))
    else:
        cur.execute("SELECT chat_id FROM users WHERE username = ? COLLATE NOCASE", (identifier,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def set_vip(chat_id: int, days: int):
    """Foydalanuvchiga berilgan kun sonicha VIP status beradi (hozirgi vaqtdan boshlab)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET vip_until = datetime('now', ?), vip_channel_removed = 0 WHERE chat_id = ?",
        (f"+{int(days)} days", chat_id),
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def get_vip_until(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT vip_until FROM users WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_username(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_vip_users():
    """Hozir FAOL VIP statusga ega barcha foydalanuvchilarni (muddati eng
    yaqin tugaydigani birinchi) qaytaradi: (chat_id, username, vip_until)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """SELECT chat_id, username, vip_until FROM users
           WHERE vip_until IS NOT NULL AND vip_until > datetime('now')
           ORDER BY vip_until ASC"""
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_vip_users():
    """Hozir VIP muddati faol bo'lgan barcha foydalanuvchilarni (chat_id, username, vip_until)
    ko'rinishida, tugash sanasi bo'yicha o'sish tartibida qaytaradi."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """SELECT chat_id, username, vip_until FROM users
           WHERE vip_until IS NOT NULL AND vip_until > datetime('now')
           ORDER BY vip_until ASC"""
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def adjust_vip_days(chat_id: int, delta_days: int) -> bool:
    """
    Foydalanuvchining VIP tugash sanasiga berilgan kun sonini qo'shadi
    (delta_days manfiy bo'lsa - ayiradi). Agar hozircha VIP bo'lmasa,
    hozirgi vaqtdan boshlab hisoblanadi.

    - Agar muddat UZAYTIRILSA (delta_days > 0): 'vip_channel_removed'
      bayrog'i 0 ga qaytariladi - shunda kelajakda bu YANGI muddat ham
      tugaganda, bot buni albatta payqab, kanaldan chiqarish/VIP2 xabarini
      yuborishni bajaradi (aks holda eski bayroq saqlanib qolib, ikkinchi
      marta tugashi butunlay e'tiborsiz qolib ketishi mumkin edi).
    - Qaytaradi: True - agar shu amaldan keyin VIP muddati o'tib ketgan
      (darhol tugagan) bo'lsa, aks holda False. Buni chaqiruvchi tomon
      darhol _process_single_vip_expiry chaqirish uchun ishlatishi kerak.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT vip_until FROM users WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    current = row[0] if row else None
    modifier = f"{delta_days:+d} days"

    if current:
        cur.execute("UPDATE users SET vip_until = datetime(vip_until, ?) WHERE chat_id = ?", (modifier, chat_id))
    else:
        cur.execute("UPDATE users SET vip_until = datetime('now', ?) WHERE chat_id = ?", (modifier, chat_id))

    if delta_days > 0:
        cur.execute("UPDATE users SET vip_channel_removed = 0 WHERE chat_id = ?", (chat_id,))

    cur.execute(
        "SELECT vip_until IS NOT NULL AND vip_until <= datetime('now') FROM users WHERE chat_id = ?",
        (chat_id,),
    )
    row2 = cur.fetchone()
    became_expired = bool(row2[0]) if row2 else False

    conn.commit()
    conn.close()
    return became_expired


def revoke_vip(chat_id: int):
    """Foydalanuvchining VIP statusini butunlay bekor qiladi."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET vip_until = NULL WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def is_vip(chat_id: int) -> bool:
    """Adminlar HAR DOIM VIP hisoblanadi (cheksiz). Boshqalar uchun vip_until tekshiriladi."""
    if is_admin(chat_id):
        return True
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT vip_until IS NOT NULL AND vip_until > datetime('now') FROM users WHERE chat_id = ?",
        (chat_id,),
    )
    row = cur.fetchone()
    conn.close()
    return bool(row[0]) if row else False


def log_search(chat_id: int, code: str, found: bool):
    """Har bir kod qidiruvini (topilgan yoki topilmagan) 'searches' jadvaliga yozadi."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO searches (chat_id, code, found, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
        (chat_id, code, 1 if found else 0),
    )
    conn.commit()
    conn.close()


def get_stats():
    """Admin panel uchun hisobot ma'lumotlarini hisoblab qaytaradi."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    def scalar(query, params=()):
        cur.execute(query, params)
        return cur.fetchone()[0]

    stats = {
        "total_users": scalar("SELECT COUNT(*) FROM users"),
        "new_today": scalar("SELECT COUNT(*) FROM users WHERE date(first_seen) = date('now')"),
        "new_30d": scalar(
            "SELECT COUNT(*) FROM users WHERE first_seen >= datetime('now', '-30 days')"
        ),
        "active_today": scalar(
            "SELECT COUNT(DISTINCT chat_id) FROM activity WHERE date(created_at) = date('now')"
        ),
        "active_30d": scalar(
            "SELECT COUNT(DISTINCT chat_id) FROM activity WHERE created_at >= datetime('now', '-30 days')"
        ),
        "searches_today": scalar(
            "SELECT COUNT(*) FROM searches WHERE date(created_at) = date('now')"
        ),
        "searches_30d": scalar(
            "SELECT COUNT(*) FROM searches WHERE created_at >= datetime('now', '-30 days')"
        ),
    }
    conn.close()
    return stats


def get_all_user_chat_ids(exclude_admins: bool = True):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT chat_id FROM users")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    if exclude_admins:
        rows = [cid for cid in rows if cid not in ADMIN_IDS]
    return rows


def get_user_chat_ids_by_audience(audience: str):
    """
    Reklama tarqatish uchun foydalanuvchilarni auditoriya bo'yicha filtrlab qaytaradi.
    audience: 'regular' (faqat VIP bo'lmaganlar), 'vip' (faqat VIP'lar), 'all' (hammasi).
    Har uch holatda ham adminlar VA "reklama yuborilmaydiganlar" ro'yxatidagi
    foydalanuvchilar (ads_excluded=1) chiqarib tashlanadi - statusidan qat'i nazar.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if audience == "vip":
        cur.execute(
            """SELECT chat_id FROM users WHERE vip_until IS NOT NULL AND vip_until > datetime('now')
               AND COALESCE(ads_excluded, 0) = 0"""
        )
    elif audience == "regular":
        cur.execute(
            """SELECT chat_id FROM users WHERE (vip_until IS NULL OR vip_until <= datetime('now'))
               AND COALESCE(ads_excluded, 0) = 0"""
        )
    else:  # "all"
        cur.execute("SELECT chat_id FROM users WHERE COALESCE(ads_excluded, 0) = 0")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return [cid for cid in rows if cid not in ADMIN_IDS]


def get_excluded_ads_users():
    """Reklama yuborilmaydigan (ads_excluded=1) foydalanuvchilarni qaytaradi: (chat_id, username)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT chat_id, username FROM users WHERE COALESCE(ads_excluded, 0) = 1 ORDER BY chat_id"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def set_ads_excluded(chat_id: int, excluded: bool):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET ads_excluded = ? WHERE chat_id = ?", (1 if excluded else 0, chat_id))
    conn.commit()
    conn.close()


def add_always_send(chat_id: int, label: str, kind: str = "user"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO broadcast_always (chat_id, label, kind) VALUES (?, ?, ?)
           ON CONFLICT(chat_id) DO UPDATE SET label = excluded.label, kind = excluded.kind""",
        (chat_id, label, kind),
    )
    conn.commit()
    conn.close()


def remove_always_send(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM broadcast_always WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def get_always_send_list():
    """('Doim yuboriladi' ro'yxati) (chat_id, label, kind) - kind: 'user' yoki 'channel'."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT chat_id, label, kind FROM broadcast_always ORDER BY chat_id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_always_send_chat_ids():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT chat_id FROM broadcast_always")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def get_broadcast_recipients(audience: str):
    """
    Yakuniy reklama qabul qiluvchilar ro'yxati:
    (auditoriya bo'yicha filtrlangan foydalanuvchilar) + ("Doim yuboriladi"
    ro'yxatidagilar - foydalanuvchi HAM, kanal HAM bo'lishi mumkin).
    "Doim yuboriladi" ro'yxati "Reklama yuborilmaydiganlar" cheklovidan ham
    USTUN turadi - u yerga qo'shilgan chat har doim reklamani oladi.
    """
    audience_ids = set(get_user_chat_ids_by_audience(audience))
    always_ids = set(get_always_send_chat_ids())
    return sorted(audience_ids | always_ids)


async def resolve_broadcast_target(context: ContextTypes.DEFAULT_TYPE, message):
    """
    Admin "Doim yuboriladi" ro'yxatiga biror narsa qo'shmoqchi bo'lganda,
    yuborgan xabarini (forward, @username, havola yoki ID) FOYDALANUVCHI
    yoki KANAL sifatida aniqlashga harakat qiladi.

    Qaytaradi: (chat_id, label, kind) - muvaffaqiyatli bo'lsa
               (None, xato_matni, None) - muvaffaqiyatsiz bo'lsa
    """
    # 1) Forward qilingan xabar bo'lsa (odatda kanaldan) - undan chat'ni olamiz
    origin = getattr(message, "forward_origin", None)
    candidate_chat_id = None
    if origin is not None and getattr(origin, "chat", None) is not None:
        candidate_chat_id = origin.chat.id
    else:
        fwd_chat = getattr(message, "forward_from_chat", None)
        if fwd_chat is not None:
            candidate_chat_id = fwd_chat.id

    if candidate_chat_id is not None:
        try:
            chat = await context.bot.get_chat(candidate_chat_id)
        except Exception:
            return None, "❌ Bu kanal/guruhni aniqlab bo'lmadi.", None
        try:
            member = await context.bot.get_chat_member(candidate_chat_id, context.bot.id)
            is_chat_admin = member.status in ("administrator", "creator")
        except Exception:
            is_chat_admin = False
        if not is_chat_admin:
            return None, f"⚠️ Bot \"{chat.title or chat.id}\"da admin emas. Avval botni admin qiling.", None
        return candidate_chat_id, (chat.title or str(candidate_chat_id)), "channel"

    text = (message.text or "").strip()
    if not text:
        return None, "❌ Tushunarsiz format.", None

    # 2) Avval oddiy FOYDALANUVCHI sifatida qidiramiz (ID yoki @username)
    user_chat_id = find_user_chat_id(text)
    if user_chat_id is not None:
        username = get_username(user_chat_id)
        label = f"@{username}" if username else str(user_chat_id)
        return user_chat_id, label, "user"

    # 3) Foydalanuvchi topilmasa - KANAL/GURUH sifatida sinab ko'ramiz
    candidate = None
    if text.startswith("@"):
        candidate = text
    elif "t.me/" in text:
        path = text.split("t.me/", 1)[1].split("?")[0].strip("/")
        if path.startswith("+") or path.lower().startswith("joinchat"):
            return None, (
                "⚠️ Bu yopiq kanalning shaxsiy taklif havolasi - botlar bunday "
                "havolalar orqali kanalni aniqlay olmaydi.\n\nIltimos, o'sha "
                "kanaldan istalgan xabarni shu yerga FORWARD qiling."
            ), None
        candidate = f"@{path}"
    elif text.lstrip("-").isdigit():
        candidate = int(text)

    if candidate is None:
        return None, (
            "❌ Bunday foydalanuvchi topilmadi va bu kanal havolasiga ham "
            "o'xshamaydi.\n\nID/@username yozing, yoki kanaldan xabar forward qiling."
        ), None

    try:
        chat = await context.bot.get_chat(candidate)
    except Exception:
        return None, "❌ Bunday foydalanuvchi yoki kanal topilmadi.", None

    try:
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        is_chat_admin = member.status in ("administrator", "creator")
    except Exception:
        is_chat_admin = False

    if not is_chat_admin:
        return None, f"⚠️ Bot \"{chat.title or chat.id}\"da admin emas. Avval botni admin qiling.", None

    return chat.id, (chat.title or str(chat.id)), "channel"


def get_users_page(page: int = 0, page_size: int = 20):
    """
    Foydalanuvchilarni sahifalab qaytaradi (admin panel > Foydalanuvchilar
    bo'limi uchun). Har bir qator: (chat_id, username, vip_until).
    Qaytaradi: (rows, total_count)
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    offset = max(0, page) * page_size
    cur.execute(
        "SELECT chat_id, username, vip_until FROM users ORDER BY first_seen DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    rows = cur.fetchall()
    conn.close()
    return rows, total


# ============ YORDAMCHI FUNKSIYALAR ============

def make_preview(message) -> str:
    """Post uchun qisqa tavsif (ichki, admin uchun)."""
    if message.text:
        return message.text.strip()[:50]
    if message.caption:
        return message.caption.strip()[:50]
    if message.video:
        return "[video]"
    if message.photo:
        return "[rasm]"
    if message.document:
        return "[hujjat]"
    if message.audio:
        return "[audio]"
    if message.voice:
        return "[ovozli xabar]"
    if message.animation:
        return "[gif]"
    if message.sticker:
        return "[stiker]"
    return "[post]"


def parse_codes(text: str):
    """"12,avatar,avatr" -> ['12', 'AVATAR', 'AVATR'] (bo'sh qatorlar chiqarib tashlanadi)."""
    raw_parts = text.split(",")
    codes = [p.strip() for p in raw_parts if p.strip()]
    return codes


async def track_and_trim(update: Update, context: ContextTypes.DEFAULT_TYPE, sent_message, include_incoming: bool = True):
    """
    Har bir foydalanuvchi (ADMIN HAM shu jumladan) bilan suhbatda, chatdagi
    xabarlar tarixini (shu chat uchun context.chat_data ichida) kuzatib
    boradi va har safar yangi xabar yuborilgach, SO'NGGI 2 TADAN BOSHQA
    barcha eski xabarlarni o'chirib tashlaydi. Natijada chatda doim faqat
    oxirgi almashinuv (foydalanuvchi kodi/tugmasi + bot javobi) ko'rinishda
    qoladi.

    Eslatma: tarix botning joriy ishga tushishi davomida xotirada saqlanadi -
    bot qayta ishga tushirilsa, eski (avvalgi sessiyadagi) xabarlar
    "unutiladi" va endi avtomatik o'chirilmaydi.
    """
    chat_id = update.effective_chat.id
    history = context.chat_data.setdefault("recent_ids", [])

    if include_incoming and update.message is not None:
        if not history or history[-1] != update.message.message_id:
            history.append(update.message.message_id)

    if sent_message is not None and hasattr(sent_message, "message_id"):
        history.append(sent_message.message_id)

    to_delete = history[:-2]
    keep = history[-2:]

    for mid in to_delete:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            # Xabar allaqachon o'chirilgan, juda eski (48 soatdan katta),
            # yoki umuman mavjud emas bo'lishi mumkin - e'tiborsiz qoldiramiz.
            pass

    context.chat_data["recent_ids"] = keep


# ============ /add SUHBATI (ADMIN) ============

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/add (yoki /add_game) buyrug'i orqali HAM, admin panelidagi tegishli
    tugma orqali HAM ishga tushishi mumkin. Qaysi trigger ishlatilganiga
    qarab, post 'movie' yoki 'game' kategoriyasida saqlanadi.

    Butun suhbat davomida almashiladigan HAR BIR xabar (admin) 'add_flow_msg_ids'
    ro'yxatida kuzatib boriladi - post/o'yin to'liq saqlangach, ular barchasi
    birdek o'chiriladi va faqat yakuniy natija matni qoladi."""
    user_id = update.effective_user.id
    context.user_data["add_flow_msg_ids"] = []  # yangi sessiya - eski qoldiqlarni tozalaymiz

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        category = CATEGORY_GAME if query.data == "adm:add_game" else CATEGORY_MOVIE
        if not is_admin(user_id):
            await query.edit_message_text("⛔️ Sizda qo'shish huquqi yo'q.")
            return ConversationHandler.END
        context.user_data["pending_category"] = category
        label = "o'yin" if category == CATEGORY_GAME else "post"
        icon = "🎮" if category == CATEGORY_GAME else "🎬"
        await query.edit_message_text(
            f"{icon} {label.capitalize()}ni yuboring (video, rasm, hujjat, yoki oddiy matn "
            "bo'lishi mumkin).\n\nBekor qilish uchun /cancel yozing."
        )
        context.user_data["add_flow_msg_ids"].append(query.message.message_id)
        return WAITING_POST

    text = (update.message.text or "")
    category = CATEGORY_GAME if text.startswith("/add_game") else CATEGORY_MOVIE

    if not is_admin(user_id):
        await update.message.reply_text("⛔️ Sizda qo'shish huquqi yo'q.")
        return ConversationHandler.END

    context.user_data["pending_category"] = category
    label = "o'yin" if category == CATEGORY_GAME else "post"
    icon = "🎮" if category == CATEGORY_GAME else "🎬"
    context.user_data["add_flow_msg_ids"].append(update.message.message_id)
    sent = await update.message.reply_text(
        f"{icon} {label.capitalize()}ni yuboring (video, rasm, hujjat, yoki oddiy matn "
        "bo'lishi mumkin).\n\nBekor qilish uchun /cancel yozing."
    )
    context.user_data["add_flow_msg_ids"].append(sent.message_id)
    return WAITING_POST


async def add_receive_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    preview = make_preview(message)
    category = context.user_data.pop("pending_category", CATEGORY_MOVIE)
    flow_ids = context.user_data.setdefault("add_flow_msg_ids", [])

    # Agar "saqlash guruhi" sozlangan bo'lsa (admin panel orqali yoki kodda),
    # postni ADMIN bilan shaxsiy chatda emas, balki o'sha guruhda saqlaymiz -
    # shunda admin o'z shaxsiy chat tarixini tozalab tashlasa ham, post
    # xavfsiz qoladi.
    storage_chat_id = message.chat_id
    storage_message_id = message.message_id
    copied_to_storage = False

    db_group_id = get_storage_chat_id()
    if db_group_id:
        try:
            stored = await context.bot.copy_message(
                chat_id=db_group_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
            storage_chat_id = db_group_id
            storage_message_id = stored.message_id
            copied_to_storage = True
        except Exception:
            logger.exception(
                "Postni saqlash guruhiga (chat_id=%s) nusxalab bo'lmadi - "
                "asl xabar (admin chatidagi) ishlatiladi.",
                db_group_id,
            )
            warn = await update.message.reply_text(
                "⚠️ Diqqat: postni saqlash guruhiga nusxalab bo'lmadi (bot guruhda "
                "admin emasmi yoki guruh o'chirilganmi - tekshiring). Post hozircha "
                "faqat shu chatda saqlanadi."
            )
            flow_ids.append(warn.message_id)

    # MUHIM: asl post xabarini FAQAT nusxa muvaffaqiyatli olinganda tozalash
    # ro'yxatiga qo'shamiz - aks holda bu xabarning O'ZI "baza" bo'lib
    # qolgani uchun, uni o'chirsak post butunlay ishlamay qoladi.
    if copied_to_storage:
        flow_ids.append(message.message_id)

    # Postning o'zini vaqtincha saqlab qo'yamiz (kodlar va tugma nomi
    # kelgandan keyin bazaga yozamiz)
    context.user_data["pending_post"] = {
        "chat_id": storage_chat_id,
        "message_id": storage_message_id,
        "preview": preview,
        "category": category,
    }

    label = "O'yin" if category == CATEGORY_GAME else "Post"
    sent = await update.message.reply_text(
        f"✅ {label} qabul qilindi: {preview}\n\n"
        f"Endi shu {label.lower()} uchun kodlarni vergul bilan ajratib yozing.\n"
        "Masalan: 12,avatar,avatr,avatar2\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    flow_ids.append(sent.message_id)
    return WAITING_CODES


async def add_receive_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_post")
    if not pending:
        await update.message.reply_text(
            "⚠️ Avval /add buyrug'i bilan boshlang."
        )
        return ConversationHandler.END

    flow_ids = context.user_data.setdefault("add_flow_msg_ids", [])
    flow_ids.append(update.message.message_id)

    codes = parse_codes(update.message.text or "")
    if not codes:
        warn = await update.message.reply_text(
            "❌ Hech qanday kod topilmadi. Kodlarni vergul bilan ajratib yozing, "
            "masalan: 12,avatar,avatr\n\nYoki /cancel bilan bekor qiling."
        )
        flow_ids.append(warn.message_id)
        return WAITING_CODES

    pending["codes"] = codes

    sent = await update.message.reply_text(
        "✅ Kodlar qabul qilindi.\n\n"
        "Endi shu post uchun TUGMA NOMINI yozing - bu nom "
        f'"{BTN_KINOLAR}" ro\'yxatida shu post tugmasi sifatida chiqadi.\n'
        "Masalan: Avatar: Suvning yo'li (2022)\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    flow_ids.append(sent.message_id)
    return WAITING_BUTTON_NAME


async def add_receive_button_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_post")
    if not pending or "codes" not in pending:
        await update.message.reply_text(
            "⚠️ Avval /add buyrug'i bilan boshlang."
        )
        return ConversationHandler.END

    flow_ids = context.user_data.setdefault("add_flow_msg_ids", [])
    flow_ids.append(update.message.message_id)

    button_name = (update.message.text or "").strip()
    if not button_name:
        warn = await update.message.reply_text(
            "❌ Tugma nomi bo'sh bo'lishi mumkin emas. Iltimos, nom yozing, "
            "yoki /cancel bilan bekor qiling."
        )
        flow_ids.append(warn.message_id)
        return WAITING_BUTTON_NAME

    pending["button_name"] = button_name

    sent = await update.message.reply_text(
        "🔗 Post ostiga qo'shimcha tugma (masalan kanalga havola) qo'shmoqchimisiz?\n\n"
        "Agar KERAK BO'LMASA - shunchaki 0 yozing.\n"
        "Agar KERAK BO'LSA - havolani yuboring (http:// yoki https:// bilan boshlanishi kerak).\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    flow_ids.append(sent.message_id)
    return WAITING_EXTRA_LINK


async def add_receive_extra_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_post")
    if not pending or "button_name" not in pending:
        await update.message.reply_text("⚠️ Avval /add buyrug'i bilan boshlang.")
        return ConversationHandler.END

    flow_ids = context.user_data.setdefault("add_flow_msg_ids", [])
    flow_ids.append(update.message.message_id)

    text = (update.message.text or "").strip()

    if text == "0":
        pending["extra_button_text"] = None
        pending["extra_button_url"] = None
        await _ask_visibility(update, context)
        return WAITING_VISIBILITY

    if not (text.startswith("http://") or text.startswith("https://")):
        warn = await update.message.reply_text(
            "❌ Link http:// yoki https:// bilan boshlanishi kerak.\n"
            "Tugma kerak bo'lmasa - 0 yozing, yoki /cancel bilan bekor qiling."
        )
        flow_ids.append(warn.message_id)
        return WAITING_EXTRA_LINK

    pending["extra_button_url"] = text

    sent = await update.message.reply_text(
        "✏️ Endi shu tugma uchun NOM yozing (masalan: 📢 Kanalga o'tish):\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    flow_ids.append(sent.message_id)
    return WAITING_EXTRA_LINK_NAME


async def add_receive_extra_link_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_post")
    if not pending or "extra_button_url" not in pending:
        await update.message.reply_text("⚠️ Avval /add buyrug'i bilan boshlang.")
        return ConversationHandler.END

    flow_ids = context.user_data.setdefault("add_flow_msg_ids", [])
    flow_ids.append(update.message.message_id)

    text = (update.message.text or "").strip()
    if not text:
        warn = await update.message.reply_text(
            "❌ Tugma nomi bo'sh bo'lishi mumkin emas. Qaytadan yozing, "
            "yoki /cancel bilan bekor qiling."
        )
        flow_ids.append(warn.message_id)
        return WAITING_EXTRA_LINK_NAME

    pending["extra_button_text"] = text
    await _ask_visibility(update, context)
    return WAITING_VISIBILITY


async def _ask_visibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Postni saqlashdan oldin oxirgi savol - kimlar ko'ra oladi?"""
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(VISIBILITY_LABELS[VISIBILITY_ALL], callback_data=f"addvis:{VISIBILITY_ALL}")],
            [InlineKeyboardButton(VISIBILITY_LABELS[VISIBILITY_VIP], callback_data=f"addvis:{VISIBILITY_VIP}")],
            [InlineKeyboardButton(VISIBILITY_LABELS[VISIBILITY_ADMIN], callback_data=f"addvis:{VISIBILITY_ADMIN}")],
        ]
    )
    sent = await update.message.reply_text(
        "👁 Bu postni KIMLAR ko'ra olsin?\n\n"
        "(VIP bo'lmaganlar bu postni na kod yozib, na \"Barcha postlar\" "
        "ro'yxatida ko'ra olmaydi, agar \"Faqat VIP\" tanlansa)",
        reply_markup=keyboard,
    )
    context.user_data.setdefault("add_flow_msg_ids", []).append(sent.message_id)


async def add_receive_visibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin ko'rinish huquqi tugmalaridan birini bosganda ishga tushadi.
    Post/o'yin bazaga muvaffaqiyatli saqlangach, BUTUN suhbat davomidagi
    barcha oraliq xabarlar (post, kodlar, tugma nomi, link savollari,
    ko'rinish huquqi savoli) o'chirib tashlanadi - faqat yakuniy natija
    (pastda 2 ta navigatsiya tugmasi bilan) qoladi."""
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get("pending_post")
    if not pending:
        await query.edit_message_text("⚠️ Sessiya topilmadi. /add orqali qaytadan boshlang.")
        return ConversationHandler.END

    visibility = query.data.split(":")[1]  # "addvis:all" -> "all"
    if visibility not in (VISIBILITY_ALL, VISIBILITY_VIP, VISIBILITY_ADMIN):
        visibility = VISIBILITY_ALL
    pending["visibility"] = visibility

    post_id = save_post(
        pending["chat_id"],
        pending["message_id"],
        pending["preview"],
        pending["button_name"],
        update.effective_user.id,
        extra_button_text=pending.get("extra_button_text"),
        extra_button_url=pending.get("extra_button_url"),
        category=pending.get("category", CATEGORY_MOVIE),
        visibility=visibility,
    )
    save_codes(pending["codes"], post_id)
    context.user_data.pop("pending_post", None)

    codes_str = ", ".join(pending["codes"])
    extra_line = ""
    if pending.get("extra_button_url"):
        extra_line = f"\nLink-tugma: {pending['extra_button_text']} -> {pending['extra_button_url']}"

    category_label = "O'yin" if pending.get("category") == CATEGORY_GAME else "Post"
    text = (
        f"✅ Saqlandi! ({category_label})\n"
        f"Tugma nomi: {pending['button_name']}\n"
        f"Kodlar: {codes_str}\n"
        f"Ko'rish huquqi: {VISIBILITY_LABELS[visibility]}{extra_line}"
    )

    chat_id = query.message.chat_id

    # Butun /add suhbatidagi barcha oraliq xabarlarni o'chiramiz - shu
    # jumladan "Kimlar ko'rsin?" savolining o'zi ham (query.message).
    flow_ids = context.user_data.pop("add_flow_msg_ids", [])
    flow_ids.append(query.message.message_id)
    for mid in flow_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

    nav_keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="adm:menu")],
            [InlineKeyboardButton("🏠 Bosh menyuga qaytish", callback_data="adm:backhome")],
        ]
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=nav_keyboard)
    return ConversationHandler.END


def home_button_row():
    """
    Admin panelning istalgan ichki sahifasiga qo'shiladigan qayta
    ishlatiladigan qator - "🔙 Orqaga" tugmasi yonida/ostida, foydalanuvchi
    (admin) istalgan chuqurlikdan BIR BOSISHDA asosiy (pastdagi doimiy
    tugmali) menyuga chiqib ketishi uchun.
    """
    return [InlineKeyboardButton("🏠 Bosh menyu", callback_data="adm:backhome")]


async def adm_backhome_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Istalgan admin panel sahifasidagi "🏠 Bosh menyu" tugmasi bosilganda
    ishga tushadi - eski xabarni o'chirib, o'rniga pastdagi doimiy tugmalar
    (Barcha postlar/VIP/O'yinlar/Mening statusim) bilan birga YANGI "Bosh
    menyu" xabarini yuboradi. Buni ataylab shunday qilamiz (shunchaki eski
    xabarni o'chirib qo'ymasdan) - chunki oldingi tajribada, pastdagi
    klaviatura faqat uni QAYTA BIRIKTIRGAN xabar orqali kafolatlanadi, aks
    holda ba'zan ko'rinmay qolishi mumkin edi.

    MUHIM: bu funksiya har bir ConversationHandler'ning `fallbacks`
    ro'yxatiga ham qo'shilgan - shuning uchun agar admin biror suhbat
    (masalan post qo'shish, VIP muddatini o'zgartirish) ICHIDA turib shu
    tugmani bossa, o'sha suhbat holati ham TO'G'RI YAKUNLANADI (osilib
    qolmaydi), aks holda keyingi, aloqasiz xabar noto'g'ri talqin qilinishi
    mumkin edi."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()  # suhbat holatiga oid barcha vaqtinchalik ma'lumotlarni tozalaymiz
    try:
        await query.message.delete()
    except Exception:
        pass
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🏠 Bosh menyu.",
        reply_markup=main_menu_markup(),
    )
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_post", None)
    chat_id = update.effective_chat.id

    flow_ids = context.user_data.pop("add_flow_msg_ids", [])
    for mid in flow_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

    try:
        await update.message.delete()
    except Exception:
        pass

    await context.bot.send_message(chat_id=chat_id, text="Bekor qilindi.")
    return ConversationHandler.END


# ============ ODDIY BUYRUQLAR ============

def main_menu_markup():
    keyboard = [
        [KeyboardButton(BTN_KINOLAR), KeyboardButton(BTN_VIP)],
        [KeyboardButton(BTN_GAMES), KeyboardButton(BTN_STATUS)],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_chat.id, update.effective_user.username)
    sent = await update.message.reply_text(
        "Salom! 🎬\n\n"
        "Kerakli postni olish uchun menga kodni yuboring, masalan: avatar\n"
        "Yoki pastdagi tugmalardan foydalaning.",
        reply_markup=main_menu_markup(),
    )
    await track_and_trim(update, context, sent)


POSTS_PER_PAGE = 10

CATEGORY_HEADERS = {
    CATEGORY_MOVIE: "🎬 Mavjud postlar (tugmani bosing):",
    CATEGORY_GAME: "🎮 Mavjud o'yinlar (tugmani bosing):",
}
CATEGORY_ICONS = {
    CATEGORY_MOVIE: "🎬",
    CATEGORY_GAME: "🎮",
}


def build_posts_page_markup(rows, page: int, category: str = CATEGORY_MOVIE):
    """
    Postlar ro'yxatini sahifalab (har sahifada 10 tadan) InlineKeyboardMarkup
    ko'rinishida quradi. Pastida doim ❌ Yopish tugmasi bo'ladi; agar bir
    nechta sahifa bo'lsa, uning chap va o'ng tomonida ◀️/▶️ tugmalari chiqadi.
    'category' navigatsiya tugmalari to'g'ri ro'yxatga qaytishi uchun
    callback_data ichiga yoziladi. matn, markup ni qaytaradi.
    """
    total = len(rows)
    total_pages = max(1, (total + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * POSTS_PER_PAGE
    page_rows = rows[start:start + POSTS_PER_PAGE]

    icon = CATEGORY_ICONS.get(category, "🎬")
    keyboard = [
        [InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"code:{code}")]
        for code, label, post_id in page_rows
    ]

    nav_row = []
    if total_pages > 1 and page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"listpage:{category}:{page - 1}"))
    nav_row.append(InlineKeyboardButton("❌ Yopish", callback_data="listclose"))
    if total_pages > 1 and page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"listpage:{category}:{page + 1}"))
    keyboard.append(nav_row)

    text = CATEGORY_HEADERS.get(category, CATEGORY_HEADERS[CATEGORY_MOVIE])
    if total_pages > 1:
        text += f"\n\nSahifa: {page + 1}/{total_pages}"

    return text, InlineKeyboardMarkup(keyboard)


async def show_posts_list(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str = CATEGORY_MOVIE):
    """'Barcha postlar' yoki 'O'yinlar' ro'yxatini ko'rsatadi (kategoriya bo'yicha)."""
    user_id = update.effective_user.id
    keyboard = main_menu_markup()  # pastdagi tugmalar ADMIN uchun ham doim ko'rinadi

    chat_id = update.effective_chat.id

    if category == CATEGORY_GAME and not is_vip(user_id):
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text="🔒 O'yinlar bo'limi faqat VIP foydalanuvchilar uchun ochiq.\n"
                 "VIP status olish uchun admin bilan bog'laning.",
            reply_markup=keyboard,
        )
        await track_and_trim(update, context, sent)
        return

    rows = list_all_codes(category=category)
    rows = filter_rows_by_visibility(rows, user_id)
    if not rows:
        empty_text = (
            "Hozircha bazada o'yinlar yo'q." if category == CATEGORY_GAME
            else "Hozircha bazada postlar yo'q."
        )
        sent = await context.bot.send_message(chat_id=chat_id, text=empty_text, reply_markup=keyboard)
        await track_and_trim(update, context, sent)
        return

    text, markup = build_posts_page_markup(rows, page=0, category=category)
    sent = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)

    # DIQQAT: bu sahifa oddiy track_and_trim orqali avtomatik O'CHIRILMAYDI -
    # u faqat ❌ Yopish tugmasi bosilganda YOKI pastdagi menyudan (Barcha
    # postlar/VIP/O'yinlar/Mening statusim) biri bosilganda o'chiriladi.
    # Shu ro'yxatdan ketma-ket bir nechta post tanlansa, HAR SAFAR faqat
    # OXIRGI tanlangan post ko'rinishda qoladi - oldingisi avtomatik
    # o'chiriladi (chatni chalkash qilib yubormaslik uchun).
    context.chat_data["open_list_message_id"] = sent.message_id
    context.chat_data["open_list_last_post_id"] = None


async def list_movies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/list buyrug'i va "🎬 Barcha postlar" tugmasi uchun."""
    await show_posts_list(update, context, category=CATEGORY_MOVIE)


async def list_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/games buyrug'i va "🎮 O'yinlar" tugmasi uchun."""
    await show_posts_list(update, context, category=CATEGORY_GAME)


async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"👤 Mening statusim" tugmasi bosilganda - foydalanuvchining tarifi haqida ma'lumot beradi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if is_admin(user_id):
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text="👤 Mening statusim\n\n⭐ Siz ADMIN sifatida cheksiz VIP statusga egasiz.",
            reply_markup=main_menu_markup(),
        )
        await track_and_trim(update, context, sent)
        return

    if is_vip(user_id):
        vip_until = get_vip_until(user_id)
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text="👤 Mening statusim\n\n"
                 "⭐ Tarifingiz: VIP\n"
                 f"⏰ Tugash sanasi: {vip_until}",
            reply_markup=main_menu_markup(),
        )
        await track_and_trim(update, context, sent)

        # VIP foydalanuvchiga VIP1 kodli postni ham yuboramiz (bu "system"
        # posti, shuning uchun allow_system=True bilan chetlab o'tiladi)
        vip_post = await send_post_for_code(
            VIP_WELCOME_CODE, update.effective_chat.id, context, allow_system=True
        )
        if vip_post not in (None, VIP_REQUIRED):
            await track_and_trim(update, context, vip_post, include_incoming=False)
    else:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⭐ VIP'ga o'tish", callback_data=f"code:{VIP_CODE}")]]
        )
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text="👤 Mening statusim\n\n"
                 "🔹 Tarifingiz: Oddiy\n\n"
                 "VIP tarifga o'tib, 🎮 O'yinlar bo'limi va qo'shimcha imkoniyatlarga ega bo'ling!",
            reply_markup=keyboard,
        )
        await track_and_trim(update, context, sent)


async def handle_list_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """◀️/▶️ tugmalari bosilganda - ro'yxatni boshqa sahifaga (shu kategoriya ichida) almashtiradi."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    # Format: "listpage:<category>:<page>"
    category = parts[1] if len(parts) >= 3 else CATEGORY_MOVIE
    try:
        page = int(parts[2]) if len(parts) >= 3 else int(parts[1])
    except (IndexError, ValueError):
        page = 0

    if category == CATEGORY_GAME and not is_vip(update.effective_user.id):
        await query.edit_message_text(
            "🔒 Bu bo'lim endi sizga ochiq emas (VIP muddati tugagan bo'lishi mumkin)."
        )
        return

    rows = list_all_codes(category=category)
    rows = filter_rows_by_visibility(rows, update.effective_user.id)
    if not rows:
        await query.edit_message_text("Hozircha bo'sh.")
        return

    text, markup = build_posts_page_markup(rows, page, category=category)
    await query.edit_message_text(text, reply_markup=markup)


async def handle_list_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """❌ Yopish tugmasi bosilganda - ro'yxat xabarini VA shu ro'yxatdan
    tanlab ochilgan (oxirgi) postni birga o'chiradi."""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    list_id = context.chat_data.pop("open_list_message_id", None)
    last_post_id = context.chat_data.pop("open_list_last_post_id", None)

    if list_id == query.message.message_id:
        ids_to_delete = [list_id]
        if last_post_id is not None:
            ids_to_delete.append(last_post_id)
        for mid in ids_to_delete:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass
    else:
        # Sessiya kuzatilmagan bo'lsa ham, kamida shu xabarni o'chiramiz
        try:
            await query.message.delete()
        except Exception:
            pass


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔️ Sizda bu buyruqdan foydalanish huquqi yo'q.")
        return

    if not context.args:
        await update.message.reply_text("Foydalanish: /delete KOD")
        return

    code = context.args[0]
    if delete_code(code):
        await update.message.reply_text(f"🗑 {code} o'chirildi.")
    else:
        await update.message.reply_text(f"{code} topilmadi.")


# ============ ADMIN PANEL (/admin) ============

WAITING_EDIT_VALUE = 100  # Tahrirlash suhbati uchun alohida ConversationHandler holati
WAITING_EDIT_LINK_URL = 101  # Link-tugma URL'ini tahrirlash holati
WAITING_EDIT_LINK_NAME = 102  # Link-tugma nomini tahrirlash holati
WAITING_BROADCAST_AUDIENCE = 199  # Reklama auditoriyasini tanlash holati
WAITING_BROADCAST_POST = 200  # Reklama tarqatish suhbati uchun alohida holat
WAITING_BROADCAST_LINK = 201  # Reklama uchun link-tugma URL'ini so'rash holati
WAITING_BROADCAST_LINK_NAME = 202  # Reklama uchun link-tugma nomini so'rash holati
WAITING_BROADCAST_CONFIRM = 203  # Reklamani yakuniy tasdiqlash holati
WAITING_VIP_USER, WAITING_VIP_DAYS = 300, 301  # VIP berish suhbati uchun alohida holatlar
WAITING_ADSEXCL_USER = 210  # Reklama yuborilmaydiganlar ro'yxatiga qo'shish holati
WAITING_ADSALWAYS_ITEM = 211  # "Doim yuboriladi" ro'yxatiga qo'shish holati
WAITING_VIP_ADJUST_DAYS = 302  # VIP muddatini uzaytirish/qisqartirish uchun alohida holat
WAITING_DB_GROUP = 400  # Baza guruhini sozlash suhbati uchun alohida holat
WAITING_VIP_CHANNEL = 500  # VIP kanalni sozlash suhbati uchun alohida holat
WAITING_AUTOACCEPT_CHANNEL = 550  # "Avto qo'shish" kanalini sozlash suhbati uchun alohida holat
WAITING_VIP_SPECIAL_POST = 600  # VIP1/VIP2 postini sozlash suhbati uchun alohida holat
WAITING_DB_UPLOAD = 700  # Bazani qo'lda .db fayl orqali yuklash holati
WAITING_DB_UPLOAD_CONFIRM = 701  # Yuklangan bazani tasdiqlash holati


def admin_menu_markup():
    keyboard = [
        [
            InlineKeyboardButton("➕ Yangi post", callback_data="adm:add"),
            InlineKeyboardButton("🎮 O'yin qo'shish", callback_data="adm:add_game"),
        ],
        [
            InlineKeyboardButton("✏️ Tahrirlash", callback_data="adm:editlist"),
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm:users"),
        ],
        [
            InlineKeyboardButton("⭐ VIP berish", callback_data="adm:vip"),
            InlineKeyboardButton("📢 Reklama", callback_data="adm:broadcast"),
        ],
        [
            InlineKeyboardButton("📊 Hisobot", callback_data="adm:stats"),
            InlineKeyboardButton("🗄 Baza guruhi", callback_data="adm:setdb"),
        ],
        [
            InlineKeyboardButton("📺 VIP kanal", callback_data="adm:setvipchannel"),
            InlineKeyboardButton("🤖 Avto qo'shish", callback_data="adm:setautoaccept"),
        ],
        [
            InlineKeyboardButton("🎁 VIP1 posti", callback_data="adm:setvip1"),
            InlineKeyboardButton("⏰ VIP2 posti", callback_data="adm:setvip2"),
        ],
        [
            InlineKeyboardButton("🔄 Hozir zaxiralash", callback_data="adm:backupnow"),
            InlineKeyboardButton("♻️ Hozir tiklash", callback_data="adm:restorenow"),
        ],
        [InlineKeyboardButton("📥 DB faylni qo'lda yuklash", callback_data="adm:dbupload")],
        home_button_row(),
    ]
    return InlineKeyboardMarkup(keyboard)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔️ Sizda admin panelidan foydalanish huquqi yo'q.")
        return
    await update.message.reply_text("⚙️ Admin panel:", reply_markup=admin_menu_markup())


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin uchun yordamchi buyruq: joriy chat (yoki guruh)ning ID raqamini
    ko'rsatadi. Bu ID 'saqlash guruhi' sifatida STORAGE_CHAT_ID sozlamasiga
    yozish uchun kerak. Guruhda ishlatish uchun botni o'sha guruhga admin
    qilib qo'shib, guruh ichida /chatid yozing.
    """
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    chat = update.effective_chat
    await update.message.reply_text(
        f"🆔 Bu chatning ID raqami: `{chat.id}`\n"
        f"Turi: {chat.type}\n\n"
        "Buni 'saqlash guruhi' sifatida ishlatish uchun shu raqamni "
        "STORAGE_CHAT_ID sozlamasiga yozing.",
        parse_mode="Markdown",
    )


async def adm_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    await query.edit_message_text("⚙️ Admin panel:", reply_markup=admin_menu_markup())


async def adm_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    s = get_stats()
    text = (
        "📊 Hisobot\n\n"
        f"👥 Jami foydalanuvchilar: {s['total_users']}\n\n"
        f"🆕 Yangi foydalanuvchilar:\n"
        f"   Bugun: {s['new_today']}\n"
        f"   Oxirgi 30 kun: {s['new_30d']}\n\n"
        f"✅ Faol foydalanuvchilar:\n"
        f"   Bugun: {s['active_today']}\n"
        f"   Oxirgi 30 kun: {s['active_30d']}\n\n"
        f"🔎 Qidirishlar soni:\n"
        f"   Bugun: {s['searches_today']}\n"
        f"   Oxirgi 30 kun: {s['searches_30d']}"
    )
    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="adm:menu")], home_button_row()]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


USERS_PER_PAGE = 20


async def render_users_page(query, page: int):
    """Foydalanuvchilar ro'yxatini sahifalab (har sahifada 20 tadan) ko'rsatadi."""
    rows, total = get_users_page(page, USERS_PER_PAGE)
    total_pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    if total == 0:
        text = "👥 Hozircha botdan foydalangan hech kim yo'q."
    else:
        start_num = page * USERS_PER_PAGE + 1
        lines = []
        for i, (chat_id, username, vip_until) in enumerate(rows, start=start_num):
            uname = f"@{username}" if username else "(username yo'q)"
            vip_mark = " ⭐VIP" if vip_until else ""
            lines.append(f"{i}. ID: {chat_id} | {uname}{vip_mark}")
        text = (
            f"👥 Foydalanuvchilar (jami {total} ta)\n"
            f"Sahifa: {page + 1}/{total_pages}\n\n" + "\n".join(lines)
        )

    nav_row = []
    if total_pages > 1 and page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"adm:userspage:{page - 1}"))
    nav_row.append(InlineKeyboardButton("🔙 Orqaga", callback_data="adm:menu"))
    if total_pages > 1 and page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"adm:userspage:{page + 1}"))

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([nav_row, home_button_row()]))


async def adm_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    await render_users_page(query, 0)


async def adm_users_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    try:
        page = int(query.data.split(":")[2])
    except (IndexError, ValueError):
        page = 0
    await render_users_page(query, page)


async def render_edit_list(query):
    """Tahrirlash uchun postlar ro'yxatini (post_id, nom, kategoriya) inline tugmalar sifatida chizadi."""
    posts = get_all_posts()
    if not posts:
        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="adm:menu")], home_button_row()]
        await query.edit_message_text(
            "Hozircha postlar yo'q.", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                f"{'🎮' if category == CATEGORY_GAME else '🎬'} {label}",
                callback_data=f"adm:editpost:{post_id}",
            )
        ]
        for post_id, label, category in posts
    ]
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="adm:menu")])
    keyboard.append(home_button_row())
    await query.edit_message_text(
        "✏️ Tahrirlash uchun postni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def adm_editlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    await render_edit_list(query)


async def adm_postdetail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    post_id = int(query.data.split(":")[2])
    codes = get_codes_for_post(post_id)
    codes_str = ", ".join(codes) if codes else "(kodlar yo'q)"

    details = get_post_details(post_id)
    if details:
        button_name, extra_button_text, extra_button_url, visibility, category = details
        link_status = f"{extra_button_text} -> {extra_button_url}" if extra_button_url else "(yo'q)"
        visibility_label = VISIBILITY_LABELS.get(visibility, VISIBILITY_LABELS[VISIBILITY_ALL])
    else:
        link_status = "(yo'q)"
        visibility_label = VISIBILITY_LABELS[VISIBILITY_ALL]

    keyboard = [
        [InlineKeyboardButton("✏️ Kodlarni tahrirlash", callback_data=f"adm:editcodes:{post_id}")],
        [InlineKeyboardButton("✏️ Tugma nomini tahrirlash", callback_data=f"adm:editname:{post_id}")],
        [InlineKeyboardButton("🔗 Link tugmani tahrirlash", callback_data=f"adm:editlink:{post_id}")],
        [InlineKeyboardButton("👁 Ko'rinish huquqini tahrirlash", callback_data=f"adm:editvis:{post_id}")],
        [InlineKeyboardButton("🗑 Postni o'chirish", callback_data=f"adm:delpost:{post_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="adm:editlist")],
        home_button_row(),
    ]
    await query.edit_message_text(
        f"🎬 Post #{post_id}\n"
        f"Kodlar: {codes_str}\n"
        f"Link-tugma: {link_status}\n"
        f"Ko'rinish huquqi: {visibility_label}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def adm_delpost_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    post_id = int(query.data.split(":")[2])
    keyboard = [
        [InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"adm:delconfirm:{post_id}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"adm:editpost:{post_id}")],
    ]
    await query.edit_message_text(
        "⚠️ Haqiqatan ham bu postni butunlay o'chirmoqchimisiz?\n"
        "(post va unga bog'liq BARCHA kodlar o'chiriladi)",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def adm_delpost_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    post_id = int(query.data.split(":")[2])
    delete_post(post_id)
    await render_edit_list(query)


async def adm_editvis_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "👁 Ko'rinish huquqini tahrirlash" tugmasini bosganda - 3 ta variantni ko'rsatadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    post_id = int(query.data.split(":")[2])
    keyboard = [
        [InlineKeyboardButton(VISIBILITY_LABELS[VISIBILITY_ALL], callback_data=f"adm:setvis:{VISIBILITY_ALL}:{post_id}")],
        [InlineKeyboardButton(VISIBILITY_LABELS[VISIBILITY_VIP], callback_data=f"adm:setvis:{VISIBILITY_VIP}:{post_id}")],
        [InlineKeyboardButton(VISIBILITY_LABELS[VISIBILITY_ADMIN], callback_data=f"adm:setvis:{VISIBILITY_ADMIN}:{post_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm:editpost:{post_id}")],
        home_button_row(),
    ]
    await query.edit_message_text(
        "👁 Bu postni KIMLAR ko'ra olsin?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def adm_setvis_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin ko'rinish huquqi variantlaridan birini tanlaganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    parts = query.data.split(":")  # "adm:setvis:vip:5"
    visibility = parts[2]
    post_id = int(parts[3])
    if visibility not in (VISIBILITY_ALL, VISIBILITY_VIP, VISIBILITY_ADMIN):
        visibility = VISIBILITY_ALL

    update_post_visibility(post_id, visibility)

    keyboard = [[InlineKeyboardButton("🔙 Postga qaytish", callback_data=f"adm:editpost:{post_id}")]]
    await query.edit_message_text(
        f"✅ Ko'rinish huquqi yangilandi: {VISIBILITY_LABELS[visibility]}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def edit_field_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "Kodlarni tahrirlash", "Tugma nomini tahrirlash" yoki "Link
    tugmani tahrirlash" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    parts = query.data.split(":")  # "adm:editcodes:5" / "adm:editname:5" / "adm:editlink:5"
    field_key = parts[1]
    post_id = int(parts[2])

    context.user_data["edit_post_id"] = post_id

    if field_key == "editcodes":
        context.user_data["edit_field"] = "codes"
        await query.edit_message_text(
            "✏️ Ushbu post uchun YANGI kodlarni vergul bilan ajratib yozing "
            "(eski kodlar butunlay almashtiriladi):\n"
            "Masalan: 12,avatar,avatr\n\n"
            "Bekor qilish uchun /cancel yozing."
        )
        return WAITING_EDIT_VALUE

    if field_key == "editlink":
        await query.edit_message_text(
            "🔗 Link tugma uchun YANGI havolani yuboring "
            "(http:// yoki https:// bilan boshlanishi kerak).\n\n"
            "Link tugmani BUTUNLAY OLIB TASHLAMOQCHI bo'lsangiz - 0 yozing.\n\n"
            "Bekor qilish uchun /cancel yozing."
        )
        return WAITING_EDIT_LINK_URL

    # "editname"
    context.user_data["edit_field"] = "name"
    await query.edit_message_text(
        "✏️ Ushbu post uchun YANGI tugma nomini yozing:\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_EDIT_VALUE


async def edit_receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post_id = context.user_data.get("edit_post_id")
    field = context.user_data.get("edit_field")

    if post_id is None or field is None:
        await update.message.reply_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    text = (update.message.text or "").strip()

    if field == "codes":
        codes = parse_codes(text)
        if not codes:
            await update.message.reply_text(
                "❌ Kodlar topilmadi. Vergul bilan ajratib qaytadan yozing, "
                "yoki /cancel bilan bekor qiling."
            )
            return WAITING_EDIT_VALUE
        replace_codes_for_post(post_id, codes)
        await update.message.reply_text(f"✅ Kodlar yangilandi: {', '.join(codes)}")
    else:  # "name"
        if not text:
            await update.message.reply_text(
                "❌ Tugma nomi bo'sh bo'lishi mumkin emas. Qaytadan yozing, "
                "yoki /cancel bilan bekor qiling."
            )
            return WAITING_EDIT_VALUE
        update_post_button_name(post_id, text)
        await update.message.reply_text(f"✅ Tugma nomi yangilandi: {text}")

    context.user_data.pop("edit_post_id", None)
    context.user_data.pop("edit_field", None)
    return ConversationHandler.END


async def edit_receive_link_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post_id = context.user_data.get("edit_post_id")
    if post_id is None:
        await update.message.reply_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    text = (update.message.text or "").strip()

    if text == "0":
        update_post_link(post_id, None, None)
        await update.message.reply_text("✅ Link tugma olib tashlandi.")
        context.user_data.pop("edit_post_id", None)
        return ConversationHandler.END

    if not (text.startswith("http://") or text.startswith("https://")):
        await update.message.reply_text(
            "❌ Link http:// yoki https:// bilan boshlanishi kerak.\n"
            "Tugmani olib tashlamoqchi bo'lsangiz - 0 yozing, yoki /cancel bilan bekor qiling."
        )
        return WAITING_EDIT_LINK_URL

    context.user_data["edit_link_url"] = text
    await update.message.reply_text(
        "✏️ Endi shu tugma uchun NOM yozing (masalan: 📢 Kanalga o'tish):\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_EDIT_LINK_NAME


async def edit_receive_link_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post_id = context.user_data.get("edit_post_id")
    url = context.user_data.get("edit_link_url")

    if post_id is None or url is None:
        await update.message.reply_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(
            "❌ Tugma nomi bo'sh bo'lishi mumkin emas. Qaytadan yozing, "
            "yoki /cancel bilan bekor qiling."
        )
        return WAITING_EDIT_LINK_NAME

    update_post_link(post_id, text, url)
    await update.message.reply_text(f"✅ Link tugma yangilandi: {text} -> {url}")

    context.user_data.pop("edit_post_id", None)
    context.user_data.pop("edit_link_url", None)
    return ConversationHandler.END


async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("edit_post_id", None)
    context.user_data.pop("edit_field", None)
    context.user_data.pop("edit_link_url", None)
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ============ REKLAMA TARQATISH (/admin -> 📢 Reklama tarqatish) ============

AUDIENCE_LABELS = {
    "regular": "oddiy foydalanuvchilar",
    "vip": "VIP foydalanuvchilar",
    "all": "barcha foydalanuvchilar",
}


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "📢 Reklama tarqatish" tugmasini bosganda ishga tushadi - avval auditoriya so'raladi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("👤 Faqat oddiy foydalanuvchilarga", callback_data="adm:bcast:regular")],
        [InlineKeyboardButton("⭐ Faqat VIP foydalanuvchilarga", callback_data="adm:bcast:vip")],
        [InlineKeyboardButton("📢 Hammaga", callback_data="adm:bcast:all")],
        [InlineKeyboardButton("🚫 Reklama yuborilmaydiganlar", callback_data="adm:adsexcl")],
        [InlineKeyboardButton("✅ Doim yuboriladi", callback_data="adm:adsalways")],
    ]
    await query.edit_message_text(
        "📢 Reklamani kimlarga yubormoqchisiz?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAITING_BROADCAST_AUDIENCE


async def broadcast_choose_audience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin auditoriya tugmalaridan birini tanlaganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    audience = query.data.split(":")[2]  # "adm:bcast:regular" -> "regular"
    context.user_data["broadcast_audience"] = audience

    user_ids = get_broadcast_recipients(audience)
    label = AUDIENCE_LABELS.get(audience, "foydalanuvchilar")

    await query.edit_message_text(
        "📢 Reklama uchun postni yuboring (video, rasm, hujjat yoki oddiy matn "
        "bo'lishi mumkin).\n\n"
        f"Bu post {label}ga ({len(user_ids)} ta) yuboriladi.\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_BROADCAST_POST


async def broadcast_receive_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin reklama postini yuborganda - postni vaqtincha saqlab, link-tugma
    haqida so'raydi (xuddi oddiy post qo'shishdagi kabi)."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    message = update.message
    context.user_data["broadcast_post"] = {
        "chat_id": message.chat_id,
        "message_id": message.message_id,
    }

    await message.reply_text(
        "🔗 Post ostiga qo'shimcha tugma (masalan kanalga havola) qo'shmoqchimisiz?\n\n"
        "Agar KERAK BO'LMASA - shunchaki 0 yozing.\n"
        "Agar KERAK BO'LSA - havolani yuboring (http:// yoki https:// bilan boshlanishi kerak).\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_BROADCAST_LINK


async def broadcast_receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("broadcast_post")
    if not pending:
        await update.message.reply_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    text = (update.message.text or "").strip()

    if text == "0":
        pending["extra_button_text"] = None
        pending["extra_button_url"] = None
        await _show_broadcast_preview(update, context)
        return WAITING_BROADCAST_CONFIRM

    if not (text.startswith("http://") or text.startswith("https://")):
        await update.message.reply_text(
            "❌ Link http:// yoki https:// bilan boshlanishi kerak.\n"
            "Tugma kerak bo'lmasa - 0 yozing, yoki /cancel bilan bekor qiling."
        )
        return WAITING_BROADCAST_LINK

    pending["extra_button_url"] = text
    await update.message.reply_text(
        "✏️ Endi shu tugma uchun NOM yozing (masalan: 📢 Kanalga o'tish):\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_BROADCAST_LINK_NAME


async def broadcast_receive_link_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("broadcast_post")
    if not pending or "extra_button_url" not in pending:
        await update.message.reply_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(
            "❌ Tugma nomi bo'sh bo'lishi mumkin emas. Qaytadan yozing, "
            "yoki /cancel bilan bekor qiling."
        )
        return WAITING_BROADCAST_LINK_NAME

    pending["extra_button_text"] = text
    await _show_broadcast_preview(update, context)
    return WAITING_BROADCAST_CONFIRM


def _broadcast_link_markup(pending: dict):
    """pending ma'lumotidan link-tugma uchun InlineKeyboardMarkup quradi (agar bo'lsa)."""
    if pending.get("extra_button_url"):
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=pending["extra_button_text"], url=pending["extra_button_url"])]]
        )
    return None


async def _show_broadcast_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reklamaning aynan qanday ko'rinishda yuborilishini (tugma bilan yoki
    tugmasiz) admin uchun oldindan ko'rsatadi va yakuniy tasdiqlashni so'raydi."""
    pending = context.user_data.get("broadcast_post")
    audience = context.user_data.get("broadcast_audience", "all")
    user_ids = get_broadcast_recipients(audience)
    label = AUDIENCE_LABELS.get(audience, "foydalanuvchilar")
    chat_id = update.effective_chat.id

    markup = _broadcast_link_markup(pending)

    # Postning aynan qanday ko'rinishini (link-tugma bilan) oldindan ko'rsatamiz
    try:
        await context.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=pending["chat_id"],
            message_id=pending["message_id"],
            reply_markup=markup,
        )
    except Exception:
        logger.exception("Reklama oldindan ko'rishni ko'rsatishda xatolik.")

    confirm_keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Ha, yuborish", callback_data="adm:bcastconfirm")],
            [InlineKeyboardButton("❌ Yo'q, bekor qilish", callback_data="adm:bcastcancel")],
        ]
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "👆 Reklama AYNAN shu ko'rinishda yuboriladi.\n\n"
            f"Auditoriya: {label} ({len(user_ids)} ta)\n\n"
            "Tasdiqlaysizmi?"
        ),
        reply_markup=confirm_keyboard,
    )


async def broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "✅ Ha, yuborish" tugmasini bosganda - haqiqiy tarqatishni boshlaydi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    pending = context.user_data.pop("broadcast_post", None)
    audience = context.user_data.pop("broadcast_audience", "all")

    if not pending:
        await query.edit_message_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    user_ids = get_broadcast_recipients(audience)
    if not user_ids:
        label = AUDIENCE_LABELS.get(audience, "foydalanuvchilar")
        await query.edit_message_text(f"⚠️ Hozircha {label} yo'q.")
        return ConversationHandler.END

    markup = _broadcast_link_markup(pending)
    admin_chat_id = pending["chat_id"]
    admin_message_id = pending["message_id"]

    await query.edit_message_text(f"📢 Yuborilmoqda... (0/{len(user_ids)})")

    success = 0
    failed = 0

    for i, uid in enumerate(user_ids, start=1):
        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=admin_chat_id,
                message_id=admin_message_id,
                reply_markup=markup,
            )
            success += 1
        except Exception:
            # Foydalanuvchi botni bloklagan, akkaunt o'chirilgan va h.k. -
            # bunday xatolar oddiy holat, jarayonni to'xtatmaymiz.
            failed += 1

        # Telegram'ning yuborish tezligi cheklovlariga tegib ketmaslik uchun
        # kichik pauza qo'shamiz (soniyasiga ~20 xabar).
        await asyncio.sleep(0.05)

        # Har 20 ta yuborishda holatni yangilab turamiz
        if i % 20 == 0:
            try:
                await query.edit_message_text(f"📢 Yuborilmoqda... ({i}/{len(user_ids)})")
            except Exception:
                pass

    await query.edit_message_text(
        f"✅ Reklama yuborildi!\n"
        f"Muvaffaqiyatli: {success}\n"
        f"Yuborilmadi (bloklangan/o'chirilgan): {failed}"
    )
    return ConversationHandler.END


async def broadcast_confirm_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin oxirgi tasdiqlashda "❌ Yo'q, bekor qilish" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("broadcast_post", None)
    context.user_data.pop("broadcast_audience", None)
    await query.edit_message_text("Bekor qilindi.")
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("broadcast_audience", None)
    context.user_data.pop("broadcast_post", None)
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ============ REKLAMA YUBORILMAYDIGANLAR RO'YXATI (/admin -> Reklama -> 🚫) ============

async def render_adsexcl_list(query):
    """Reklama yuborilmaydiganlar ro'yxatini (➕ Yangi qo'shish tugmasi bilan birga) chizadi."""
    excluded = get_excluded_ads_users()
    keyboard = [[InlineKeyboardButton("➕ Yangi qo'shish", callback_data="adm:adsexclnew")]]
    for chat_id, username in excluded:
        label = f"@{username}" if username else str(chat_id)
        keyboard.append([InlineKeyboardButton(f"🚫 {label}", callback_data=f"adm:adsexcluser:{chat_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="adm:broadcast")])
    keyboard.append(home_button_row())

    text = (
        "🚫 Reklama yuborilmaydiganlar ro'yxati:"
        if excluded
        else "🚫 Hozircha reklama yuborilmaydiganlar ro'yxati bo'sh."
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def adm_adsexcl_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"🚫 Reklama yuborilmaydiganlar" tugmasi bosilganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await render_adsexcl_list(query)
    return ConversationHandler.END


async def adm_adsexcl_user_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ro'yxatdagi bitta foydalanuvchi tugmasi bosilganda - tafsilot va o'chirish tugmasini ko'rsatadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    target_chat_id = int(query.data.split(":")[2])
    username = get_username(target_chat_id)
    label = f"@{username}" if username else str(target_chat_id)

    keyboard = [
        [InlineKeyboardButton("🗑 Ro'yxatdan olib tashlash", callback_data=f"adm:adsexclremove:{target_chat_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="adm:adsexcl")],
        home_button_row(),
    ]
    await query.edit_message_text(
        f"🚫 {label}\nID: {target_chat_id}\n\n"
        "Bu foydalanuvchiga hech qanday reklama (auditoriyasidan qat'i nazar) yuborilmaydi.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def adm_adsexcl_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"🗑 Ro'yxatdan olib tashlash" tugmasi bosilganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    target_chat_id = int(query.data.split(":")[2])
    set_ads_excluded(target_chat_id, False)
    await render_adsexcl_list(query)


async def adsexcl_new_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"➕ Yangi qo'shish" tugmasi bosilganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "👤 Reklama yuborilmaydigan foydalanuvchining ID raqamini yoki @username'ini yozing.\n\n"
        "Eslatma: foydalanuvchi botga kamida bir marta murojaat qilgan bo'lishi kerak.\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_ADSEXCL_USER


async def adsexcl_new_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    identifier = (update.message.text or "").strip()
    chat_id = find_user_chat_id(identifier)

    if chat_id is None:
        await update.message.reply_text(
            "❌ Bunday foydalanuvchi topilmadi (u botga hali murojaat qilmagan bo'lishi mumkin).\n"
            "Qaytadan urinib ko'ring, yoki /cancel bilan bekor qiling."
        )
        return WAITING_ADSEXCL_USER

    set_ads_excluded(chat_id, True)
    username = get_username(chat_id)
    label = f"@{username}" if username else str(chat_id)

    excluded = get_excluded_ads_users()
    keyboard = [[InlineKeyboardButton("➕ Yangi qo'shish", callback_data="adm:adsexclnew")]]
    for cid, uname in excluded:
        lbl = f"@{uname}" if uname else str(cid)
        keyboard.append([InlineKeyboardButton(f"🚫 {lbl}", callback_data=f"adm:adsexcluser:{cid}")])
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="adm:broadcast")])
    keyboard.append(home_button_row())

    await update.message.reply_text(
        f"✅ {label} reklama yuborilmaydiganlar ro'yxatiga qo'shildi.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


async def adsexcl_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ============ "DOIM YUBORILADI" RO'YXATI (/admin -> Reklama -> ✅) ============
# "Reklama yuborilmaydiganlar"ning aksi - bu yerga qo'shilgan foydalanuvchi
# YOKI KANAL, auditoriya (oddiy/VIP/hammaga) va "yuborilmaydiganlar"
# ro'yxatidan qat'i nazar, HAR DOIM reklamani oladi. Kanal qo'shish uchun
# bot o'sha kanalda ADMIN bo'lishi shart.

def _adsalways_icon(kind: str) -> str:
    return "📺" if kind == "channel" else "✅"


async def render_adsalways_list(query):
    """'Doim yuboriladi' ro'yxatini (➕ Yangi qo'shish tugmasi bilan birga) chizadi."""
    items = get_always_send_list()
    keyboard = [[InlineKeyboardButton("➕ Yangi qo'shish", callback_data="adm:adsalwaysnew")]]
    for chat_id, label, kind in items:
        icon = _adsalways_icon(kind)
        keyboard.append([InlineKeyboardButton(f"{icon} {label}", callback_data=f"adm:adsalwaysitem:{chat_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="adm:broadcast")])
    keyboard.append(home_button_row())

    text = (
        "✅ 'Doim yuboriladi' ro'yxati:\n\n"
        "Bu yerdagi foydalanuvchi/kanallarga auditoriya tanlovi va "
        "'yuborilmaydiganlar' ro'yxatidan qat'i nazar HAR DOIM reklama yuboriladi."
        if items
        else "✅ Hozircha 'Doim yuboriladi' ro'yxati bo'sh.\n\n"
        "Bu yerga qo'shilgan foydalanuvchi/kanallarga har doim reklama yuboriladi."
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def adm_adsalways_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"✅ Doim yuboriladi" tugmasi bosilganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await render_adsalways_list(query)
    return ConversationHandler.END


async def adm_adsalways_item_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ro'yxatdagi bitta yozuv tugmasi bosilganda - tafsilot va o'chirish tugmasini ko'rsatadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    target_chat_id = int(query.data.split(":")[2])

    items = dict((cid, (label, kind)) for cid, label, kind in get_always_send_list())
    label, kind = items.get(target_chat_id, (str(target_chat_id), "user"))
    icon = _adsalways_icon(kind)
    kind_label = "Kanal/guruh" if kind == "channel" else "Foydalanuvchi"

    keyboard = [
        [InlineKeyboardButton("🗑 Ro'yxatdan olib tashlash", callback_data=f"adm:adsalwaysremove:{target_chat_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="adm:adsalways")],
        home_button_row(),
    ]
    await query.edit_message_text(
        f"{icon} {label}\nTuri: {kind_label}\nID: {target_chat_id}\n\n"
        "Bu chatga HAR DOIM reklama yuboriladi (auditoriya tanlovi va "
        "'yuborilmaydiganlar' ro'yxatidan qat'i nazar).",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def adm_adsalways_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"🗑 Ro'yxatdan olib tashlash" tugmasi bosilganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    target_chat_id = int(query.data.split(":")[2])
    remove_always_send(target_chat_id)
    await render_adsalways_list(query)


async def adsalways_new_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"➕ Yangi qo'shish" tugmasi bosilganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "✅ 'Doim yuboriladi' ro'yxatiga qo'shish\n\n"
        "Quyidagilardan BIRINI yuboring:\n"
        "• Foydalanuvchining ID raqami yoki @username'i\n"
        "  (botga kamida bir marta murojaat qilgan bo'lishi kerak)\n"
        "• Kanal/guruh havolasi yoki @username'i (bot u yerda ADMIN bo'lishi shart)\n"
        "• YOKI kanaldan/guruhdan istalgan xabarni shu yerga FORWARD qiling\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_ADSALWAYS_ITEM


async def adsalways_new_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, label, kind = await resolve_broadcast_target(context, update.message)

    if chat_id is None:
        # 'label' bu holatda xato matni
        await update.message.reply_text(
            f"{label}\n\nQaytadan urinib ko'ring, yoki /cancel bilan bekor qiling."
        )
        return WAITING_ADSALWAYS_ITEM

    add_always_send(chat_id, label, kind)
    icon = _adsalways_icon(kind)

    items = get_always_send_list()
    keyboard = [[InlineKeyboardButton("➕ Yangi qo'shish", callback_data="adm:adsalwaysnew")]]
    for cid, lbl, knd in items:
        keyboard.append(
            [InlineKeyboardButton(f"{_adsalways_icon(knd)} {lbl}", callback_data=f"adm:adsalwaysitem:{cid}")]
        )
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="adm:broadcast")])
    keyboard.append(home_button_row())

    await update.message.reply_text(
        f"✅ {icon} {label} 'Doim yuboriladi' ro'yxatiga qo'shildi.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


async def adsalways_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


async def render_vip_menu(query):
    """VIP foydalanuvchilar ro'yxatini (tepada 'Yangi VIP' tugmasi bilan) chizadi."""
    vip_users = get_vip_users()

    keyboard = [[InlineKeyboardButton("🆕 Yangi VIP", callback_data="adm:vipnew")]]
    for chat_id, username, vip_until in vip_users:
        label = f"@{username}" if username else str(chat_id)
        keyboard.append([InlineKeyboardButton(f"⭐ {label}", callback_data=f"adm:vipuser:{chat_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="adm:menu")])
    keyboard.append(home_button_row())

    text = (
        "⭐ VIP foydalanuvchilar:" if vip_users
        else "⭐ Hozircha faol VIP foydalanuvchilar yo'q."
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def adm_vip_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panelda "⭐ VIP status berish" tugmasi bosilganda - VIP ro'yxatini ko'rsatadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    await render_vip_menu(query)


async def render_vipuser_detail(query, target_chat_id: int):
    """Bitta VIP foydalanuvchi haqida ma'lumot va boshqaruv tugmalarini chizadi."""
    username = get_username(target_chat_id)
    vip_until = get_vip_until(target_chat_id)
    label = f"@{username}" if username else str(target_chat_id)

    keyboard = [
        [InlineKeyboardButton("➕ Muddatni uzaytirish", callback_data=f"adm:vipextend:{target_chat_id}")],
        [InlineKeyboardButton("➖ Muddatni qisqartirish", callback_data=f"adm:vipreduce:{target_chat_id}")],
        [InlineKeyboardButton("❌ VIP ni bekor qilish", callback_data=f"adm:vipcanceling:{target_chat_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="adm:vip")],
        home_button_row(),
    ]
    await query.edit_message_text(
        f"⭐ {label}\nID: {target_chat_id}\nTugash sanasi: {vip_until}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def adm_vipuser_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ro'yxatdan biror VIP foydalanuvchi tanlanganda - uning ma'lumoti va boshqaruv tugmalari."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    target_chat_id = int(query.data.split(":")[2])
    await render_vipuser_detail(query, target_chat_id)


async def vipadjust_back_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VIP muddatini uzaytirish/qisqartirish kutilayotgan holatda "🔙 Orqaga" bosilganda
    suhbatni bekor qilib, o'sha foydalanuvchi detali sahifasiga qaytaradi."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("vip_adjust_action", None)
    context.user_data.pop("vip_adjust_target", None)

    target_chat_id = int(query.data.split(":")[2])
    await render_vipuser_detail(query, target_chat_id)
    return ConversationHandler.END


async def adm_vipcancel_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VIP ni bekor qilishdan oldin tasdiqlash so'raydi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    target_chat_id = int(query.data.split(":")[2])
    keyboard = [
        [InlineKeyboardButton("✅ Ha, bekor qilish", callback_data=f"adm:vipcanceldo:{target_chat_id}")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm:vipuser:{target_chat_id}")],
        home_button_row(),
    ]
    await query.edit_message_text(
        "⚠️ Haqiqatan ham bu foydalanuvchining VIP statusini butunlay bekor qilmoqchimisiz?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def adm_vipcancel_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VIP ni haqiqatan bekor qiladi (darhol kanaldan chiqarish va VIP2
    xabarini yuborish bilan birga) va ro'yxatga qaytaradi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    target_chat_id = int(query.data.split(":")[2])
    revoke_vip(target_chat_id)
    await _process_single_vip_expiry(context, target_chat_id)
    await render_vip_menu(query)


async def vip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin VIP ro'yxatidagi "🆕 Yangi VIP" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="adm:vipback")], home_button_row()])
    await query.edit_message_text(
        "👤 VIP status beriladigan foydalanuvchining ID raqamini yoki "
        "@username'ini yozing.\n\n"
        "Eslatma: foydalanuvchi botga kamida bir marta murojaat qilgan "
        "bo'lishi kerak (aks holda bot uni topa olmaydi).\n\n"
        "Bekor qilish uchun /cancel yozing, yoki pastdagi tugmani bosing.",
        reply_markup=keyboard,
    )
    return WAITING_VIP_USER


async def vip_receive_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    identifier = (update.message.text or "").strip()
    chat_id = find_user_chat_id(identifier)

    if chat_id is None:
        await update.message.reply_text(
            "❌ Bunday foydalanuvchi topilmadi (u botga hali murojaat qilmagan "
            "bo'lishi mumkin).\nQaytadan urinib ko'ring, yoki /cancel bilan bekor qiling."
        )
        return WAITING_VIP_USER

    context.user_data["vip_target_chat_id"] = chat_id

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="adm:vipback")], home_button_row()])
    await update.message.reply_text(
        "📅 Necha kunga VIP status berilsin? (butun son kiriting, masalan: 30)\n\n"
        "Bekor qilish uchun /cancel yozing, yoki pastdagi tugmani bosing.",
        reply_markup=keyboard,
    )
    return WAITING_VIP_DAYS


async def vip_receive_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text(
            "❌ Musbat butun son kiriting (masalan: 30), yoki /cancel bilan bekor qiling."
        )
        return WAITING_VIP_DAYS

    days = int(text)
    chat_id = context.user_data.get("vip_target_chat_id")
    if chat_id is None:
        await update.message.reply_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    set_vip(chat_id, days)
    vip_until = get_vip_until(chat_id)

    await update.message.reply_text(
        f"✅ VIP status berildi!\nFoydalanuvchi: {chat_id}\nMuddat: {days} kun\n"
        f"Tugash sanasi: {vip_until}"
    )

    # Yangi VIP foydalanuvchiga o'z tarifi haqida xabar va VIP1 kodli postni yuboramiz
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🌟 Tabriklaymiz! Sizga VIP status berildi.\n\n"
                f"📅 Tarif muddati: {days} kun\n"
                f"⏰ Tugash sanasi: {vip_until}\n\n"
                "Endi sizga 🎮 O'yinlar bo'limi ochiq!"
            ),
        )
        vip_sent = await send_post_for_code(VIP_WELCOME_CODE, chat_id, context, allow_system=True)
        if vip_sent is None or vip_sent == VIP_REQUIRED:
            logger.info(
                "VIP xush kelibsiz posti (%s) topilmadi - admin uni /admin panel orqali qo'shishi kerak.",
                VIP_WELCOME_CODE,
            )
    except Exception:
        logger.exception("VIP foydalanuvchiga xabar yuborishda xatolik")
        await update.message.reply_text(
            "⚠️ Foydalanuvchiga xabar yuborib bo'lmadi (ehtimol u botni bloklagan)."
        )

    context.user_data.pop("vip_target_chat_id", None)
    return ConversationHandler.END


async def vipadjust_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "➕ Muddatni uzaytirish" yoki "➖ Muddatni qisqartirish" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    parts = query.data.split(":")  # "adm:vipextend:123" yoki "adm:vipreduce:123"
    action = "extend" if parts[1] == "vipextend" else "reduce"
    target_chat_id = int(parts[2])

    context.user_data["vip_adjust_action"] = action
    context.user_data["vip_adjust_target"] = target_chat_id

    verb = "qo'shmoqchisiz" if action == "extend" else "ayirmoqchisiz"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Orqaga", callback_data=f"adm:vipuser:{target_chat_id}")], home_button_row()]
    )
    await query.edit_message_text(
        f"📅 Necha kun {verb}? (butun son kiriting, masalan: 7)\n\n"
        "Bekor qilish uchun /cancel yozing, yoki pastdagi tugmani bosing.",
        reply_markup=keyboard,
    )
    return WAITING_VIP_ADJUST_DAYS


async def vipadjust_receive_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text(
            "❌ Musbat butun son kiriting (masalan: 7), yoki /cancel bilan bekor qiling."
        )
        return WAITING_VIP_ADJUST_DAYS

    days = int(text)
    action = context.user_data.pop("vip_adjust_action", None)
    target_chat_id = context.user_data.pop("vip_adjust_target", None)

    if action is None or target_chat_id is None:
        await update.message.reply_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    became_expired = adjust_vip_days(target_chat_id, days if action == "extend" else -days)
    vip_until = get_vip_until(target_chat_id)

    verb = "uzaytirildi" if action == "extend" else "qisqartirildi"
    extra_note = ""
    if became_expired:
        extra_note = "\n\n⏰ Bu qisqartirish natijasida VIP muddati allaqachon tugadi - foydalanuvchi darhol xabardor qilinmoqda va kanaldan chiqarilmoqda."

    await update.message.reply_text(
        f"✅ Muddat {verb}!\nFoydalanuvchi: {target_chat_id}\nYangi tugash sanasi: {vip_until}{extra_note}"
    )

    if became_expired:
        await _process_single_vip_expiry(context, target_chat_id)

    return ConversationHandler.END


async def vip_back_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VIP suhbati davomida (matn kiritish kutilayotganda) "🔙 Orqaga" bosilganda
    suhbatni bekor qilib, VIP ro'yxatiga qaytaradi."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("vip_target_chat_id", None)
    context.user_data.pop("vip_adjust_action", None)
    context.user_data.pop("vip_adjust_target", None)
    await render_vip_menu(query)
    return ConversationHandler.END


async def vip_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("vip_target_chat_id", None)
    context.user_data.pop("vip_adjust_action", None)
    context.user_data.pop("vip_adjust_target", None)
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ============ BAZA GURUHINI SOZLASH (/admin -> 🗄 Baza guruhi) ============

async def db_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "🗄 Baza guruhi" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    current = get_storage_chat_id()
    current_text = (
        f"\n\nHozirgi baza guruhi ID: `{current}`" if current
        else "\n\nHozircha baza guruhi sozlanmagan (postlar admin bilan shaxsiy chatda saqlanmoqda)."
    )

    await query.edit_message_text(
        "🗄 Baza guruhini sozlash\n\n"
        "1️⃣ Avval GURUH yarating va BOTNI shu guruhga ADMIN qilib qo'shing "
        "(bu qadamni Telegram ilovasi orqali qo'lda bajarishingiz kerak - "
        "bot havola orqali o'zi guruhga qo'shila olmaydi).\n\n"
        "2️⃣ Keyin shu yerga quyidagilardan BIRINI yuboring:\n"
        "   • guruhning ochiq havolasi (masalan https://t.me/mygroup)\n"
        "   • YOKI guruhdan istalgan xabarni shu yerga FORWARD qiling "
        "(yopiq guruhlar uchun ham ishlaydigan eng ishonchli usul)\n"
        f"{current_text}\n\nBekor qilish uchun /cancel yozing.",
        parse_mode="Markdown",
    )
    return WAITING_DB_GROUP


async def db_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    candidate = None

    # 1) Guruhdan forward qilingan xabar bo'lsa - undan chat_id ni olamiz
    origin = getattr(message, "forward_origin", None)
    if origin is not None and getattr(origin, "chat", None) is not None:
        candidate = origin.chat.id
    else:
        fwd_chat = getattr(message, "forward_from_chat", None)
        if fwd_chat is not None:
            candidate = fwd_chat.id

    # 2) Aks holda matn sifatida - havola, @username yoki ID bo'lishi mumkin
    if candidate is None:
        text = (message.text or "").strip()

        if text.startswith("@"):
            candidate = text
        elif "t.me/" in text:
            path = text.split("t.me/", 1)[1].split("?")[0].strip("/")
            if path.startswith("+") or path.lower().startswith("joinchat"):
                await message.reply_text(
                    "⚠️ Bu yopiq guruhning shaxsiy taklif havolasi - botlar bunday "
                    "havolalar orqali guruhni aniqlay olmaydi.\n\n"
                    "Iltimos, o'sha guruhdan istalgan xabarni shu yerga FORWARD qiling "
                    "(bot o'sha guruhda admin bo'lsa kifoya), yoki /cancel bilan bekor qiling."
                )
                return WAITING_DB_GROUP
            candidate = f"@{path}"
        elif text.lstrip("-").isdigit():
            candidate = int(text)
        else:
            await message.reply_text(
                "❌ Tushunarsiz format. Guruh havolasini, @username'ini, ID raqamini yuboring, "
                "yoki guruhdan xabar forward qiling.\n\nBekor qilish uchun /cancel yozing."
            )
            return WAITING_DB_GROUP

    # Bot haqiqatan ham shu chatga kira olishini tekshiramiz
    try:
        chat = await context.bot.get_chat(candidate)
    except Exception:
        logger.exception("Baza guruhini aniqlashda xatolik: %s", candidate)
        await message.reply_text(
            "❌ Bu guruhni topib bo'lmadi. Ehtimol bot hali o'sha guruhga qo'shilmagan.\n"
            "Tekshirib, qaytadan urinib ko'ring, yoki /cancel bilan bekor qiling."
        )
        return WAITING_DB_GROUP

    # Bot shu guruhda ADMIN ekanligini tekshiramiz (xabar nusxalab yubora olishi uchun shart)
    try:
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        is_group_admin = member.status in ("administrator", "creator")
        # "Pin messages" huquqi alohida tekshiriladi - bazani zaxiralash/tiklash
        # tizimi FAQAT shu huquq orqali ishlaydi (Bot API'da guruh tarixini
        # "qidirish" imkoni umuman yo'q - faqat PIN qilingan xabarni topish
        # mumkin, shuning uchun bu huquq juda muhim).
        can_pin = getattr(member, "can_pin_messages", False) or member.status == "creator"
    except Exception:
        is_group_admin = False
        can_pin = False

    if not is_group_admin:
        await message.reply_text(
            f"⚠️ Topildi: {chat.title or chat.id}, lekin bot bu yerda ADMIN emas.\n"
            "Iltimos, botni shu guruhda administrator qiling, so'ng qaytadan yuboring.\n\n"
            "Bekor qilish uchun /cancel yozing."
        )
        return WAITING_DB_GROUP

    pin_warning = ""
    if not can_pin:
        pin_warning = (
            "\n\n🔴 DIQQAT - JIDDIY MUAMMO: botda \"Pin messages\" (xabarlarni "
            "qadash) huquqi YO'Q!\n"
            "Ma'lumotlar bazasini zaxiralash/tiklash tizimi FAQAT shu huquq "
            "orqali ishlaydi - Telegram Bot API botlarga guruh tarixini "
            "\"qidirish\" imkonini bermaydi, faqat PIN qilingan xabarni topish "
            "mumkin. Shu huquqsiz, zaxira yuklanadi, lekin bot uni HECH QACHON "
            "qayta topa olmaydi va baza yo'qolganda tiklay olmaydi!\n\n"
            "Iltimos, guruh sozlamalaridan (Administrators → bot) "
            "\"Pin Messages\" huquqini albatta yoqing."
        )

    set_setting("storage_chat_id", str(chat.id))
    await message.reply_text(
        f"✅ Baza guruhi sozlandi!\nGuruh: {chat.title or chat.id}\nID: {chat.id}\n\n"
        "Bundan buyon /add yoki /add_game orqali qo'shiladigan barcha postlar "
        "shu guruhda xavfsiz saqlanadi."
        f"{pin_warning}\n\n"
        "⚠️ MUHIM (ishonchlilik uchun QATTIQ TAVSIYA ETILADI): Render (yoki "
        "boshqa serveringiz) sozlamalarida \"Environment\" bo'limiga quyidagini "
        "QO'LDA qo'shing:\n\n"
        f"STORAGE_CHAT_ID = {chat.id}\n\n"
        "Sababi: bu ID hozircha faqat botning ma'lumotlar bazasida saqlangan. "
        "Agar baza fayli biror sababdan yo'qolib qolsa (masalan qayta deploy "
        "paytida), muhit o'zgaruvchisi bo'lmasa, bot 'qayerdan tiklashim kerak' "
        "degan savolga javob topa olmay qoladi. Muhit o'zgaruvchisi esa fayl "
        "tizimidan mustaqil - u har doim saqlanib qoladi."
    )
    return ConversationHandler.END


async def db_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ============ VIP KANALNI SOZLASH (/admin -> 📺 VIP kanal) ============

async def vipchannel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "📺 VIP kanal" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    current = get_vip_channel_id()
    current_text = (
        f"\n\nHozirgi VIP kanal ID: `{current}`" if current
        else "\n\nHozircha VIP kanal sozlanmagan."
    )

    await query.edit_message_text(
        "📺 VIP kanalni sozlash\n\n"
        "1️⃣ Avval KANAL yarating (yopiq bo'lishi mumkin) va uning sozlamalarida "
        "\"Qo'shilish so'rovlarini tasdiqlash\" (Join Requests) yoqilganligiga "
        "ishonch hosil qiling.\n"
        "2️⃣ BOTNI shu kanalga ADMIN qilib qo'shing (\"Foydalanuvchilarni qo'shish\" "
        "huquqi bilan - bu so'rovlarni tasdiqlash uchun shart).\n\n"
        "3️⃣ Keyin shu yerga quyidagilardan BIRINI yuboring:\n"
        "   • kanalning ochiq havolasi (masalan https://t.me/mychannel)\n"
        "   • YOKI kanaldan istalgan xabarni shu yerga FORWARD qiling\n"
        f"{current_text}\n\nBekor qilish uchun /cancel yozing.",
        parse_mode="Markdown",
    )
    return WAITING_VIP_CHANNEL


async def vipchannel_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    candidate = None

    origin = getattr(message, "forward_origin", None)
    if origin is not None and getattr(origin, "chat", None) is not None:
        candidate = origin.chat.id
    else:
        fwd_chat = getattr(message, "forward_from_chat", None)
        if fwd_chat is not None:
            candidate = fwd_chat.id

    if candidate is None:
        text = (message.text or "").strip()

        if text.startswith("@"):
            candidate = text
        elif "t.me/" in text:
            path = text.split("t.me/", 1)[1].split("?")[0].strip("/")
            if path.startswith("+") or path.lower().startswith("joinchat"):
                await message.reply_text(
                    "⚠️ Bu yopiq kanalning shaxsiy taklif havolasi - botlar bunday "
                    "havolalar orqali kanalni aniqlay olmaydi.\n\n"
                    "Iltimos, o'sha kanaldan istalgan xabarni shu yerga FORWARD qiling, "
                    "yoki /cancel bilan bekor qiling."
                )
                return WAITING_VIP_CHANNEL
            candidate = f"@{path}"
        elif text.lstrip("-").isdigit():
            candidate = int(text)
        else:
            await message.reply_text(
                "❌ Tushunarsiz format. Kanal havolasini, @username'ini, ID raqamini yuboring, "
                "yoki kanaldan xabar forward qiling.\n\nBekor qilish uchun /cancel yozing."
            )
            return WAITING_VIP_CHANNEL

    try:
        chat = await context.bot.get_chat(candidate)
    except Exception:
        logger.exception("VIP kanalni aniqlashda xatolik: %s", candidate)
        await message.reply_text(
            "❌ Bu kanalni topib bo'lmadi. Ehtimol bot hali o'sha kanalga qo'shilmagan.\n"
            "Tekshirib, qaytadan urinib ko'ring, yoki /cancel bilan bekor qiling."
        )
        return WAITING_VIP_CHANNEL

    try:
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        is_channel_admin = member.status in ("administrator", "creator")
    except Exception:
        is_channel_admin = False

    if not is_channel_admin:
        await message.reply_text(
            f"⚠️ Topildi: {chat.title or chat.id}, lekin bot bu yerda ADMIN emas.\n"
            "Iltimos, botni shu kanalda administrator qiling (Foydalanuvchilarni qo'shish "
            "huquqi bilan), so'ng qaytadan yuboring.\n\nBekor qilish uchun /cancel yozing."
        )
        return WAITING_VIP_CHANNEL

    set_setting("vip_channel_id", str(chat.id))
    await message.reply_text(
        f"✅ VIP kanal sozlandi!\nKanal: {chat.title or chat.id}\nID: {chat.id}\n\n"
        "Endi VIP statusi bor foydalanuvchilarning shu kanalga qo'shilish so'rovlari "
        "avtomatik tasdiqlanadi, VIP bo'lmaganlarniki e'tiborsiz qoldiriladi, va VIP "
        "muddati tugagan foydalanuvchilar kanaldan avtomatik chiqarib yuboriladi."
    )
    return ConversationHandler.END


async def vipchannel_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ============ "AVTO QO'SHISH" KANALINI SOZLASH (/admin -> 🤖 Avto qo'shish) ============
# VIP kanaldan farqi: bu yerda HAR QANDAY foydalanuvchining qo'shilish
# so'rovi (VIP statusidan qat'i nazar) avtomatik tasdiqlanadi, va hech kim
# keyinchalik avtomatik chiqarib yuborilmaydi (muddat tekshiruvi yo'q).

async def autoaccept_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "🤖 Avto qo'shish" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    current = get_auto_accept_channel_id()
    current_text = (
        f"\n\nHozirgi 'Avto qo'shish' kanal ID: `{current}`" if current
        else "\n\nHozircha 'Avto qo'shish' kanali sozlanmagan."
    )

    await query.edit_message_text(
        "🤖 'Avto qo'shish' kanalini sozlash\n\n"
        "Bu kanalga yuborilgan HAR QANDAY qo'shilish so'rovi (VIP yoki "
        "oddiy foydalanuvchidan qat'i nazar) avtomatik tasdiqlanadi. "
        "VIP kanaldan farqli o'laroq, bu yerdan hech kim keyinchalik "
        "avtomatik chiqarib yuborilmaydi.\n\n"
        "1️⃣ Avval KANAL yarating va uning sozlamalarida \"Qo'shilish "
        "so'rovlarini tasdiqlash\" (Join Requests) yoqilganligiga ishonch "
        "hosil qiling.\n"
        "2️⃣ BOTNI shu kanalga ADMIN qilib qo'shing (\"Foydalanuvchilarni "
        "qo'shish\" huquqi bilan).\n\n"
        "3️⃣ Keyin shu yerga quyidagilardan BIRINI yuboring:\n"
        "   • kanalning ochiq havolasi (masalan https://t.me/mychannel)\n"
        "   • YOKI kanaldan istalgan xabarni shu yerga FORWARD qiling\n"
        f"{current_text}\n\nBekor qilish uchun /cancel yozing.",
        parse_mode="Markdown",
    )
    return WAITING_AUTOACCEPT_CHANNEL


async def autoaccept_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    candidate = None

    origin = getattr(message, "forward_origin", None)
    if origin is not None and getattr(origin, "chat", None) is not None:
        candidate = origin.chat.id
    else:
        fwd_chat = getattr(message, "forward_from_chat", None)
        if fwd_chat is not None:
            candidate = fwd_chat.id

    if candidate is None:
        text = (message.text or "").strip()

        if text.startswith("@"):
            candidate = text
        elif "t.me/" in text:
            path = text.split("t.me/", 1)[1].split("?")[0].strip("/")
            if path.startswith("+") or path.lower().startswith("joinchat"):
                await message.reply_text(
                    "⚠️ Bu yopiq kanalning shaxsiy taklif havolasi - botlar bunday "
                    "havolalar orqali kanalni aniqlay olmaydi.\n\n"
                    "Iltimos, o'sha kanaldan istalgan xabarni shu yerga FORWARD qiling, "
                    "yoki /cancel bilan bekor qiling."
                )
                return WAITING_AUTOACCEPT_CHANNEL
            candidate = f"@{path}"
        elif text.lstrip("-").isdigit():
            candidate = int(text)
        else:
            await message.reply_text(
                "❌ Tushunarsiz format. Kanal havolasini, @username'ini, ID raqamini yuboring, "
                "yoki kanaldan xabar forward qiling.\n\nBekor qilish uchun /cancel yozing."
            )
            return WAITING_AUTOACCEPT_CHANNEL

    try:
        chat = await context.bot.get_chat(candidate)
    except Exception:
        logger.exception("'Avto qo'shish' kanalini aniqlashda xatolik: %s", candidate)
        await message.reply_text(
            "❌ Bu kanalni topib bo'lmadi. Ehtimol bot hali o'sha kanalga qo'shilmagan.\n"
            "Tekshirib, qaytadan urinib ko'ring, yoki /cancel bilan bekor qiling."
        )
        return WAITING_AUTOACCEPT_CHANNEL

    try:
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        is_channel_admin = member.status in ("administrator", "creator")
    except Exception:
        is_channel_admin = False

    if not is_channel_admin:
        await message.reply_text(
            f"⚠️ Topildi: {chat.title or chat.id}, lekin bot bu yerda ADMIN emas.\n"
            "Iltimos, botni shu kanalda administrator qiling (Foydalanuvchilarni qo'shish "
            "huquqi bilan), so'ng qaytadan yuboring.\n\nBekor qilish uchun /cancel yozing."
        )
        return WAITING_AUTOACCEPT_CHANNEL

    set_setting("auto_accept_channel_id", str(chat.id))
    await message.reply_text(
        f"✅ 'Avto qo'shish' kanali sozlandi!\nKanal: {chat.title or chat.id}\nID: {chat.id}\n\n"
        "Endi bu kanalga yuborilgan HAR QANDAY qo'shilish so'rovi (VIP yoki oddiy "
        "foydalanuvchidan qat'i nazar) avtomatik tasdiqlanadi."
    )
    return ConversationHandler.END


async def autoaccept_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ============ VIP1 / VIP2 MAXSUS POSTLARINI SOZLASH ============
# (/admin -> 🎁 VIP boshlanish posti / ⏰ VIP tugash posti)

VIP_SPECIAL_LABELS = {
    VIP_WELCOME_CODE: "🎁 VIP boshlanish posti (VIP status berilganda avtomatik yuboriladi)",
    VIP_EXPIRED_CODE: "⏰ VIP tugash posti (VIP muddati tugaganda avtomatik yuboriladi)",
}


async def vipspecial_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "VIP boshlanish posti" yoki "VIP tugash posti" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    code = VIP_WELCOME_CODE if query.data == "adm:setvip1" else VIP_EXPIRED_CODE
    context.user_data["vip_special_code"] = code
    label = VIP_SPECIAL_LABELS[code]

    existing = get_post_by_code(code)
    existing_note = "\n\n⚠️ Hozir bu kodga biriktirilgan post bor - yangisini yuborsangiz, ESKISI ALMASHTIRILADI." if existing else ""

    await query.edit_message_text(
        f"{label}\n\n"
        "Postni yuboring (video, rasm, hujjat yoki oddiy matn bo'lishi mumkin)."
        f"{existing_note}\n\nBekor qilish uchun /cancel yozing."
    )
    return WAITING_VIP_SPECIAL_POST


async def vipspecial_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = context.user_data.pop("vip_special_code", None)
    if not code:
        await update.message.reply_text("⚠️ Sessiya topilmadi. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    message = update.message
    preview = make_preview(message)

    # Boshqa postlar kabi, agar "baza guruhi" sozlangan bo'lsa - shu yerga nusxalab saqlaymiz
    storage_chat_id = message.chat_id
    storage_message_id = message.message_id
    db_group_id = get_storage_chat_id()
    if db_group_id:
        try:
            stored = await context.bot.copy_message(
                chat_id=db_group_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
            storage_chat_id = db_group_id
            storage_message_id = stored.message_id
        except Exception:
            logger.exception("VIP maxsus postini saqlash guruhiga nusxalab bo'lmadi (kod=%s)", code)

    post_id = save_post(
        storage_chat_id,
        storage_message_id,
        preview,
        code,
        update.effective_user.id,
        category=CATEGORY_SYSTEM,
        visibility=VISIBILITY_ADMIN,
    )
    save_codes([code], post_id)

    label = VIP_SPECIAL_LABELS[code]
    await update.message.reply_text(f"✅ Saqlandi!\n{label}")
    return ConversationHandler.END


async def vipspecial_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("vip_special_code", None)
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


async def handle_chat_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Har qanday kanal/guruhga qo'shilish so'rovi kelganda ishga tushadi.

    1) Agar bu VIP kanal bo'lsa: VIP foydalanuvchi -> avtomatik tasdiqlanadi,
       VIP bo'lmagan foydalanuvchi -> e'tiborsiz qoldiriladi (so'rov kutishda qoladi).
    2) Agar bu "Avto qo'shish" kanali bo'lsa: HAR QANDAY foydalanuvchi
       (VIP statusidan qat'i nazar) darhol avtomatik tasdiqlanadi - va
       (VIP kanaldan farqli o'laroq) keyinchalik hech kim avtomatik
       chiqarib yuborilmaydi.

    Boshqa chatlardagi so'rovlarga (agar bo'lsa) tegilmaydi.
    """
    request = update.chat_join_request
    chat_id = request.chat.id
    user_id = request.from_user.id

    vip_channel_id = get_vip_channel_id()
    auto_accept_channel_id = get_auto_accept_channel_id()

    if auto_accept_channel_id and chat_id == auto_accept_channel_id:
        try:
            await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            save_user(user_id, request.from_user.username)
        except Exception:
            logger.exception("'Avto qo'shish' kanaliga so'rovni tasdiqlashda xatolik: %s", user_id)
        return

    if not vip_channel_id or chat_id != vip_channel_id:
        return

    if is_vip(user_id):
        try:
            await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            save_user(user_id, request.from_user.username)
        except Exception:
            logger.exception("VIP kanalga qo'shilish so'rovini tasdiqlashda xatolik: %s", user_id)
    # VIP bo'lmasa - hech narsa qilmaymiz, so'rov kutishda (pending) qoladi.


async def _process_single_vip_expiry(context: ContextTypes.DEFAULT_TYPE, uid: int):
    """
    Bitta foydalanuvchi uchun "VIP tugadi" holatini qayta ishlaydi:
      1) Agar VIP kanal sozlangan bo'lsa - o'sha kanaldan avtomatik chiqarib
         yuboradi (ban+unban - shunda kelajakda qaytadan qo'shilish so'rovi
         yuborishlari mumkin bo'ladi)
      2) VIP kanal sozlanган-sozlanmaganidan QAT'I NAZAR - foydalanuvchiga
         xabar va VIP2 kodli postni yuboradi
    Bu funksiya HAM avtomatik (job_queue) HAM qo'lda (admin "Bekor qilish"/
    "Qisqartirish" tugmalari) VIP tugashi holatlarida ishlatiladi.
    """
    vip_channel_id = get_vip_channel_id()
    if vip_channel_id:
        try:
            await context.bot.ban_chat_member(chat_id=vip_channel_id, user_id=uid)
            await context.bot.unban_chat_member(chat_id=vip_channel_id, user_id=uid, only_if_banned=True)
        except Exception:
            # Foydalanuvchi kanalda umuman bo'lmagan bo'lishi mumkin - bu normal holat.
            logger.info("VIP kanaldan chiqarishda kutilgan xatolik (ehtimol u yerda emas): %s", uid)

    try:
        await context.bot.send_message(
            chat_id=uid,
            text="⏰ VIP tarifingiz muddati tugadi.\n\n"
                 "Qayta VIP olish uchun admin bilan bog'laning.",
        )
        vip2_sent = await send_post_for_code(VIP_EXPIRED_CODE, uid, context, allow_system=True)
        if vip2_sent in (None, VIP_REQUIRED):
            logger.info(
                "VIP2 kodli post topilmadi/yuborilmadi (kod=%s, foydalanuvchi=%s) - "
                "admin uni /admin panel orqali qo'shishi mumkin.",
                VIP_EXPIRED_CODE, uid,
            )
    except Exception:
        # Foydalanuvchi botni bloklagan bo'lishi mumkin - bu normal holat.
        logger.info("VIP tugashi haqida xabar yuborib bo'lmadi: %s", uid)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET vip_channel_removed = 1 WHERE chat_id = ?", (uid,))
    conn.commit()
    conn.close()


async def vip_expiry_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Doimiy ravishda (job_queue orqali) ishga tushadigan vazifa: VIP muddati
    o'tgan, lekin hali "qayta ishlanmagan" foydalanuvchilarni topib, har
    birini _process_single_vip_expiry orqali qayta ishlaydi.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """SELECT chat_id FROM users
           WHERE vip_until IS NOT NULL AND vip_until <= datetime('now')
             AND (vip_channel_removed IS NULL OR vip_channel_removed = 0)"""
    )
    expired_users = [r[0] for r in cur.fetchall()]
    conn.close()

    if not expired_users:
        return

    logger.info("VIP muddati tugagan %d foydalanuvchi qayta ishlanmoqda...", len(expired_users))

    for uid in expired_users:
        await _process_single_vip_expiry(context, uid)


VIP_REQUIRED = "VIP_REQUIRED"  # send_post_for_code uchun maxsus qaytariladigan belgi


async def send_post_for_code(
    code: str,
    target_chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reply_markup=None,
    allow_system: bool = False,
):
    """Berilgan kodga mos postni topib, target_chat_id'ga yuboradi.
    Muvaffaqiyatli bo'lsa yuborilgan xabar obyektini qaytaradi.
    Agar kod topilmasa yoki yuborishda xatolik bo'lsa - None.
    Agar bu O'YIN posti bo'lib, foydalanuvchida VIP status bo'lmasa - VIP_REQUIRED.

    allow_system=True FAQAT botning o'z ICHKI avtomatik yuborishlarida
    ishlatiladi (VIP berilganda VIP1, VIP tugaganda VIP2, "Mening statusim"da
    VIP1 ko'rsatilganda) - bu holatda kategoriya/ko'rinish cheklovlari
    butunlay chetlab o'tiladi. Oddiy foydalanuvchi kod yozganda yoki
    ro'yxatdan tanlaganda BU HECH QACHON True bo'lmasligi kerak - aks holda
    "system" (masalan VIP1/VIP2) postlari oshkor bo'lib qolishi mumkin.

    Har bir urinish (topilgan yoki topilmagan) statistika uchun loglanadi."""
    row = get_post_by_code(code)
    log_search(target_chat_id, code, found=(row is not None))

    if row is None:
        return None

    chat_id, message_id, preview, extra_button_text, extra_button_url, category, visibility = row

    if not allow_system:
        if category == CATEGORY_SYSTEM:
            # Yashirin tizim posti (masalan VIP1/VIP2) - oddiy kod qidiruvida
            # yoki ro'yxatda HECH QACHON ko'rinmaydi, "topilmadi" bilan bir xil.
            return None
        if category == CATEGORY_GAME and not is_vip(target_chat_id):
            return VIP_REQUIRED
        if visibility == VISIBILITY_VIP and not is_vip(target_chat_id):
            return VIP_REQUIRED
        if visibility == VISIBILITY_ADMIN and not is_admin(target_chat_id):
            # Admin uchun mo'ljallangan post - boshqalarga "umuman mavjud emas"
            # sifatida ko'rsatiladi (yashirin post).
            return None

    # Agar post uchun link-tugma belgilangan bo'lsa, uni ishlatamiz (bitta
    # xabarga faqat bitta reply_markup biriktirish mumkin, shuning uchun bu
    # holatda pastdagi doimiy klaviatura o'rniga shu tugma ko'rsatiladi -
    # doimiy klaviatura keyingi javoblarda qayta chiqadi).
    final_markup = reply_markup
    if extra_button_url:
        final_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=extra_button_text or "🔗 Havola", url=extra_button_url)]]
        )

    try:
        sent = await context.bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=chat_id,
            message_id=message_id,
            reply_markup=final_markup,
        )
        return sent
    except Exception:
        logger.exception("Postni yuborishda xatolik: kod=%s", code)
        return None


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi kod yuborganda (yoki pastdagi tugmani bosganda) ishlaydi."""
    text = (update.message.text or "").strip()

    if text.startswith("/"):
        return

    user_id = update.effective_user.id
    save_user(update.effective_chat.id, update.effective_user.username)
    keyboard = main_menu_markup()  # pastdagi tugmalar ADMIN uchun ham doim ko'rinadi

    # Agar pastdagi menyu tugmalaridan biri bosilsa - avval ochiq turgan
    # "Barcha postlar"/"O'yinlar" ro'yxati VA undan tanlab ochilgan (oxirgi)
    # post (agar bo'lsa) birga o'chiriladi. Shuningdek, foydalanuvchining
    # ANIQ SHU BOSGAN tugma matni (masalan "🎬 Barcha postlar" degan
    # xabarning o'zi) ham darhol o'chiriladi - u boshqa hech qanday tizim
    # orqali kuzatilmagani uchun aks holda chatda abadiy qolib ketardi.
    if text in (BTN_KINOLAR, BTN_VIP, BTN_GAMES, BTN_STATUS):
        list_id = context.chat_data.pop("open_list_message_id", None)
        last_post_id = context.chat_data.pop("open_list_last_post_id", None)
        for mid in (list_id, last_post_id):
            if mid is None:
                continue
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
            except Exception:
                pass
        try:
            await update.message.delete()
        except Exception:
            pass

    # Pastdagi doimiy tugmalar
    if text == BTN_KINOLAR:
        await list_movies(update, context)
        return

    if text == BTN_GAMES:
        await list_games(update, context)
        return

    if text == BTN_STATUS:
        await show_status(update, context)
        return

    if text == BTN_VIP:
        sent = await send_post_for_code(
            VIP_CODE, update.effective_chat.id, context, reply_markup=keyboard
        )
        if sent is None:
            sent = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⭐ VIP post hali qo'shilmagan.\n"
                     f"(Admin uchun: /add orqali post qo'shing va kod sifatida "
                     f"\"{VIP_CODE}\" yozing)",
                reply_markup=keyboard,
            )
        await track_and_trim(update, context, sent)
        return

    # Oddiy kod sifatida qidiramiz
    sent = await send_post_for_code(
        text, update.effective_chat.id, context, reply_markup=keyboard
    )
    if sent == VIP_REQUIRED:
        sent = await update.message.reply_text(
            "🔒 Bu o'yin faqat VIP foydalanuvchilar uchun ochiq.\n"
            "VIP status olish uchun admin bilan bog'laning.",
            reply_markup=keyboard,
        )
    elif sent is None:
        sent = await update.message.reply_text(
            "❌ Bunday kodli post topilmadi yoki uni yuborishda xatolik yuz berdi.\n"
            "Kodni tekshirib qaytadan yuboring, yoki pastdagi tugmalardan foydalaning.",
            reply_markup=keyboard,
        )
    await track_and_trim(update, context, sent)


async def handle_list_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/list dagi inline tugma bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()  # tugmadagi "yuklanmoqda" holatini olib tashlaydi

    if not query.data or not query.data.startswith("code:"):
        return
    code = query.data[len("code:"):]

    user_id = update.effective_user.id
    save_user(query.message.chat_id, update.effective_user.username)
    reply_markup = main_menu_markup()  # pastdagi tugmalar ADMIN uchun ham doim ko'rinadi

    sent = await send_post_for_code(
        code, query.message.chat_id, context, reply_markup=reply_markup
    )
    if sent == VIP_REQUIRED:
        sent = await query.message.reply_text(
            "🔒 Bu o'yin faqat VIP foydalanuvchilar uchun ochiq.\n"
            "VIP status olish uchun admin bilan bog'laning.",
            reply_markup=reply_markup,
        )
    elif sent is None:
        sent = await query.message.reply_text(
            "❌ Bu post topilmadi (o'chirilgan bo'lishi mumkin).",
            reply_markup=reply_markup,
        )

    # Agar bu tugma "Barcha postlar"/"O'yinlar" ochiq ro'yxatidan bosilgan
    # bo'lsa: avval SHU SESSIYADA oldin ochilgan post bo'lsa - uni o'chiramiz
    # (faqat oxirgi tanlangan post ko'rinishda qolishi uchun), keyin yangi
    # postni sessiyaga "oxirgi ochilgan" sifatida yozib qo'yamiz. Bunday
    # holatda oddiy 2-xabar trim tizimi ishlatilmaydi (sessiya alohida
    # boshqaradi, X yoki pastki menyu bosilguncha saqlanadi).
    if context.chat_data.get("open_list_message_id") == query.message.message_id:
        previous_post_id = context.chat_data.get("open_list_last_post_id")
        if previous_post_id is not None:
            try:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=previous_post_id)
            except Exception:
                pass

        if sent is not None and hasattr(sent, "message_id"):
            context.chat_data["open_list_last_post_id"] = sent.message_id
    else:
        await track_and_trim(update, context, sent)


async def handle_pinned_service_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Telegram'da biror xabar PIN qilinganda, u avtomatik ravishda
    "[Bot] xabarni pin qildi" degan ALOHIDA TIZIM XABARINI yaratadi - bu
    bizning bazani soatlik zaxiralash jarayonimizning yon ta'siri (chunki
    har safar yangi zaxira pin qilinadi). Bu bildirishnomalar vaqt o'tishi
    bilan to'planib, guruhni keraksiz xabarlar bilan to'ldirib yuborishi
    mumkin - shuning uchun ularni PAYDO BO'LISHI BILANOQ avtomatik
    o'chiramiz.
    """
    message = update.message
    if message is None or message.pinned_message is None:
        return
    try:
        await context.bot.delete_message(chat_id=message.chat_id, message_id=message.message_id)
    except Exception:
        pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Xatolik yuz berdi:", exc_info=context.error)


class _HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """Render (yoki shunga o'xshash platformalar) 'portni tinglayapsizmi'
    tekshiruvini qanoatlantirish uchun har qanday so'rovga 200 OK bilan
    javob beradi. Botning asosiy ishiga (Telegram bilan gaplashish) hech
    qanday aloqasi yo'q - faqat platforma buni talab qilgani uchun kerak."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Bot ishlamoqda ✅".encode("utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # standart HTTP loglarini o'chirib qo'yamiz (keraksiz shovqin)


def start_health_check_server():
    """PORT muhit o'zgaruvchisi berilgan bo'lsa (Render kabi platformalarda
    avtomatik beriladi), fon rejimida (alohida thread'da) mayda HTTP server
    ishga tushiradi. Agar PORT berilmagan bo'lsa (masalan kompyuterda sinab
    ko'rayotganda), umuman hech narsa qilmaydi."""
    port_raw = os.environ.get("PORT")
    if not port_raw:
        return
    try:
        port = int(port_raw)
    except ValueError:
        logger.warning("PORT muhit o'zgaruvchisi noto'g'ri qiymatga ega: %s", port_raw)
        return

    def _serve():
        try:
            server = http.server.HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
            logger.info("Health-check HTTP server %s portda ishga tushdi.", port)
            server.serve_forever()
        except Exception:
            logger.exception("Health-check HTTP serverni ishga tushirishda xatolik.")

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()


def _get_backup_chat_id():
    """
    Zaxira nusxa qayerga yuborilishi/qidirilishi kerakligini aniqlaydi.

    Avval BAZADA saqlangan qiymat tekshiriladi (`get_storage_chat_id()`),
    chunki bu ENG YANGI va TO'G'RI manba - masalan guruh supergroup'ga
    aylanib, ID o'zgarganda, bot buni avtomatik yangilab qo'yadi (pastdagi
    ChatMigrated ishlov beruvchisiga qarang). Bazada hech narsa topilmasa
    (masalan fayl tizimi tozalanganda) - kod/muhit o'zgaruvchisidagi
    STORAGE_CHAT_ID standart qiymatiga qaytadi (bu fayl tizimidan mustaqil,
    shuning uchun "boshlang'ich nuqta" sifatida ishlatiladi).
    """
    return get_storage_chat_id() or (ADMIN_IDS[0] if ADMIN_IDS else None)


def _count_posts_in_db() -> int:
    """Mahalliy bazadagi postlar sonini hisoblaydi (xavfsizlik tekshiruvi uchun)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM posts")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


async def backup_database(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """
    movies.db faylini (SQLite bazaning o'zini) hujjat sifatida saqlash
    guruhiga (yoki admin chatiga) yuklaydi va PIN qiladi. Bu Render kabi
    platformalarda (bepul rejada doimiy fayl xotirasi bo'lmagani uchun)
    bot qayta deploy qilinganda ma'lumotlar YO'QOLIB ketmasligi uchun
    zarur - bot ishga tushganda shu pin qilingan nusxadan tiklanadi.

    Guruh eski zaxira fayllari bilan TO'LIB KETMASLIGI uchun, yangi zaxira
    muvaffaqiyatli yuklab bo'lingandan KEYIN, undan OLDINGI (eski) zaxira
    xabari avtomatik o'chiriladi - shunda guruhda doim faqat BITTA (eng
    so'nggi) zaxira fayli saqlanadi.

    ⚠️ XAVFSIZLIK TEKSHIRUVI: agar mahalliy baza BO'SH (0 ta post) bo'lsa-yu,
    guruhda ALLAQACHON zaxira mavjud bo'lsa - bu zaxiralanmaydi va OLDINGI
    zaxira O'CHIRILMAYDI.

    Diagnostika uchun natija lug'atini qaytaradi: {"ok", "reason", "pinned",
    "posts_count", "chat_id"} - bu /admin dagi "Hozir zaxiralash" tugmasi
    orqali adminga to'liq holatni ko'rsatish uchun ishlatiladi.
    """
    backup_chat_id = _get_backup_chat_id()
    if not backup_chat_id:
        logger.warning("Bazani zaxiralash uchun chat topilmadi (baza guruhi ham, admin ham sozlanmagan).")
        return {"ok": False, "reason": "no_chat", "pinned": False, "posts_count": 0, "chat_id": None, "error": None}

    if not os.path.exists(DB_PATH):
        return {"ok": False, "reason": "no_file", "pinned": False, "posts_count": 0, "chat_id": backup_chat_id, "error": None}

    previous_backup_message_id = get_setting("last_backup_message_id")
    posts_count = _count_posts_in_db()

    if posts_count == 0 and previous_backup_message_id:
        logger.warning(
            "⚠️ Mahalliy baza BO'SH (0 ta post), lekin oldin zaxira mavjud - "
            "xavfsizlik uchun zaxiralash O'TKAZIB YUBORILDI (yaxshi zaxira saqlanib qoladi)."
        )
        return {
            "ok": False, "reason": "empty_skip", "pinned": False,
            "posts_count": posts_count, "chat_id": backup_chat_id, "error": None,
        }

    sent = None
    last_error = None
    attempts_left = 3  # 1-urinish + 2 qayta urinish (migratsiya + vaqtinchalik xatolar uchun yetarli)
    attempt = 0
    while attempt < attempts_left:
        try:
            with open(DB_PATH, "rb") as f:
                sent = await context.bot.send_document(
                    chat_id=backup_chat_id,
                    document=f,
                    filename="movies_backup.db",
                    caption="🗄 Avtomatik zaxira nusxa (backup) - bu xabarni O'CHIRMANG.",
                )
            break
        except ChatMigrated as e:
            # Guruh oddiy guruhdan SUPERGROUP'ga aylantirilgan - Telegram
            # yangi chat_id beradi. Buni AVTOMATIK saqlab qo'yamiz va
            # DARHOL yangi ID bilan qayta urinamiz - admin hech narsa
            # qilishiga hojat qolmaydi. Bu urinish oddiy qayta-urinish
            # byudjetini "yemaydi" - shuning uchun attempts_left'ni oshiramiz.
            logger.warning(
                "Guruh supergroup'ga aylantirilgan. Eski ID: %s -> Yangi ID: %s. "
                "Sozlama avtomatik yangilanmoqda.", backup_chat_id, e.new_chat_id,
            )
            backup_chat_id = e.new_chat_id
            set_setting("storage_chat_id", str(backup_chat_id))
            last_error = e
            if attempts_left < 5:  # xavfsizlik chegarasi - cheksiz oshib ketmasin
                attempts_left += 1  # bu urinish migratsiyani aniqlash uchun ketdi, hisobga olmaymiz
        except Exception as e:
            last_error = e
            await asyncio.sleep(2)
        attempt += 1

    if sent is None:
        logger.error("Bazani zaxiralashda (yuklashda) xatolik yuz berdi: %s", last_error, exc_info=last_error)
        return {
            "ok": False, "reason": "upload_failed", "pinned": False,
            "posts_count": posts_count, "chat_id": backup_chat_id,
            "error": str(last_error) if last_error else None,
        }

    pinned_ok = False
    try:
        await context.bot.pin_chat_message(
            chat_id=backup_chat_id, message_id=sent.message_id, disable_notification=True
        )
        pinned_ok = True
    except Exception:
        logger.warning(
            "Zaxira xabarini PIN qilib bo'lmadi - botda 'Pin messages' huquqi "
            "borligini tekshiring (aks holda tiklash ishlamaydi)."
        )

    # Yangi zaxira muvaffaqiyatli yuklandi - endi shu haqidagi ma'lumotni
    # saqlaymiz va, agar oldingi zaxira bo'lsa, uni guruhdan o'chiramiz.
    set_setting("last_backup_message_id", str(sent.message_id))

    if previous_backup_message_id:
        try:
            await context.bot.delete_message(
                chat_id=backup_chat_id, message_id=int(previous_backup_message_id)
            )
        except Exception:
            # Allaqachon o'chirilgan yoki topilmagan bo'lishi mumkin - muammo emas.
            pass

    return {
        "ok": True, "reason": "success", "pinned": pinned_ok,
        "posts_count": posts_count, "chat_id": backup_chat_id, "error": None,
    }


async def backup_database_job(context: ContextTypes.DEFAULT_TYPE):
    """
    `job_queue.run_repeating` orqali har 1 soatda chaqiriladigan wrapper.
    `backup_database`ni chaqiradi, va agar zaxira YUKLANGAN, lekin PIN
    qilinmagan bo'lsa (ya'ni tiklash ISHLAMAYDIGAN holatda qolsa) - adminga
    darhol ogohlantirish xabari yuboradi. Spam bo'lmasligi uchun, xabar
    faqat HOLAT O'ZGARGANDA (avval yaxshi edi, endi yomon bo'lib qoldi)
    yuboriladi, har safar emas.
    """
    result = await backup_database(context)

    pin_problem_now = result.get("ok") and not result.get("pinned")
    was_already_warned = get_setting("pin_problem_warned") == "1"

    if pin_problem_now and not was_already_warned:
        set_setting("pin_problem_warned", "1")
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "🚨 DIQQAT: Baza zaxirasi yuklandi, LEKIN PIN QILINMADI!\n\n"
                        "Bu degani - agar bot qayta ishga tushsa (masalan qayta "
                        "deploy qilinganda), u bu zaxirani TOPA OLMAYDI va "
                        "BO'SH bazadan boshlaydi - barcha postlar yo'qoladi!\n\n"
                        "Iltimos, tezda tuzating: guruh sozlamalari → "
                        "Administrators → botingiz → 'Pin Messages' huquqini yoqing."
                    ),
                )
            except Exception:
                logger.exception("Pin muammosi haqida adminga (%s) xabar yuborib bo'lmadi.", admin_id)
    elif not pin_problem_now and was_already_warned and result.get("ok"):
        # Muammo tuzatilgan - keyingi safar yana muammo chiqsa, qayta ogohlantirish kerak
        set_setting("pin_problem_warned", "0")


_BACKUP_REASON_LABELS = {
    "success": "Muvaffaqiyatli yuklandi",
    "no_chat": "Saqlash chati topilmadi (baza guruhi sozlanmagan)",
    "no_file": "Mahalliy baza fayli topilmadi",
    "empty_skip": "Baza bo'sh - xavfsizlik uchun o'tkazib yuborildi (eski zaxira saqlanib qoldi)",
    "upload_failed": "Yuklashda xatolik yuz berdi",
}


async def adm_backupnow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "🔄 Hozir zaxiralash / tekshirish" tugmasini bosganda - darhol
    zaxiralaydi va to'liq diagnostika natijasini ko'rsatadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    await query.edit_message_text("🔄 Zaxiralanmoqda, biroz kuting...")
    result = await backup_database(context)

    lines = ["🔄 Zaxiralash natijasi:\n"]
    lines.append(f"Holat: {'✅ Muvaffaqiyatli' if result['ok'] else '❌ Muvaffaqiyatsiz'}")
    lines.append(f"Sabab: {_BACKUP_REASON_LABELS.get(result['reason'], result['reason'])}")
    lines.append(f"Postlar soni (mahalliy bazada): {result['posts_count']}")
    lines.append(f"Saqlash chati ID: {result['chat_id']}")
    if result["ok"]:
        pin_text = "✅ Ha" if result["pinned"] else "❌ Yo'q (MUAMMO - tiklash ishlamaydi!)"
        lines.append(f"PIN qilindi: {pin_text}")
    elif result.get("error"):
        lines.append(f"\n⚠️ Texnik tafsilot:\n{result['error']}")

    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="adm:menu")], home_button_row()]
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard))


async def _restore_from_pinned_backup(bot) -> dict:
    """
    'Baza guruhi'da PIN qilingan eng so'nggi zaxira hujjatini qidirib,
    topilsa DB_PATH'ga yuklab qo'yadi. Natija lug'atini qaytaradi -
    bu ham avtomatik ishga tushish bosqichida (restore_database_if_needed),
    ham admin "♻️ Zaxiradan hozir tiklash" tugmasi bosilganda ishlatiladi.
    """
    backup_chat_id = _get_backup_chat_id()
    if not backup_chat_id:
        return {"ok": False, "reason": "no_chat", "posts_count": 0}

    try:
        chat = await bot.get_chat(backup_chat_id)
        pinned = chat.pinned_message
        if pinned is None or pinned.document is None:
            return {"ok": False, "reason": "no_pinned", "posts_count": 0}
        file = await bot.get_file(pinned.document.file_id)
        await file.download_to_drive(DB_PATH)
    except Exception:
        logger.exception("Bazani zaxiradan tiklashda xatolik.")
        return {"ok": False, "reason": "download_failed", "posts_count": 0}

    init_db()  # tiklangan fayl ustida jadvallarni yaratish/migratsiya qilish
    posts_count = _count_posts_in_db()
    logger.info("✅ Baza muvaffaqiyatli zaxiradan tiklandi (%s), postlar: %s.", DB_PATH, posts_count)
    return {"ok": True, "reason": "success", "posts_count": posts_count}


async def restore_database_if_needed(bot):
    """
    Bot ishga tushganda (post_init bosqichida) chaqiriladi. Agar mahalliy
    'movies.db' fayli mavjud bo'lmasa yoki bo'sh bo'lsa (yangi/tozalangan
    fayl tizimi belgisi), saqlash chatida PIN qilingan eng so'nggi zaxira
    nusxani qidirib, topilsa - yuklab olib, o'rniga qo'yadi.
    """
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
        return  # mahalliy baza allaqachon bor - tiklashga hojat yo'q
    await _restore_from_pinned_backup(bot)


async def adm_restorenow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "♻️ Zaxiradan hozir tiklash" tugmasini bosganda - PIN qilingan
    zaxiradan QO'LDA, darhol tiklashga urinadi (fayl bo'sh bo'lmasa ham)."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return

    await query.edit_message_text("♻️ Tiklanmoqda, biroz kuting...")
    result = await _restore_from_pinned_backup(context.bot)

    reason_labels = {
        "success": "Muvaffaqiyatli tiklandi",
        "no_chat": "Saqlash chati topilmadi (baza guruhi sozlanmagan)",
        "no_pinned": "PIN qilingan zaxira topilmadi",
        "download_failed": "Yuklab olishda xatolik yuz berdi",
    }
    text = (
        "♻️ Tiklash natijasi:\n\n"
        f"Holat: {'✅ Muvaffaqiyatli' if result['ok'] else '❌ Muvaffaqiyatsiz'}\n"
        f"Sabab: {reason_labels.get(result['reason'], result['reason'])}\n"
        f"Postlar soni (tiklangandan keyin): {result['posts_count']}"
    )
    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="adm:menu")], home_button_row()]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def dbupload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin "📥 DB faylni qo'lda yuklash" tugmasini bosganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "📥 Bazani qo'lda tiklash\n\n"
        "Iltimos, `.db` formatidagi SQLite faylni (masalan avval saqlab qo'ygan "
        "`movies.db` nusxasini, yoki guruhdagi zaxirani) shu yerga HUJJAT "
        "(fayl) sifatida yuboring.\n\n"
        "⚠️ DIQQAT: bu joriy bazani BUTUNLAY almashtiradi!\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_DB_UPLOAD


async def dbupload_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    message = update.message
    document = message.document

    if document is None:
        await message.reply_text(
            "❌ Bu hujjat (fayl) emasga o'xshaydi. `.db` faylni HUJJAT sifatida yuboring, "
            "yoki /cancel bilan bekor qiling."
        )
        return WAITING_DB_UPLOAD

    tmp_path = DB_PATH + ".import_tmp"
    try:
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(tmp_path)
    except Exception:
        logger.exception("Import uchun faylni yuklab olishda xatolik.")
        await message.reply_text(
            "❌ Faylni yuklab olishda xatolik yuz berdi. Qaytadan urinib ko'ring, "
            "yoki /cancel bilan bekor qiling."
        )
        return WAITING_DB_UPLOAD

    # Validatsiya: bu haqiqatan ham SQLite baza va bizning jadvalimizga egami?
    posts_count = 0
    try:
        test_conn = sqlite3.connect(tmp_path)
        test_cur = test_conn.cursor()
        test_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in test_cur.fetchall()}
        if "posts" in tables:
            test_cur.execute("SELECT COUNT(*) FROM posts")
            posts_count = test_cur.fetchone()[0]
        test_conn.close()
    except Exception:
        tables = set()

    if "posts" not in tables:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        await message.reply_text(
            "❌ Bu fayl to'g'ri SQLite baza emas, yoki bizning bot bazamizga "
            "o'xshamayapti ('posts' jadvali topilmadi).\n\n"
            "Boshqa faylni sinab ko'ring, yoki /cancel bilan bekor qiling."
        )
        return WAITING_DB_UPLOAD

    context.user_data["dbupload_tmp_path"] = tmp_path
    context.user_data["dbupload_posts_count"] = posts_count

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Ha, almashtirish", callback_data="adm:dbuploadconfirm")],
            [InlineKeyboardButton("❌ Yo'q, bekor qilish", callback_data="adm:dbuploadcancel")],
        ]
    )
    await message.reply_text(
        f"📦 Faylda {posts_count} ta post topildi.\n\n"
        "⚠️ Bu joriy bazani BUTUNLAY almashtiradi. Davom etasizmi?",
        reply_markup=keyboard,
    )
    return WAITING_DB_UPLOAD_CONFIRM


async def dbupload_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    tmp_path = context.user_data.pop("dbupload_tmp_path", None)
    posts_count = context.user_data.pop("dbupload_posts_count", 0)

    if not tmp_path or not os.path.exists(tmp_path):
        await query.edit_message_text("⚠️ Sessiya topilmadi yoki fayl yo'qolgan. /admin orqali qaytadan boshlang.")
        return ConversationHandler.END

    try:
        os.replace(tmp_path, DB_PATH)
    except Exception:
        logger.exception("Faylni almashtirishda xatolik.")
        await query.edit_message_text("❌ Faylni almashtirishda ichki xatolik yuz berdi.")
        return ConversationHandler.END

    init_db()  # yangi fayl ustida jadvallarni yaratish/migratsiya qilish

    await query.edit_message_text(
        f"✅ Baza muvaffaqiyatli almashtirildi!\nTopilgan postlar soni: {posts_count}\n\n"
        "Tavsiya: endi shu yangi bazani darhol zaxiralab qo'ying - "
        "/admin → 🔄 Hozir zaxiralash / tekshirish tugmasini bosing."
    )
    return ConversationHandler.END


async def dbupload_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tmp_path = context.user_data.pop("dbupload_tmp_path", None)
    context.user_data.pop("dbupload_posts_count", None)
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    await query.edit_message_text("Bekor qilindi.")
    return ConversationHandler.END


async def dbupload_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tmp_path = context.user_data.pop("dbupload_tmp_path", None)
    context.user_data.pop("dbupload_posts_count", None)
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


async def _post_init(app):
    """Bot pollingni boshlashdan OLDIN, bir marta ishga tushadigan bosqich."""
    await restore_database_if_needed(app.bot)
    init_db()  # tiklangan (yoki yangi) fayl ustida jadvallarni yaratish/migratsiya qilish


def main():
    start_health_check_server()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).build()

    add_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            CommandHandler("add_game", add_start),
            CallbackQueryHandler(add_start, pattern=r"^adm:add$"),
            CallbackQueryHandler(add_start, pattern=r"^adm:add_game$"),
        ],
        states={
            WAITING_POST: [
                MessageHandler(filters.ALL & ~filters.COMMAND, add_receive_post),
            ],
            WAITING_CODES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_codes),
            ],
            WAITING_BUTTON_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_button_name),
            ],
            WAITING_EXTRA_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_extra_link),
            ],
            WAITING_EXTRA_LINK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_extra_link_name),
            ],
            WAITING_VISIBILITY: [
                CallbackQueryHandler(add_receive_visibility, pattern=r"^addvis:(all|vip|admin)$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", add_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    edit_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_field_start, pattern=r"^adm:editcodes:\d+$"),
            CallbackQueryHandler(edit_field_start, pattern=r"^adm:editname:\d+$"),
            CallbackQueryHandler(edit_field_start, pattern=r"^adm:editlink:\d+$"),
        ],
        states={
            WAITING_EDIT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_value),
            ],
            WAITING_EDIT_LINK_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_link_url),
            ],
            WAITING_EDIT_LINK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_link_name),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", edit_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    broadcast_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(broadcast_start, pattern=r"^adm:broadcast$"),
            CallbackQueryHandler(adsexcl_new_start, pattern=r"^adm:adsexclnew$"),
            CallbackQueryHandler(adsalways_new_start, pattern=r"^adm:adsalwaysnew$"),
        ],
        states={
            WAITING_BROADCAST_AUDIENCE: [
                CallbackQueryHandler(broadcast_choose_audience, pattern=r"^adm:bcast:(regular|vip|all)$"),
                CallbackQueryHandler(adm_adsexcl_list_callback, pattern=r"^adm:adsexcl$"),
                CallbackQueryHandler(adm_adsalways_list_callback, pattern=r"^adm:adsalways$"),
            ],
            WAITING_BROADCAST_POST: [
                MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_receive_post),
            ],
            WAITING_BROADCAST_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive_link),
            ],
            WAITING_BROADCAST_LINK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive_link_name),
            ],
            WAITING_BROADCAST_CONFIRM: [
                CallbackQueryHandler(broadcast_confirm_callback, pattern=r"^adm:bcastconfirm$"),
                CallbackQueryHandler(broadcast_confirm_cancel_callback, pattern=r"^adm:bcastcancel$"),
            ],
            WAITING_ADSEXCL_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, adsexcl_new_receive),
            ],
            WAITING_ADSALWAYS_ITEM: [
                MessageHandler(filters.ALL & ~filters.COMMAND, adsalways_new_receive),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", broadcast_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    vip_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(vip_start, pattern=r"^adm:vipnew$"),
            CallbackQueryHandler(vipadjust_start, pattern=r"^adm:vipextend:\d+$"),
            CallbackQueryHandler(vipadjust_start, pattern=r"^adm:vipreduce:\d+$"),
        ],
        states={
            WAITING_VIP_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, vip_receive_user),
                CallbackQueryHandler(vip_back_to_list, pattern=r"^adm:vipback$"),
            ],
            WAITING_VIP_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, vip_receive_days),
                CallbackQueryHandler(vip_back_to_list, pattern=r"^adm:vipback$"),
            ],
            WAITING_VIP_ADJUST_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, vipadjust_receive_days),
                CallbackQueryHandler(vipadjust_back_to_user, pattern=r"^adm:vipuser:\d+$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", vip_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    db_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(db_start, pattern=r"^adm:setdb$"),
        ],
        states={
            WAITING_DB_GROUP: [
                MessageHandler(filters.ALL & ~filters.COMMAND, db_receive),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", db_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    vipchannel_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(vipchannel_start, pattern=r"^adm:setvipchannel$"),
        ],
        states={
            WAITING_VIP_CHANNEL: [
                MessageHandler(filters.ALL & ~filters.COMMAND, vipchannel_receive),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", vipchannel_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    autoaccept_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(autoaccept_start, pattern=r"^adm:setautoaccept$"),
        ],
        states={
            WAITING_AUTOACCEPT_CHANNEL: [
                MessageHandler(filters.ALL & ~filters.COMMAND, autoaccept_receive),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", autoaccept_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    vipspecial_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(vipspecial_start, pattern=r"^adm:setvip1$"),
            CallbackQueryHandler(vipspecial_start, pattern=r"^adm:setvip2$"),
        ],
        states={
            WAITING_VIP_SPECIAL_POST: [
                MessageHandler(filters.ALL & ~filters.COMMAND, vipspecial_receive),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", vipspecial_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    dbupload_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(dbupload_start, pattern=r"^adm:dbupload$"),
        ],
        states={
            WAITING_DB_UPLOAD: [
                MessageHandler(filters.Document.ALL & ~filters.COMMAND, dbupload_receive),
            ],
            WAITING_DB_UPLOAD_CONFIRM: [
                CallbackQueryHandler(dbupload_confirm_callback, pattern=r"^adm:dbuploadconfirm$"),
                CallbackQueryHandler(dbupload_cancel_callback, pattern=r"^adm:dbuploadcancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", dbupload_cancel),
            CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"),
        ],
    )

    app.add_handler(add_conversation)
    app.add_handler(edit_conversation)
    app.add_handler(broadcast_conversation)
    app.add_handler(vip_conversation)
    app.add_handler(db_conversation)
    app.add_handler(vipchannel_conversation)
    app.add_handler(autoaccept_conversation)
    app.add_handler(vipspecial_conversation)
    app.add_handler(dbupload_conversation)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_movies))
    app.add_handler(CommandHandler("games", list_games))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("chatid", chatid_command))

    app.add_handler(CallbackQueryHandler(handle_list_button, pattern=r"^code:"))
    app.add_handler(CallbackQueryHandler(handle_list_page_callback, pattern=r"^listpage:"))
    app.add_handler(CallbackQueryHandler(handle_list_close_callback, pattern=r"^listclose$"))
    app.add_handler(CallbackQueryHandler(adm_menu_callback, pattern=r"^adm:menu$"))
    app.add_handler(CallbackQueryHandler(adm_backupnow_callback, pattern=r"^adm:backupnow$"))
    app.add_handler(CallbackQueryHandler(adm_restorenow_callback, pattern=r"^adm:restorenow$"))
    app.add_handler(CallbackQueryHandler(adm_backhome_callback, pattern=r"^adm:backhome$"))
    app.add_handler(CallbackQueryHandler(adm_stats_callback, pattern=r"^adm:stats$"))
    app.add_handler(CallbackQueryHandler(adm_users_callback, pattern=r"^adm:users$"))
    app.add_handler(CallbackQueryHandler(adm_vip_menu_callback, pattern=r"^adm:vip$"))
    app.add_handler(CallbackQueryHandler(adm_vipuser_detail_callback, pattern=r"^adm:vipuser:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_vipcancel_confirm_callback, pattern=r"^adm:vipcanceling:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_vipcancel_do_callback, pattern=r"^adm:vipcanceldo:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_users_page_callback, pattern=r"^adm:userspage:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_adsexcl_list_callback, pattern=r"^adm:adsexcl$"))
    app.add_handler(CallbackQueryHandler(adm_adsexcl_user_detail_callback, pattern=r"^adm:adsexcluser:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_adsexcl_remove_callback, pattern=r"^adm:adsexclremove:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_adsalways_list_callback, pattern=r"^adm:adsalways$"))
    app.add_handler(CallbackQueryHandler(adm_adsalways_item_detail_callback, pattern=r"^adm:adsalwaysitem:-?\d+$"))
    app.add_handler(CallbackQueryHandler(adm_adsalways_remove_callback, pattern=r"^adm:adsalwaysremove:-?\d+$"))
    app.add_handler(CallbackQueryHandler(adm_editlist_callback, pattern=r"^adm:editlist$"))
    app.add_handler(CallbackQueryHandler(adm_postdetail_callback, pattern=r"^adm:editpost:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_editvis_menu, pattern=r"^adm:editvis:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_setvis_callback, pattern=r"^adm:setvis:(all|vip|admin):\d+$"))
    app.add_handler(CallbackQueryHandler(adm_delpost_confirm_callback, pattern=r"^adm:delpost:\d+$"))
    app.add_handler(CallbackQueryHandler(adm_delpost_do_callback, pattern=r"^adm:delconfirm:\d+$"))

    # VIP kanalga qo'shilish so'rovlarini avtomatik boshqarish
    app.add_handler(ChatJoinRequestHandler(handle_chat_join_request))

    app.add_handler(MessageHandler(filters.StatusUpdate.PINNED_MESSAGE, handle_pinned_service_message))
    app.add_error_handler(error_handler)

    # Foydalanuvchi matn (kod) yuborsa
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # VIP muddati tugagan foydalanuvchilarni kanaldan avtomatik chiqarish -
    # har soatda bir marta tekshiradi (birinchi tekshiruv 30 soniyadan keyin)
    if app.job_queue is not None:
        app.job_queue.run_repeating(vip_expiry_job, interval=3600, first=30)
        # Bazani har 1 soatda avtomatik zaxiralab turadi (Render kabi
        # platformalarda doimiy fayl xotirasi bo'lmagani uchun ZARUR -
        # aks holda qayta deploy qilinganda barcha ma'lumot yo'qolib ketadi).
        app.job_queue.run_repeating(backup_database_job, interval=3600, first=60)
    else:
        logger.warning(
            "job_queue mavjud emas - VIP muddati tugaganda avtomatik kanaldan "
            "chiqarish VA bazani avtomatik zaxiralash ISHLAMAYDI. "
            "`pip install \"python-telegram-bot[job-queue]\"` bilan o'rnatishni tekshiring."
        )

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
