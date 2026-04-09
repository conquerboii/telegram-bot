from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
import asyncio, os, json, time
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BOT_DIR, "media")
DATA_FILE = os.path.join(BOT_DIR, "data.json")
os.makedirs(MEDIA_DIR, exist_ok=True)

client = TelegramClient("bot_session", api_id, api_hash)

# ── Load / Save data ──────────────────────────────────────
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"groups": {}, "user_active": {}, "user_broadcast": {}}, f)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

data = load_data()

# ── Utility Functions ─────────────────────────────────────
def get_active_gid(uid):
    gid = data["user_active"].get(str(uid))
    if gid in data["groups"]:
        return gid
    if len(data["groups"])==1:
        return list(data["groups"].keys())[0]
    return None

async def send_item(item, gid):
    chat = int(gid)
    if item.get("type")=="text":
        await client.send_message(chat, item["content"])
    elif item.get("type")=="photo":
        if os.path.exists(item["path"]):
            await client.send_file(chat, item["path"], caption=item.get("caption",""))

# ── Scheduler ─────────────────────────────────────────────
async def scheduler():
    while True:
        now = time.time()
        for gid, g in list(data["groups"].items()):
            if not g.get("posting"): continue
            queue = g.get("queue", [])
            if not queue: continue
            interval = g.get("interval_sec", 3600)
            last = g.get("last_sent", 0)
            if now - last < interval: continue
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
        await asyncio.sleep(10)

# ── Command Handlers ─────────────────────────────────────
@client.on(events.NewMessage)
async def handler(event):
    text = event.raw_text or ""
    uid = event.sender_id
    if not text.startswith("/"):
        return  # Normal messages can be handled later if queueing needed

    cmd = text.split()[0]

    if cmd=="/start":
        await event.reply("🤖 Bot ready! Use /getid, /addgroup, /start_posting etc.")
    elif cmd=="/getid":
        await event.reply(f"📍 ID: `{event.chat_id}`")
    elif cmd=="/start_posting":
        gid = get_active_gid(uid)
        if not gid: await event.reply("❗ Select a group first."); return
        data["groups"][gid]["posting"]=True
        save_data(data)
        await event.reply(f"🟢 Posting started: *{data['groups'][gid]['name']}*")
    elif cmd=="/stop_posting":
        gid = get_active_gid(uid)
        if not gid: await event.reply("❗ Select a group first."); return
        data["groups"][gid]["posting"]=False
        save_data(data)
        await event.reply(f"🔴 Posting stopped: *{data['groups'][gid]['name']}*")
    elif cmd=="/send_now":
        gid = get_active_gid(uid)
        if not gid: await event.reply("❗ Select a group first."); return
        g = data["groups"][gid]
        queue = g.get("queue", [])
        if not queue: await event.reply("📭 Queue empty!"); return
        to_send = queue[:10]
        g["queue"] = queue[10:]
        g["last_sent"] = time.time()
        save_data(data)
        sent = 0
        for item in to_send:
            try:
                await send_item(item, gid)
                sent +=1
                await asyncio.sleep(1)
            except: pass
        await event.reply(f"✅ Sent {sent}/{len(to_send)} items → *{g['name']}*")
    elif cmd=="/clear":
        gid = get_active_gid(uid)
        if not gid: await event.reply("❗ Select a group first."); return
        data["groups"][gid]["queue"]=[]
        save_data(data)
        await event.reply(f"🗑️ Queue cleared → *{data['groups'][gid]['name']}*")
    elif cmd=="/status":
        gid = get_active_gid(uid)
        msg = "📊 Status\n"
        for g_id, g in data["groups"].items():
            msg += f"{g['name']} | Posting: {'🟢' if g.get('posting') else '🔴'} | Queue: {len(g.get('queue',[]))}\n"
        await event.reply(msg or "❌ No groups found.")
    elif cmd=="/setinterval":
        parts = text.split()
        if len(parts)<2 or not parts[1].isdigit(): 
            await event.reply("Usage: /setinterval <minutes>"); return
        minutes = int(parts[1])
        gid = get_active_gid(uid)
        if not gid: await event.reply("❗ Select a group first."); return
        data["groups"][gid]["interval_sec"]=minutes*60
        save_data(data)
        await event.reply(f"⏱ Interval set: {minutes} min → *{data['groups'][gid]['name']}*")
    elif cmd=="/removegroup":
        parts = text.split()
        if len(parts)<2: await event.reply("Usage: /removegroup <group_id>"); return
        gid = parts[1].strip()
        if gid not in data["groups"]: await event.reply("❌ Group not found."); return
        name = data["groups"][gid]["name"]
        del data["groups"][gid]
        save_data(data)
        await event.reply(f"🗑️ Removed: *{name}*")
    elif cmd=="/test_connection":
        gid = get_active_gid(uid)
        if not gid: await event.reply("❗ Select a group first."); return
        try:
            await client.send_message(int(gid), "🤖 Test message")
            await event.reply("✅ Test message sent!")
        except Exception as e:
            await event.reply(f"❌ Error: {e}")

# ── Run Bot ─────────────────────────────────────────────
client.start(bot_token=bot_token)
client.loop.create_task(scheduler())
print("🤖 Bot running with all features…")
client.run_until_disconnected()
