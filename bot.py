# bot.py — Full Stable Telegram Auto Forward Bot

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
import asyncio
import json
import os
import time

# ── Config (from .env) ─────────────────────────────────────────────
api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BOT_DIR, "media")
DATA_FILE = os.path.join(BOT_DIR, "data.json")
os.makedirs(MEDIA_DIR, exist_ok=True)

client = TelegramClient('bot_session', api_id, api_hash)

# ── Data Handling ─────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"groups": {}, "user_active": {}, "user_broadcast": {}}

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

# ── Helpers ───────────────────────────────────────────────────────
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
        interval_min = g.get("interval_sec", 3600) // 60
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

# ── Command Handlers ──────────────────────────────────────────────
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
                "⚠️ ID nahi mil rahi.\nForward karke ID lo ya web.telegram.org se check karo.",
                parse_mode="md"
            )
        return

    # ── Process commands & normal messages ──
    if text.startswith("/"):
        await handle_command(event, text, uid)
    else:
        await handle_content(event, text, uid)

# ── Handle normal content ──────────────────────────────────────────
async def handle_content(event, text, uid):
    broadcast_on = data.get("user_broadcast", {}).get(uid, False)
    if not data["groups"]:
        await event.reply("❗ Koi group nahi hai. `/addgroup <id> <naam>` se add karo.", parse_mode="md")
        return

    if event.photo:
        filename = f"photo_{event.id}.jpg"
        filepath = os.path.join(MEDIA_DIR, filename)
        await event.message.download_media(file=filepath)
        item = {"type": "photo", "path": filepath, "caption": event.message.text or ""}
    elif text:
        item = {"type": "text", "content": text}
    else:
        return

    if broadcast_on:
        for g in data["groups"].values():
            g.setdefault("queue", []).append(item)
        save_data(data)
        names = ", ".join(f"*{g['name']}*" for g in data["groups"].values())
        await event.reply(f"📢 Broadcast saved → {names}", parse_mode="md")
    else:
        gid = get_active_gid(int(uid))
        if not gid:
            await event.reply("❗ Pehle `/select <number>` se group choose karo.", parse_mode="md")
            return
        g = data["groups"][gid]
        g.setdefault("queue", []).append(item)
        save_data(data)
        await event.reply(f"✅ Saved → *{g['name']}* (Queue: {len(g['queue'])})", parse_mode="md")

# ── Handle commands ──────────────────────────────────────────────
async def handle_command(event, text, uid):
    if text == "/start":
        await event.reply("👋 *Bot ready!*", parse_mode="md")
    elif text.startswith("/addgroup"):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await event.reply("Usage: `/addgroup <group_id> <naam>`", parse_mode="md")
            return
        raw_id, name = parts[1], parts[2]
        try:
            _, full_id, tg_name = await verify_chat(raw_id)
        except ValueError as e:
            await event.reply(f"❌ {e}", parse_mode="md")
            return
        data["groups"][full_id] = {
            "name": name,
            "queue": data["groups"].get(full_id, {}).get("queue", []),
            "posting": False,
            "interval_sec": 3600,
            "last_sent": 0,
        }
        data["user_active"][uid] = full_id
        save_data(data)
        await event.reply(f"✅ Added: *{name}*", parse_mode="md")
    elif text == "/groups":
        active_gid = get_active_gid(int(uid))
        msg = groups_list_text(active_gid)
        await event.reply(msg, parse_mode="md")
    elif text.startswith("/select"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            await event.reply("Usage: `/select <number>`", parse_mode="md")
            return
        idx = int(parts[1])
        gid = group_index_to_id(idx)
        if not gid:
            await event.reply("❌ Number not found.", parse_mode="md")
            return
        data["user_active"][uid] = gid
        save_data(data)
        await event.reply(f"✅ Active: *{data['groups'][gid]['name']}*", parse_mode="md")
    elif text.startswith("/broadcast"):
        arg = text.split(maxsplit=1)[1].lower() if len(text.split())>1 else ""
        data.setdefault("user_broadcast", {})[uid] = (arg=="on")
        save_data(data)
        await event.reply(f"📢 Broadcast {'ON' if arg=='on' else 'OFF'}", parse_mode="md")
    elif text == "/start_posting":
        gid = get_active_gid(int(uid))
        if gid:
            data["groups"][gid]["posting"] = True
            save_data(data)
            await event.reply(f"🟢 Posting started: *{data['groups'][gid]['name']}*", parse_mode="md")
    elif text == "/stop_posting":
        gid = get_active_gid(int(uid))
        if gid:
            data["groups"][gid]["posting"] = False
            save_data(data)
            await event.reply(f"🔴 Posting stopped: *{data['groups'][gid]['name']}*", parse_mode="md")
    # ── Add other commands like /send_now, /clear, /status, /setinterval, /removegroup, /test_connection here similarly

# ── Scheduler ──────────────────────────────────────────────────────
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
            for item in to_send:
                try:
                    await send_item(item, gid)
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"[{g['name']}] Error: {e}")
        await asyncio.sleep(30)

# ── Main ───────────────────────────────────────────────────────────
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 Bot running")
    client.loop.create_task(scheduler())
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
