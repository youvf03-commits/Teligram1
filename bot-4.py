import os
import re
import json
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.constants import ChatMemberStatus, MessageEntityType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN") or "8379437159:AAG_bUEIBCpAmjZSIN76YmB8Ytfuye8JDdo"
DATA_FILE = "blocked.json"
WARN_LIMIT = 3  # এতগুলো ওয়ার্নের পর অটো ব্যান

LINK_REGEX = re.compile(
    r"(https?://|ftp://|www\.|t\.me|telegram\.me|telegram\.dog|"
    r"\b[a-z0-9\u0980-\u09FF-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(/\S*)?)",
    re.IGNORECASE,
)


# ---------- ডাটা ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = {}
    # পুরনো ফরম্যাট (লিস্ট) থাকলে নতুন ফরম্যাটে মাইগ্রেট করা
    fixed = {}
    for cid, val in raw.items():
        if isinstance(val, list):
            fixed[cid] = {"words": val, "filters": {}, "warns": {}}
        elif isinstance(val, dict):
            val.setdefault("words", [])
            val.setdefault("filters", {})
            val.setdefault("warns", {})
            fixed[cid] = val
    return fixed


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


DATA = load_data()


def chat_data(cid: str) -> dict:
    return DATA.setdefault(cid, {"words": [], "filters": {}, "warns": {}})


# ---------- হেল্পার ----------
async def is_admin(update: Update, user_id: int) -> bool:
    try:
        m = await update.effective_chat.get_member(user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def admin_only(update: Update) -> bool:
    if not await is_admin(update, update.effective_user.id):
        await update.message.reply_text("❌ শুধু অ্যাডমিন এই কমান্ড ব্যবহার করতে পারবে।")
        return False
    return True


async def get_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """রিপ্লাই করা ইউজার অথবা /cmd USER_ID"""
    msg = update.message
    if msg.reply_to_message:
        return msg.reply_to_message.from_user
    if context.args and context.args[0].lstrip("-").isdigit():
        try:
            m = await update.effective_chat.get_member(int(context.args[0]))
            return m.user
        except Exception:
            return None
    await msg.reply_text("ℹ️ কারো মেসেজে রিপ্লাই করে কমান্ড দিন।")
    return None


def parse_duration(text: str):
    m = re.fullmatch(r"(\d+)([mhd])", text.lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[unit]


def name_of(user):
    return user.mention_html()


# ---------- অ্যাডমিন কমান্ড ----------
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    user = await get_target(update, context)
    if not user:
        return
    if await is_admin(update, user.id):
        await update.message.reply_text("❌ অ্যাডমিনকে ব্যান করা যাবে না।")
        return
    try:
        await update.effective_chat.ban_member(user.id)
        await update.message.reply_html(f"🚫 {name_of(user)} কে ব্যান করা হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ব্যর্থ: {e}")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    user = await get_target(update, context)
    if not user:
        return
    try:
        await update.effective_chat.unban_member(user.id, only_if_banned=True)
        await update.message.reply_html(f"✅ {name_of(user)} কে আনব্যান করা হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ব্যর্থ: {e}")


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    user = await get_target(update, context)
    if not user:
        return
    if await is_admin(update, user.id):
        await update.message.reply_text("❌ অ্যাডমিনকে কিক করা যাবে না।")
        return
    try:
        await update.effective_chat.ban_member(user.id)
        await update.effective_chat.unban_member(user.id)
        await update.message.reply_html(f"👢 {name_of(user)} কে কিক করা হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ব্যর্থ: {e}")


async def tban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/tban 1h (রিপ্লাই করে)  — m=মিনিট, h=ঘণ্টা, d=দিন"""
    if not await admin_only(update):
        return
    if not update.message.reply_to_message or not context.args:
        await update.message.reply_text("ℹ️ রিপ্লাই করে লিখুন: /tban 1h")
        return
    delta = parse_duration(context.args[0])
    if not delta:
        await update.message.reply_text("ℹ️ সময় দিন এভাবে: 30m, 2h, 1d")
        return
    user = update.message.reply_to_message.from_user
    if await is_admin(update, user.id):
        await update.message.reply_text("❌ অ্যাডমিনকে ব্যান করা যাবে না।")
        return
    try:
        until = datetime.now(timezone.utc) + delta
        await update.effective_chat.ban_member(user.id, until_date=until)
        await update.message.reply_html(
            f"⏳ {name_of(user)} কে {context.args[0]} এর জন্য ব্যান করা হয়েছে।"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ ব্যর্থ: {e}")


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mute  অথবা  /mute 1h (রিপ্লাই করে)"""
    if not await admin_only(update):
        return
    user = await get_target(update, context)
    if not user:
        return
    if await is_admin(update, user.id):
        await update.message.reply_text("❌ অ্যাডমিনকে মিউট করা যাবে না।")
        return
    until = None
    label = "সবসময়ের জন্য"
    if update.message.reply_to_message and context.args:
        delta = parse_duration(context.args[0])
        if delta:
            until = datetime.now(timezone.utc) + delta
            label = context.args[0]
    try:
        await update.effective_chat.restrict_member(
            user.id,
            ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        await update.message.reply_html(f"🔇 {name_of(user)} কে মিউট করা হয়েছে ({label})।")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ব্যর্থ: {e}")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    user = await get_target(update, context)
    if not user:
        return
    try:
        await update.effective_chat.restrict_member(
            user.id, ChatPermissions.all_permissions()
        )
        await update.message.reply_html(f"🔊 {name_of(user)} কে আনমিউট করা হয়েছে।")
    except Exception as e:
        await update.message.reply_text(f"⚠️ ব্যর্থ: {e}")


# ---------- ব্লক টেক্সট ----------
async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/block শব্দ"""
    if not await admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("ℹ️ লিখুন: /block শব্দ")
        return
    word = " ".join(context.args).lower()
    cid = str(update.effective_chat.id)
    words = chat_data(cid)["words"]
    if word not in words:
        words.append(word)
        save_data(DATA)
    await update.message.reply_text(f"✅ ব্লক করা হয়েছে: {word}")


async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("ℹ️ লিখুন: /unblock শব্দ")
        return
    word = " ".join(context.args).lower()
    cid = str(update.effective_chat.id)
    words = chat_data(cid)["words"]
    if word in words:
        words.remove(word)
        save_data(DATA)
        await update.message.reply_text(f"✅ আনব্লক করা হয়েছে: {word}")
    else:
        await update.message.reply_text("ℹ️ এই শব্দ লিস্টে নেই।")


async def blocklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    words = chat_data(str(update.effective_chat.id))["words"]
    if not words:
        await update.message.reply_text("ℹ️ কোনো ব্লক করা শব্দ নেই।")
    else:
        await update.message.reply_text("🚫 ব্লক লিস্ট:\n" + "\n".join(f"• {w}" for w in words))


# ---------- ফিল্টার (কিওয়ার্ড → অটো রিপ্লাই) ----------
async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/filter কিওয়ার্ড উত্তর"""
    if not await admin_only(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("ℹ️ লিখুন: /filter কিওয়ার্ড উত্তর_লেখা")
        return
    keyword = context.args[0].lower()
    reply_text = " ".join(context.args[1:])
    cid = str(update.effective_chat.id)
    chat_data(cid)["filters"][keyword] = reply_text
    save_data(DATA)
    await update.message.reply_text(f"✅ ফিল্টার যোগ হয়েছে: {keyword}")


async def stop_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stopfilter কিওয়ার্ড"""
    if not await admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("ℹ️ লিখুন: /stopfilter কিওয়ার্ড")
        return
    keyword = context.args[0].lower()
    cid = str(update.effective_chat.id)
    fdict = chat_data(cid)["filters"]
    if keyword in fdict:
        del fdict[keyword]
        save_data(DATA)
        await update.message.reply_text(f"✅ ফিল্টার মুছে ফেলা হয়েছে: {keyword}")
    else:
        await update.message.reply_text("ℹ️ এই ফিল্টার নেই।")


async def list_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    fdict = chat_data(str(update.effective_chat.id))["filters"]
    if not fdict:
        await update.message.reply_text("ℹ️ কোনো ফিল্টার নেই।")
    else:
        await update.message.reply_text(
            "🗂️ ফিল্টার লিস্ট:\n" + "\n".join(f"• {k}" for k in fdict)
        )


# ---------- ওয়ার্ন সিস্টেম ----------
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    user = await get_target(update, context)
    if not user:
        return
    if await is_admin(update, user.id):
        await update.message.reply_text("❌ অ্যাডমিনকে ওয়ার্ন দেওয়া যাবে না।")
        return
    cid = str(update.effective_chat.id)
    warns = chat_data(cid)["warns"]
    uid = str(user.id)
    warns[uid] = warns.get(uid, 0) + 1
    count = warns[uid]

    if count >= WARN_LIMIT:
        warns[uid] = 0
        save_data(DATA)
        try:
            await update.effective_chat.ban_member(user.id)
            await update.message.reply_html(
                f"🚫 {name_of(user)} {WARN_LIMIT} বার ওয়ার্ন পাওয়ায় ব্যান করা হয়েছে।"
            )
        except Exception as e:
            await update.message.reply_text(f"⚠️ ব্যান করতে ব্যর্থ: {e}")
        return

    save_data(DATA)
    await update.message.reply_html(
        f"⚠️ {name_of(user)} কে ওয়ার্ন দেওয়া হয়েছে। ({count}/{WARN_LIMIT})"
    )


async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    user = await get_target(update, context)
    if not user:
        return
    cid = str(update.effective_chat.id)
    warns = chat_data(cid)["warns"]
    uid = str(user.id)
    if warns.get(uid, 0) > 0:
        warns[uid] -= 1
        save_data(DATA)
    await update.message.reply_html(
        f"✅ {name_of(user)} এর ওয়ার্ন কমানো হয়েছে। ({warns.get(uid, 0)}/{WARN_LIMIT})"
    )


async def reset_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return
    user = await get_target(update, context)
    if not user:
        return
    cid = str(update.effective_chat.id)
    chat_data(cid)["warns"][str(user.id)] = 0
    save_data(DATA)
    await update.message.reply_html(f"✅ {name_of(user)} এর ওয়ার্ন রিসেট করা হয়েছে।")


async def warns_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message:
        user = msg.reply_to_message.from_user
    else:
        user = update.effective_user
    cid = str(update.effective_chat.id)
    count = chat_data(cid)["warns"].get(str(user.id), 0)
    await update.message.reply_html(f"⚠️ {name_of(user)} এর ওয়ার্ন: {count}/{WARN_LIMIT}")


# ---------- ওয়েলকাম মেসেজ ----------
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.new_chat_members:
        return
    for user in msg.new_chat_members:
        if user.is_bot and user.id == context.bot.id:
            continue  # বট নিজে জয়েন করলে ওয়েলকাম না
        text = (
            f"🎉 স্বাগতম {name_of(user)}!\n"
            f"<b>{update.effective_chat.title}</b> গ্রুপে আপনাকে স্বাগত জানাই।\n"
            "গ্রুপের নিয়ম মেনে চলুন, লিংক দেওয়া নিষেধ 🙏"
        )
        await context.bot.send_message(
            update.effective_chat.id, text, parse_mode="HTML"
        )


# ---------- অটো মডারেশন (লিংক + ব্লক শব্দ + ফিল্টার) ----------
def has_link(msg) -> bool:
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    for e in entities:
        if e.type in (MessageEntityType.URL, MessageEntityType.TEXT_LINK):
            return True
    if msg.reply_markup and getattr(msg.reply_markup, "inline_keyboard", None):
        return True
    text = msg.text or msg.caption or ""
    return bool(LINK_REGEX.search(text))


async def delete_later(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.job.data.delete()
    except Exception:
        pass


async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message  # এডিট করা মেসেজও ধরবে
    if not msg or not msg.from_user:
        return
    if msg.from_user.id == 1087968824:  # anonymous admin
        return

    cid = str(update.effective_chat.id)
    text = (msg.text or msg.caption or "")
    lower = text.lower()

    is_admin_user = await is_admin(update, msg.from_user.id)

    if not is_admin_user:
        reason = None
        if has_link(msg):
            reason = "🔗 লিংক দেওয়া নিষেধ!"
        else:
            for w in chat_data(cid)["words"]:
                if w in lower:
                    reason = "🚫 নিষিদ্ধ শব্দ ব্যবহার করা যাবে না!"
                    break

        if reason:
            try:
                await msg.delete()
            except Exception as e:
                logging.warning(f"delete failed: {e}")
                await context.bot.send_message(
                    update.effective_chat.id,
                    "⚠️ মেসেজ ডিলিট করতে পারছি না। আমাকে অ্যাডমিন বানান এবং "
                    "'Delete messages' পারমিশন দিন।",
                )
                return

            warn_msg = await context.bot.send_message(
                update.effective_chat.id,
                f"{msg.from_user.mention_html()}, {reason}",
                parse_mode="HTML",
            )
            if context.job_queue:
                context.job_queue.run_once(delete_later, 8, data=warn_msg)
            return

    # ---- ফিল্টার (অ্যাডমিন সহ সবার মেসেজে কাজ করবে) ----
    fdict = chat_data(cid)["filters"]
    if fdict and text:
        words_in_text = re.findall(r"[\w\u0980-\u09FF]+", lower)
        for keyword, reply_text in fdict.items():
            if keyword in words_in_text or keyword in lower:
                await msg.reply_text(reply_text)
                break


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 হ্যালো! আমি Panel SOCIETY গ্রুপের মডারেটর।\n"
        "আমাকে তৈরি করেছেন —͞𝘼ʀᴀꜰᴀᴛ Bʜᴀɪ࿐\n\n"
        "সব কমান্ড দেখতে /help লিখুন।"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>সব কমান্ড</b> (রিপ্লাই করে, শুধু অ্যাডমিন)\n\n"
        "👤 <b>ইউজার ম্যানেজমেন্ট</b>\n"
        "/ban — ব্যান\n"
        "/unban — আনব্যান\n"
        "/kick — কিক (আবার জয়েন করতে পারবে)\n"
        "/tban 1h — নির্দিষ্ট সময়ের ব্যান (m/h/d)\n"
        "/mute বা /mute 1h — মিউট\n"
        "/unmute — আনমিউট\n\n"
        "🚫 <b>ব্লক শব্দ</b>\n"
        "/block শব্দ — শব্দ ব্লক (লিখলেই অটো ডিলিট)\n"
        "/unblock শব্দ — ব্লক তোলা\n"
        "/blocklist — লিস্ট দেখা\n\n"
        "🗂️ <b>ফিল্টার (অটো রিপ্লাই)</b>\n"
        "/filter কিওয়ার্ড উত্তর — ফিল্টার যোগ\n"
        "/stopfilter কিওয়ার্ড — ফিল্টার মোছা\n"
        "/filters — ফিল্টার লিস্ট\n\n"
        "⚠️ <b>ওয়ার্ন সিস্টেম</b>\n"
        f"/warn — ওয়ার্ন দেওয়া ({WARN_LIMIT} বার হলে অটো ব্যান)\n"
        "/unwarn — ১টা ওয়ার্ন কমানো\n"
        "/resetwarn — ওয়ার্ন রিসেট\n"
        "/warns — ওয়ার্ন সংখ্যা দেখা\n\n"
        "🔗 লিংক দিলে (সাধারণ মেম্বার) অটো ডিলিট হবে।\n"
        "🎉 নতুন মেম্বার জয়েন করলে ওয়েলকাম মেসেজ যাবে।"
    )
    await update.message.reply_text(text, parse_mode="HTML")


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("tban", tban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))
    app.add_handler(CommandHandler("blocklist", blocklist))
    app.add_handler(CommandHandler("filter", add_filter))
    app.add_handler(CommandHandler("stopfilter", stop_filter))
    app.add_handler(CommandHandler("filters", list_filters))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("resetwarn", reset_warn))
    app.add_handler(CommandHandler("warns", warns_count))

    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome)
    )
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, moderate)
    )

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
