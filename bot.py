import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient

# ========= CONFIG =========
TOKEN = "8486338907:AAGCsp9M2E8KHW1JADGNBTZz39p7rUNRvOM"
PASSWORD = "1234"
MONGO_URL = "mongodb+srv://dbshiv:dbusershiv05@cluster0.3joqe13.mongodb.net/ultra_bot?retryWrites=true&w=majority"

# ========= DB =========
client = MongoClient(MONGO_URL)
db = client["ultra_bot"]

groups_col = db["groups"]
messages_col = db["messages"]
settings_col = db["settings"]

# ========= MEMORY =========
authorized_users = set()
worker_running = False

# ========= LOGIN =========
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == PASSWORD:
        authorized_users.add(update.effective_user.id)
        await update.message.reply_text("✅ Login successful")
    else:
        await update.message.reply_text("❌ Wrong password")

# ========= ADD GROUP =========
async def addgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ["group", "supergroup"]:
        return await update.message.reply_text("❌ Use in group")
    groups_col.update_one(
        {"chat_id": chat.id},
        {"$set": {"chat_id": chat.id, "title": chat.title}},
        upsert=True
    )
    await update.message.reply_text(f"✅ Group added: {chat.title}")

# ========= REMOVE GROUP =========
async def removegroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    groups_col.delete_one({"chat_id": chat.id})
    await update.message.reply_text("❌ Group removed")

# ========= SHOW GROUPS =========
async def groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = list(groups_col.find())
    if not data:
        return await update.message.reply_text("❌ No groups added")
    text = "📌 Groups List:\n\n"
    for g in data:
        text += f"• {g.get('title','Unknown')} ({g['chat_id']})\n"
    await update.message.reply_text(text)

# ========= SAVE MESSAGE =========
async def save_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in authorized_users:
        return
    if update.message:
        messages_col.insert_one({
            "chat_id": update.message.chat_id,
            "message_id": update.message.message_id,
            "time": datetime.utcnow(),
            "seq": datetime.utcnow().timestamp()
        })

# ========= START POSTING =========
async def start_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in authorized_users:
        return await update.message.reply_text("❌ Login first")
    settings_col.update_one(
        {"_id": "status"},
        {"$set": {"posting": True, "last_sent": datetime.utcnow()}},
        upsert=True
    )
    await update.message.reply_text("🚀 Auto posting started")

# ========= STOP POSTING =========
async def stop_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings_col.update_one(
        {"_id": "status"},
        {"$set": {"posting": False}},
        upsert=True
    )
    await update.message.reply_text("⛔ Posting stopped")

# ========= BROADCAST =========
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in authorized_users:
        return await update.message.reply_text("❌ Login first")
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Reply to message")
    msg = update.message.reply_to_message
    groups = list(groups_col.find())
    for g in groups:
        try:
            await context.bot.copy_message(
                chat_id=g["chat_id"],
                from_chat_id=msg.chat_id,
                message_id=msg.message_id
            )
        except:
            pass
    await update.message.reply_text("✅ Broadcast sent")

# ========= SEND NOW =========
async def send_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in authorized_users:
        return await update.message.reply_text("❌ Login first")
    msgs = list(messages_col.find().sort("seq", 1).limit(10))
    if not msgs:
        return await update.message.reply_text("❌ Queue empty")
    groups = list(groups_col.find())
    sent_count = 0
    for msg in msgs:
        for g in groups:
            try:
                await context.bot.copy_message(
                    chat_id=g["chat_id"],
                    from_chat_id=msg["chat_id"],
                    message_id=msg["message_id"]
                )
            except:
                pass
        messages_col.delete_one({"_id": msg["_id"]})  # ✅ Delete after sending
        sent_count += 1
    await update.message.reply_text(f"✅ Sent {sent_count} messages immediately")

# ========= CLEAR QUEUE =========
async def clear_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messages_col.delete_many({})
    await update.message.reply_text("🗑️ Queue cleared")

# ========= STATUS =========
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting = settings_col.find_one({"_id": "status"})
    posting = setting.get("posting", False) if setting else False
    last_sent = setting.get("last_sent") if setting else None
    interval_sec = setting.get("interval_sec", 3600) if setting else 3600
    next_time = "N/A"
    if last_sent:
        elapsed = datetime.utcnow() - last_sent
        remaining_sec = max(interval_sec - elapsed.total_seconds(), 0)
        next_time = str(timedelta(seconds=int(remaining_sec)))
    queue_count = messages_col.count_documents({})
    await update.message.reply_text(
        f"📊 *Status*\n"
        f"Posting: {'🟢 ON' if posting else '🔴 OFF'}\n"
        f"Queue remaining: {queue_count}\n"
        f"Next content in: {next_time}",
        parse_mode="Markdown"
    )

# ========= SET INTERVAL =========
async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("❌ Usage: /setinterval <minutes>")
    minutes = int(context.args[0])
    settings_col.update_one(
        {"_id": "status"},
        {"$set": {"interval_sec": minutes * 60}},
        upsert=True
    )
    await update.message.reply_text(f"⏱ Interval set to {minutes} minutes")

# ========= HELP =========
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 *Available Commands:*\n\n"
        "/login <password> - Login to bot\n"
        "/addgroup - Add current group\n"
        "/removegroup - Remove current group\n"
        "/groups - List all groups\n"
        "/start_posting - Start auto posting\n"
        "/stop_posting - Stop auto posting\n"
        "/broadcast - Reply to a message to broadcast\n"
        "/sendnow - Send queued messages immediately\n"
        "/clear - Clear message queue\n"
        "/status - Show posting status, remaining messages & next content time\n"
        "/setinterval <minutes> - Set interval for auto posting\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ========= WORKER =========
async def worker(app):
    global worker_running
    if worker_running:
        return
    worker_running = True
    await asyncio.sleep(5)
    while True:
        setting = settings_col.find_one({"_id": "status"})
        if setting and setting.get("posting"):
            interval_sec = setting.get("interval_sec", 3600)
            last_sent = setting.get("last_sent", datetime.utcnow() - timedelta(seconds=interval_sec))
            elapsed = (datetime.utcnow() - last_sent).total_seconds()
            if elapsed >= interval_sec:
                msgs = list(messages_col.find().sort("seq", 1).limit(10))
                groups = list(groups_col.find())
                for msg in msgs:
                    for g in groups:
                        try:
                            await app.bot.copy_message(
                                chat_id=g["chat_id"],
                                from_chat_id=msg["chat_id"],
                                message_id=msg["message_id"]
                            )
                        except:
                            pass
                    messages_col.delete_one({"_id": msg["_id"]})  # ✅ Delete after sending
                settings_col.update_one({"_id": "status"}, {"$set": {"last_sent": datetime.utcnow()}})
        await asyncio.sleep(30)

# ========= MAIN =========
async def main():
    print("🔥 BOT STARTING 🔥")
    app = ApplicationBuilder().token(TOKEN).build()
    # --- COMMANDS ---
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("addgroup", addgroup))
    app.add_handler(CommandHandler("removegroup", removegroup))
    app.add_handler(CommandHandler("groups", groups))
    app.add_handler(CommandHandler("start_posting", start_posting))
    app.add_handler(CommandHandler("stop_posting", stop_posting))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("sendnow", send_now))
    app.add_handler(CommandHandler("clear", clear_queue))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("setinterval", set_interval))
    app.add_handler(CommandHandler("help", help_command))
    # --- MESSAGES ---
    app.add_handler(MessageHandler(filters.ALL, save_msg))
    # --- START ---
    await app.initialize()
    await app.start()
    asyncio.create_task(worker(app))
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
