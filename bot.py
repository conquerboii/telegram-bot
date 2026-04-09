from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
import asyncio, os, json, time
from dotenv import load_dotenv

load_dotenv()
api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

MEDIA_DIR = "media"
DATA_FILE = "data.json"
os.makedirs(MEDIA_DIR, exist_ok=True)

client = TelegramClient("bot_session", api_id, api_hash)

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"groups":{}, "user_active":{}, "user_broadcast":{}}, f)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

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

async def scheduler():
    while True:
        now = time.time()
        for gid, g in data["groups"].items():
            if not g.get("posting"): continue
            queue = g.get("queue",[])
            if not queue: continue
            interval = g.get("interval_sec",3600)
            last = g.get("last_sent",0)
            if now - last < interval: continue
            to_send = queue[:10]
            g["queue"] = queue[10:]
            g["last_sent"] = now
            save_data()
            for item in to_send:
                try: await send_item(item, gid); await asyncio.sleep(2)
                except: pass
        await asyncio.sleep(10)

@client.on(events.NewMessage)
async def handler(event):
    text = event.raw_text or ""
    uid = event.sender_id
    if text.startswith("/"):
        cmd = text.split()[0]
        if cmd=="/start":
            await event.reply("Bot ready!")
        elif cmd=="/getid":
            await event.reply(f"ID: `{event.chat_id}`")
        elif cmd=="/start_posting":
            gid = get_active_gid(uid)
            if not gid: await event.reply("Select group first."); return
            data["groups"][gid]["posting"]=True
            save_data()
            await event.reply("Posting started!")
        elif cmd=="/stop_posting":
            gid = get_active_gid(uid)
            if not gid: await event.reply("Select group first."); return
            data["groups"][gid]["posting"]=False
            save_data()
            await event.reply("Posting stopped!")

# ── Run Bot ─────────────────────────────────────────────
client.start(bot_token=bot_token)
client.loop.create_task(scheduler())
print("Bot running...")
client.run_until_disconnected()
