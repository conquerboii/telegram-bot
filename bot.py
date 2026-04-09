from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
import asyncio
import json
import os
import time

api_id = int(os.environ[35598649])
api_hash = os.environ[c2818a1b61c263997d48305e16a908c2]
bot_token = os.environ[8486338907:AAGCsp9M2E8KHW1JADGNBTZz39p7rUNRvOM]

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BOT_DIR, "media")
DATA_FILE = os.path.join(BOT_DIR, "data.json")

os.makedirs(MEDIA_DIR, exist_ok=True)

client = TelegramClient('bot_session', api_id, api_hash)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"groups": {}, "user_active": {}, "user_broadcast": {}}

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

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

# ── /getid — works in groups AND private ─────────────────────────────────────

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

# ── Main Handler ──────────────────────────────────────────────────────────────

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
    if not text.startswith("/"):
        broadcast_on = data.get("user_broadcast", {}).get(uid, False)
        if broadcast_on:
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
            for g in data["groups"].values():
                g.setdefault("queue", []).append(item)
            save_data(data)
            names = ", ".join(f"*{g['name']}*" for g in data["groups"].values())
            await event.reply(f"📢 Broadcast saved → {names}", parse_mode="md")
        else:
            gid = get_active_gid(event.sender_id)
            if not gid:
                await event.reply(
                    "❗ Koi group active nahi.\n"
                    "/groups — list dekho\n"
                    "/select 1 — number se select karo",
                    parse_mode="md"
                )
                return
            g = data["groups"][gid]
            if event.photo:
                filename = f"photo_{event.id}.jpg"
                filepath = os.path.join(MEDIA_DIR, filename)
                await event.message.download_media(file=filepath)
                g.setdefault("queue", []).append({"type": "photo", "path": filepath, "caption": event.message.text or ""})
                save_data(data)
                await event.reply(f"🖼 Photo saved → *{g['name']}* (Queue: {len(g['queue'])})", parse_mode="md")
            elif text:
                g.setdefault("queue", []).append({"type": "text", "content": text})
                save_data(data)
                await event.reply(f"✅ Saved → *{g['name']}* (Queue: {len(g['queue'])})", parse_mode="md")
        return

    # ── Commands ──────────────────────────────────────────────────────────────

    if text == "/start":
        await event.reply(
            "👋 *Assalam o Alaikum! Bot ready hai!*\n\n"
            "Shuru karne ke liye:\n"
            "1️⃣ `/groups` — apne groups dekho\n"
            "2️⃣ `/select 1` — group select karo\n"
            "3️⃣ Content bhejo — queue mein save hoga\n"
            "4️⃣ `/start_posting` — posting shuru karo\n\n"
            "Puri list ke liye `/help` bhejo.",
            parse_mode="md"
        )

    elif text.startswith("/addgroup"):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await event.reply("Usage: `/addgroup <group_id> <naam>`", parse_mode="md")
            return
        raw_id, name = parts[1], parts[2]
        await event.reply("⏳ Telegram se verify ho raha hai...", parse_mode="md")
        try:
            _, full_id, tg_name = await verify_chat(raw_id)
        except ValueError as e:
            await event.reply(f"❌ {e}\n\nSahi ID daalo. Channel se message forward karo taaki ID milei.", parse_mode="md")
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
        await event.reply(
            f"✅ *Verified & Added!*\n"
            f"📛 Telegram Name: {tg_name}\n"
            f"📍 ID: `{full_id}`\n"
            f"⏱ Interval: 60 min (badlne ke liye `/setinterval <minutes>`)\n\n"
            f"Active bhi set ho gaya!",
            parse_mode="md"
        )

    elif text.startswith("/joingroup"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await event.reply("Usage: `/joingroup https://t.me/+xxxx`", parse_mode="md")
            return
        link = parts[1].strip()
        await event.reply("⏳ Join ho raha hai...", parse_mode="md")
        try:
            from telethon.tl.functions.messages import ImportChatInviteRequest
            from telethon.tl.functions.channels import JoinChannelRequest
            if "t.me/+" in link:
                invite_hash = link.split("t.me/+")[1].strip()
                updates = await client(ImportChatInviteRequest(invite_hash))
                chat = updates.chats[0]
            elif "t.me/" in link:
                username = link.split("t.me/")[1].strip().lstrip("@")
                entity = await client.get_entity(username)
                await client(JoinChannelRequest(entity))
                chat = entity
            else:
                await event.reply("❌ Invalid link.", parse_mode="md")
                return
            full_id = f"-100{chat.id}" if isinstance(chat, Channel) else f"-{chat.id}"
            chat_name = getattr(chat, 'title', 'Unknown')
            data["groups"][full_id] = {"name": chat_name, "queue": [], "posting": False, "interval_sec": 3600, "last_sent": 0}
            data["user_active"][uid] = full_id
            save_data(data)
            await event.reply(
                f"✅ *Joined & Added!*\n"
                f"📛 Name: {chat_name}\n"
                f"📍 ID: `{full_id}`\n"
                f"Active bhi set ho gaya!",
                parse_mode="md"
            )
        except Exception as e:
            err = str(e)
            if "already" in err.lower() or "USER_ALREADY" in err:
                await event.reply("ℹ️ Bot pehle se is group mein hai.\nForward karke ID lo ya `/addgroup <id> <naam>` karo.", parse_mode="md")
            else:
                await event.reply(f"❌ Error: `{err}`\n\nChannel ke liye: channel admin se bot ko manually add karwao.", parse_mode="md")

    elif text == "/groups":
        active_gid = get_active_gid(event.sender_id)
        msg = "📋 *Tere Groups/Channels:*\n\n" + groups_list_text(active_gid)
        if data["groups"]:
            msg += "\n\n`/select <number>` se select karo"
        await event.reply(msg, parse_mode="md")

    elif text.startswith("/select"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await event.reply("Usage: `/select <number>`\n`/groups` se number dekho.", parse_mode="md")
            return
        idx = int(parts[1].strip())
        gid = group_index_to_id(idx)
        if not gid:
            await event.reply(f"❌ Number {idx} nahi mila. `/groups` se dekho.", parse_mode="md")
            return
        data["user_active"][uid] = gid
        save_data(data)
        g = data["groups"][gid]
        interval_min = g.get("interval_sec", 3600) // 60
        await event.reply(
            f"✅ Active: *{g['name']}*\n"
            f"Queue: {len(g.get('queue',[]))} items\n"
            f"Interval: {interval_min} min\n"
            f"Posting: {'🟢 On' if g.get('posting') else '🔴 Off'}",
            parse_mode="md"
        )

    elif text.startswith("/setgroup"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await event.reply("Usage: `/setgroup <id>` ya `/select <number>`", parse_mode="md")
            return
        val = parts[1].strip()
        gid = group_index_to_id(int(val)) if val.isdigit() else (val if val in data["groups"] else None)
        if not gid:
            await event.reply("❌ Group nahi mila. `/groups` se dekho.", parse_mode="md")
            return
        data["user_active"][uid] = gid
        save_data(data)
        g = data["groups"][gid]
        await event.reply(f"✅ Active: *{g['name']}* (Queue: {len(g.get('queue',[]))})", parse_mode="md")

    elif text.startswith("/removegroup"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await event.reply("Usage: `/removegroup <number>`\n`/groups` se number dekho.", parse_mode="md")
            return
        val = parts[1].strip()
        gid = group_index_to_id(int(val)) if val.isdigit() else (val if val in data["groups"] else None)
        if not gid:
            await event.reply("❌ Group nahi mila.", parse_mode="md")
            return
        name = data["groups"][gid]["name"]
        del data["groups"][gid]
        if data["user_active"].get(uid) == gid:
            data["user_active"].pop(uid, None)
        save_data(data)
        await event.reply(f"🗑️ Removed: *{name}*", parse_mode="md")

    elif text.startswith("/setinterval"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await event.reply("Usage: `/setinterval <minutes>`\nExample: `/setinterval 60` = 1 ghanta", parse_mode="md")
            return
        minutes = int(parts[1].strip())
        if minutes < 1:
            await event.reply("❌ Minimum 1 minute.", parse_mode="md")
            return
        gid = get_active_gid(event.sender_id)
        if not gid:
            await event.reply("❗ Pehle `/select <number>` se group choose karo.", parse_mode="md")
            return
        data["groups"][gid]["interval_sec"] = minutes * 60
        save_data(data)
        await event.reply(f"⏱ Interval set: *{minutes} minutes* → *{data['groups'][gid]['name']}*", parse_mode="md")

    elif text.startswith("/broadcast"):
        parts = text.split(maxsplit=1)
        arg = parts[1].strip().lower() if len(parts) > 1 else ""
        if arg == "on":
            data.setdefault("user_broadcast", {})[uid] = True
            save_data(data)
            await event.reply("📢 *Broadcast ON* — Ab sabhi groups mein same content jayega!", parse_mode="md")
        elif arg == "off":
            data.setdefault("user_broadcast", {})[uid] = False
            save_data(data)
            active_gid = get_active_gid(event.sender_id)
            active_name = data["groups"][active_gid]["name"] if active_gid else "koi nahi"
            await event.reply(f"📢 *Broadcast OFF* — Sirf active group: *{active_name}*", parse_mode="md")
        else:
            is_on = data.get("user_broadcast", {}).get(uid, False)
            await event.reply(f"Broadcast: *{'ON 📢' if is_on else 'OFF'}*\nUse: `/broadcast on` ya `/broadcast off`", parse_mode="md")

    elif text == "/start_posting":
        gid = get_active_gid(event.sender_id)
        if not gid:
            await event.reply("❗ Pehle `/select <number>` se group choose karo.", parse_mode="md")
            return
        data["groups"][gid]["posting"] = True
        save_data(data)
        interval_min = data["groups"][gid].get("interval_sec", 3600) // 60
        await event.reply(f"🟢 Posting start: *{data['groups'][gid]['name']}* (har {interval_min} min mein)", parse_mode="md")

    elif text == "/stop_posting":
        gid = get_active_gid(event.sender_id)
        if not gid:
            await event.reply("❗ Pehle `/select <number>` se group choose karo.", parse_mode="md")
            return
        data["groups"][gid]["posting"] = False
        save_data(data)
        await event.reply(f"🔴 Posting stop: *{data['groups'][gid]['name']}*", parse_mode="md")

    elif text == "/start_all":
        for g in data["groups"].values():
            g["posting"] = True
        save_data(data)
        await event.reply("🟢 Sabhi groups ki posting start!", parse_mode="md")

    elif text == "/stop_all":
        for g in data["groups"].values():
            g["posting"] = False
        save_data(data)
        await event.reply("🔴 Sabhi groups ki posting stop!", parse_mode="md")

    elif text == "/clear":
        gid = get_active_gid(event.sender_id)
        if not gid:
            await event.reply("❗ Pehle `/select <number>` se group choose karo.", parse_mode="md")
            return
        data["groups"][gid]["queue"] = []
        save_data(data)
        await event.reply(f"🗑️ Queue clear: *{data['groups'][gid]['name']}*", parse_mode="md")

    elif text == "/status":
        active_gid = get_active_gid(event.sender_id)
        broadcast_on = data.get("user_broadcast", {}).get(uid, False)
        msg = f"📊 *Status*\n📢 Broadcast: {'ON' if broadcast_on else 'OFF'}\n\n"
        msg += groups_list_text(active_gid)
        await event.reply(msg, parse_mode="md")

    elif text == "/send_now":
        gid = get_active_gid(event.sender_id)
        if not gid:
            await event.reply("❗ Pehle `/select <number>` se group choose karo.", parse_mode="md")
            return
        g = data["groups"][gid]
        queue = g.get("queue", [])
        if not queue:
            await event.reply(f"📭 Queue khali: *{g['name']}*", parse_mode="md")
            return
        to_send = queue[:10]
        g["queue"] = queue[10:]
        g["last_sent"] = time.time()
        save_data(data)
        await event.reply(f"⏳ Bhej raha hoon {len(to_send)} items → *{g['name']}*...", parse_mode="md")
        sent, errors = 0, []
        for item in to_send:
            try:
                await send_item(item, gid)
                sent += 1
                await asyncio.sleep(1)
            except Exception as e:
                errors.append(str(e))
        reply = f"✅ {sent}/{len(to_send)} bheje → *{g['name']}* (Queue: {len(g['queue'])} bache)"
        if errors:
            reply += "\n\n❌ Errors:\n" + "\n".join(errors[:3])
        await event.reply(reply, parse_mode="md")

    elif text == "/test_connection":
        gid = get_active_gid(event.sender_id)
        if not gid:
            await event.reply("❗ Pehle `/select <number>` se group choose karo.", parse_mode="md")
            return
        try:
            await client.send_message(int(gid), "🤖 Bot connection test!")
            await event.reply(f"✅ Test message gaya → *{data['groups'][gid]['name']}*", parse_mode="md")
        except Exception as e:
            await event.reply(f"❌ Error: `{e}`", parse_mode="md")

    elif text == "/help":
        await event.reply(
            "📋 *Commands:*\n\n"
            "*🔍 ID Pata Karo:*\n"
            "/getid — Group mein type karo → ID milegi\n"
            "Ya koi msg *forward* karo bot ko → ID milegi\n"
            "/joingroup `<link>` — Invite link se join karo\n\n"
            "*➕ Groups Manage:*\n"
            "/addgroup `<id> <naam>` — Add + verify\n"
            "/groups — Numbered list dekho\n"
            "/select `<number>` — Group select karo\n"
            "/removegroup `<number>` — Group remove karo\n\n"
            "*⏱ Interval:*\n"
            "/setinterval `<minutes>` — Posting interval set karo\n\n"
            "*📢 Broadcast:*\n"
            "/broadcast on — Sabhi groups mein same content\n"
            "/broadcast off — Sirf active group mein\n\n"
            "*▶️ Posting:*\n"
            "/start\\_posting — Active group start\n"
            "/stop\\_posting — Active group stop\n"
            "/start\\_all — Sabhi start\n"
            "/stop\\_all — Sabhi stop\n"
            "/send\\_now — Abhi turant bhejo\n\n"
            "*📊 Info:*\n"
            "/status — Saari info\n"
            "/clear — Active queue clear\n"
            "/test\\_connection — Connection check\n\n"
            "📩 Text ya 🖼 Photo bhejo → active group ki queue mein jayega",
            parse_mode="md"
        )


# ── Scheduler ─────────────────────────────────────────────────────────────────

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
