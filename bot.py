from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
import asyncio
import json
import os
import time
from dotenv import load_dotenv

# ── Environment Variables ─────────────────────────────────────────────
load_dotenv()
api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

# ── Directories ───────────────────────────────────────────────────────
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BOT_DIR, "media")
DATA_FILE = os.path.join(BOT_DIR, "data.json")
os.makedirs(MEDIA_DIR, exist_ok=True)

# ── Client ────────────────────────────────────────────────────────────
client = TelegramClient('bot_session', api_id, api_hash)

# ── Data Load/Save ───────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"groups": {}, "user_active": {}, "user_broadcast": {}}

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

# ── Helper Functions ──────────────────────────────────────────────────
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

# ── Event Handler ────────────────────────────────────────────────────
@client.on(events.NewMessage)
async def handler(event):
    text = event.raw_text or ""
    uid = str(event.sender_id)

    # ── Commands ──────────────────────────────────────────────────────
    if text.startswith("/"):
        cmd = text.split()[0]

        # ── /start ─────────────────────────────
        if cmd == "/start":
            await event.reply(
                "👋 *Bot ready hai!*\n\n"
                "/groups — groups dekho\n"
                "/addgroup <id> <name> — add karo\n"
                "/broadcast on/off\n"
                "/start_posting — posting start\n"
                "/help — full list",
                parse_mode="md"
            )
            return

        # ── /getid ─────────────────────────────
        if cmd == "/getid":
            chat_id = event.chat_id
            await event.reply(f"📍 ID: `{chat_id}`", parse_mode="md")
            return

        # ── /addgroup ──────────────────────────
        if cmd == "/addgroup":
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
                "posting": data["groups"].get(full_id, {}).get("posting", False),
                "interval_sec": data["groups"].get(full_id, {}).get("interval_sec", 3600),
                "last_sent": data["groups"].get(full_id, {}).get("last_sent", 0),
            }
            data["user_active"][uid] = full_id
            save_data(data)
            await event.reply(f"✅ *Added & Verified!* {name}", parse_mode="md")
            return

        # ── /broadcast ─────────────────────────
        if cmd == "/broadcast":
            arg = text.split(maxsplit=1)[1].strip().lower() if len(text.split())>1 else ""
            if arg == "on":
                data.setdefault("user_broadcast", {})[uid] = True
                save_data(data)
                await event.reply("📢 Broadcast ON!", parse_mode="md")
            elif arg == "off":
                data.setdefault("user_broadcast", {})[uid] = False
                save_data(data)
                await event.reply("📢 Broadcast OFF!", parse_mode="md")
            else:
                is_on = data.get("user_broadcast", {}).get(uid, False)
                await event.reply(f"Broadcast: {'ON' if is_on else 'OFF'}", parse_mode="md")
            return

        # ── /groups ────────────────────────────
        if cmd == "/groups":
            active_gid = get_active_gid(event.sender_id)
            msg = "📋 *Groups:*\n\n" + groups_list_text(active_gid)
            await event.reply(msg, parse_mode="md")
            return

        # ── /select ────────────────────────────
        if cmd == "/select":
            parts = text.split(maxsplit=1)
            if len(parts)<2 or not parts[1].isdigit():
                await event.reply("Usage: `/select <number>`", parse_mode="md")
                return
            idx = int(parts[1])
            gid = group_index_to_id(idx)
            if not gid:
                await event.reply(f"❌ Number {idx} nahi mila.", parse_mode="md")
                return
            data["user_active"][uid] = gid
            save_data(data)
            g = data["groups"][gid]
            await event.reply(f"✅ Active: *{g['name']}*", parse_mode="md")
            return

    # ── Save content to queue ───────────────────────────────────────────
    if not text.startswith("/"):
        gid = get_active_gid(event.sender_id)
        if not gid:
            return
        g = data["groups"][gid]
        if event.photo:
            filename = f"photo_{event.id}.jpg"
            filepath = os.path.join(MEDIA_DIR, filename)
            await event.message.download_media(file=filepath)
            g.setdefault("queue", []).append({"type":"photo","path":filepath,"caption":text})
        elif text:
            g.setdefault("queue", []).append({"type":"text","content":text})
        save_data(data)
        await event.reply(f"✅ Saved → *{g['name']}*", parse_mode="md")
        return

# ── Scheduler ──────────────────────────────────────────────────────────
async def scheduler():
    while True:
        now = time.time()
        for gid, g in list(data["groups"].items()):
            if not g.get("posting"): continue
            queue = g.get("queue", [])
            if not queue: continue
            interval = g.get("interval_sec",3600)
            last_sent = g.get("last_sent",0)
            if now - last_sent < interval: continue
            to_send = queue[:10]
            g["queue"] = queue[10:]
            g["last_sent"] = now
            save_data(data)
            for item in to_send:
                try: await send_item(item,gid); await asyncio.sleep(2)
                except Exception as e: print(f"[{g['name']}] Error: {e}")
        await asyncio.sleep(10)

# ── Main ───────────────────────────────────────────────────────────────
async def main():
    await client.start(bot_token=bot_token)
    print("🤖 Bot running")
    client.loop.create_task(scheduler())
    await client.run_until_disconnected()

if __name__=="__main__":
    asyncio.run(main())
