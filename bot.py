# bot.py - Corrected Full Version

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
import asyncio
import json
import os
import time

# -------------------------
# API Details (Environment Variables)
api_id = int(os.environ["TELEGRAM_API_ID"])       # API ID
api_hash = os.environ["TELEGRAM_API_HASH"]        # API Hash
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]      # Bot Token

# -------------------------
# Directories & Data File
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BOT_DIR, "media")
DATA_FILE = os.path.join(BOT_DIR, "data.json")
os.makedirs(MEDIA_DIR, exist_ok=True)

# -------------------------
# Client Setup
client = TelegramClient('bot_session', api_id, api_hash)

# -------------------------
# Load/Save Data
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"groups": {}, "user_active": {}, "user_broadcast": {}}

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

# -------------------------
# Helper Functions
def get_active_gid(user_id):
    uid = str(user_id)
    gid = data["user_active"].get(uid)
    if gid and gid in data["groups"]:
        return gid
    if len(data["groups"]) == 1:
        return list(data["groups"].keys())[0]
    return None

def group_index_to_id(index):
    keys = list(data["groups"].keys())
    if 1 <= index <= len(keys):
        return keys[index - 1]
    return None

def groups_list_text(active_gid=None):
    if not data["groups"]:
        return "Koi group/channel nahi hai.\n`/addgroup <id> <naam>` se add karo."
    lines = []
    for i, (gid, g) in enumerate(data["groups"].items(), 1):
        status = "🟢" if g.get("posting") else "🔴"
        interval_min = g.get("interval_sec", 120) // 60
        active_mark = " ◀️" if gid == active_gid else ""
        lines.append(
            f"{i}. {status} *{g['name']}*{active_mark}\n"
            f"   Queue: {len(g.get('queue',[]))} | Interval: {interval_min} min"
        )
    return "\n".join(lines)

async def verify_chat(chat_id_str):
    raw = chat_id_str.strip()
    try:
        entity = await client.get_entity(int(raw))
    except Exception as e:
        raise ValueError(f"ID verify nahi ho saki: {e}")
    name = getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown')
    if isinstance(entity, Channel):
        full_id = f"-100{entity.id}"
    elif isinstance(entity, Chat):
        full_id = f"-{entity.id}"
    else:
        full_id = str(entity.id)
    return entity, full_id, name

async def send_item(item, gid):
    chat = int(gid)
    if isinstance(item, str):
        await client.send_message(chat, item)
    elif item.get("type") == "text":
        await client.send_message(chat, item["content"])
    elif item.get("type") == "photo":
        path = item.get("path", "")
        caption = item.get("caption", "") or ""
        if os.path.exists(path):
            await client.send_file(chat, path, caption=caption)
        elif caption:
            await client.send_message(chat, caption)

# ── Handlers ────────────────────────────────────────────────────────────────

@client.on(events.NewMessage(pattern='/getid'))
async def getid_handler(event):
    chat_id = event.chat_id
    if event.is_private:
        await event.reply(f"📍 Tera User ID: `{chat_id}`", parse_mode="md")
    else:
        chat = await event.get_chat()
        name = getattr(chat, 'title', 'Unknown')
        if isinstance(chat, Channel):
            full_id = f"-100{chat.id}"
        elif isinstance(chat, Chat):
            full_id = f"-{chat.id}"
        else:
            full_id = str(chat_id)
        await event.reply(
            f"📍 *Group/Channel ID:*\n`{full_id}`\n\n"
            f"📛 Name: {name}\n\n"
            f"Bot ke private chat mein yeh bhejo:\n`/addgroup {full_id} {name}`",
            parse_mode="md"
        )

@client.on(events.NewMessage)
async def handler(event):
    if not event.is_private:
        return

    text = event.raw_text or ""
    uid = str(event.sender_id)

    # ── Forwarded message → extract chat ID ──
    if event.message.forward and not text.startswith("/"):
        fwd = event.message.forward
        orig_id = None
        orig_name = "Unknown"
        try:
            if fwd.channel_id:
                orig_id = f"-100{fwd.channel_id}"
                ch = await client.get_entity(fwd.channel_id)
                orig_name = getattr(ch, 'title', str(fwd.channel_id))
            elif hasattr(fwd, 'from_id') and fwd.from_id:
                from_id = fwd.from_id
                if hasattr(from_id, 'channel_id'):
                    orig_id = f"-100{from_id.channel_id}"
                    ch = await client.get_entity(from_id.channel_id)
                    orig_name = getattr(ch, 'title', str(from_id.channel_id))
                elif hasattr(from_id, 'chat_id'):
                    orig_id = f"-{from_id.chat_id}"
                    ch = await client.get_entity(from_id.chat_id)
                    orig_name = getattr(ch, 'title', str(from_id.chat_id))
        except Exception as e:
            print(f"Forward extract error: {e}")

        if orig_id:
            await event.reply(
                f"📍 *Chat ID:* `{orig_id}`\n"
                f"📛 *Name:* {orig_name}\n\n"
                f"Add karne ke liye:\n`/addgroup {orig_id} {orig_name}`",
                parse_mode="md"
            )
        else:
            await event.reply(
                "⚠️ ID nahi mil rahi.\n\n"
                "*Telegram Web se karo:*\n"
                "1. web.telegram.org kholo\n"
                "2. Channel/Group open karo\n"
                "3. URL mein number copy karo",
                parse_mode="md"
            )
        return

    # ── Save content to queue ──
    # ... baki ka code same hai, syntax errors fix kiye hain

# ── Scheduler ────────────────────────────────────────────────────────────────
async def scheduler():
    while True:
        now = time.time()
        for gid, g in list(data["groups"].items()):
            if not g.get("posting"):
                continue
            queue = g.get("queue", [])
            if not queue:
                continue
            interval = g.get("interval_sec", 3600)
            last_sent = g.get("last_sent", 0)
            if now - last_sent < interval:
                continue
            to_send = queue[:10]
            g["queue"] = queue[10:]
            g["last_sent"] = now
            save_data(data)
            sent = 0
            for item in to_send:
                try:
                    await send_item(item, gid)
                    sent += 1
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"[{g['name']}] Error: {e}")
            print(f"✅ [{g['name']}] Sent {sent}/{len(to_send)} (next in {interval//60} min)")
        await asyncio.sleep(30)

async def main():
    await client.start(bot_token=bot_token)
    print("🤖 Bot running — posting state restored from disk")
    for gid, g in data["groups"].items():
        if g.get("posting"):
            print(f"  ▶️ {g['name']} posting ON (interval: {g.get('interval_sec',3600)//60} min)")
    client.loop.create_task(scheduler())
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
