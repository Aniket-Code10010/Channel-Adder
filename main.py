####################################################################
##################### CONFIGURATION ################################
####################################################################

api_id = 6 # int
api_hash = "eb06d4abfb49dc3eeb1aeb98ae0f581e" # string
bot_token = "5433648888:AAFYD1VZvo0jNl2wdPiS8XjxVQ3r_yj9b2k" # string
admins = "1872074304" # string

####################################################################
######################### IMPORTS ##################################
####################################################################

from uuid import uuid1
from datetime import datetime, timedelta
# from cairo import Error
from telethon import TelegramClient, events
from telethon.errors.rpcerrorlist import ApiIdInvalidError
from telethon.tl.functions.messages import (
    ImportChatInviteRequest,
    CheckChatInviteRequest,
)
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.tl.types import InputPeerNotifySettings, InputNotifyPeer
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os, asyncio, random, shutil, sys


####################################################################
########################## DATA SETUP ##############################
####################################################################


bot = TelegramClient(None, api_id=api_id, api_hash=api_hash).start(bot_token=bot_token)

APIS = [[api_id, api_hash]]
if os.path.exists("api.csv"):
    APIS = [
        line.split(",") for line in open("api.csv", "r", encoding="utf-8").readlines()
    ]

session = [
    file.split(".")[0] for file in os.listdir("sessions/") if file.endswith(".session")
]

admin = [int(ad) for ad in admins.split()]

LOADED = []
UNLOADED = []
CLIENTS = []
SCHED = []
DATA = {}
JDATA = {}
LDATA = {}


LdDATA = {}

####################################################################
######################### FUNCTIONS ################################
####################################################################


async def load(phone, uid):
    if phone in LOADED or phone in UNLOADED:
        return
    data = LdDATA.get(uid)
    target = data["target"]
    count = data.get("count") or 0
    if target and count >= target:
        return
    try:
        api_id, api_hash = random.choice(APIS)
        client = TelegramClient(f"sessions/{phone}", api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            raise SystemError
        client.phone = phone
        LOADED.append(phone)
        DATA[phone] = client
        CLIENTS.append(client)
        data["count"] += 1
    except ApiIdInvalidError:
        APIS.remove([api_id, api_hash])
    except BaseException:
        UNLOADED.append(phone)
        session.remove(phone)
        try:
            await client.disconnect()
        except:
            pass
        try:
            if not os.path.isdir("expired"):
                os.mkdir("expired")
            shutil.move(f"sessions/{phone}.session", f"expired/")
        except:
            pass


async def load_all(num):
    uid = str(uuid1())
    LdDATA.update({uid: {"target": num or None, "count": 0}})
    start = 0
    for i in range((len(session) // 10) + 1):
        task = []
        for z in session[start : ((i + 1) * 10)]:
            task.append(load(z, uid))
        start += 10
        if task:
            await asyncio.gather(*task)
            task.clear()
    return LdDATA[uid]["count"]


async def disc_all(num=None):
    for client in list(CLIENTS):
        try:
            await client.disconnect()
            LOADED.remove(client.phone)
        except:
            pass
    CLIENTS.clear()
    return


def stop_interval():
    for sched in SCHED:
        sched.shutdown()
    SCHED.clear()
    JDATA.clear(), LDATA.clear()
    return


async def join_chat(link, mute=False, num=None, clients=[]):
    hash = False
    if "@" in link:
        chat = link.strip().split()[0]
    elif "/joinchat/" in link:
        chat = link.split("/")[-1].replace("+", "")
        hash = True
    elif "+" in link:
        chat = link.split("/")[-1].replace("+", "")
        hash = True
    elif "-100" in link or link.isdigit():
        chat = int(link)
    else:
        chat = link.strip().split()[0]
    cnt = 0
    for phone in clients:
        try:
            if num and cnt >= num:
                break
            client = DATA[phone]
            if hash:
                ch = await client(ImportChatInviteRequest(chat))
            else:
                ch = await client(JoinChannelRequest(chat))
            cnt += 1
            if LDATA.get(link):
                LDATA[link].remove(client.phone)
            if mute:
                await client(
                    UpdateNotifySettingsRequest(
                        peer=InputNotifyPeer(ch.chats[0].id),
                        settings=InputPeerNotifySettings(
                            mute_until=datetime.now() + timedelta(days=365),
                            silent=True,
                        ),
                    )
                )
        except Exception as er:
            if JDATA.get(link):
                JDATA[link].remove(client.phone)
            print(er)
    return cnt


async def leave_chat(link, num=None, clients=[]):
    hash = False
    if "@" in link:
        chat = link.split()[0]
    elif "/joinchat/" in link:
        chat = link.split("/")[-1].replace("+", "")
        hash = True
    elif "+" in link:
        chat = link.split("/")[-1].replace("+", "")
        hash = True
    elif "-100" in link or link.isdigit():
        chat = int(link)
    else:
        chat = link.split()[0]
    cnt = 0
    for phone in clients:
        try:
            client = DATA[phone]
            if hash:
                ch = await client(CheckChatInviteRequest(chat))
                if ch.left:
                    continue
                chat = ch.id
            await client(LeaveChannelRequest(chat))
            cnt += 1
            if JDATA.get(link):
                JDATA[link].remove(client.phone)
            if num and cnt >= num:
                break
        except:
            if LDATA.get(link):
                LDATA[link].remove(client.phone)
    return cnt


async def sched_join(link, mute, count):
    task = []
    if not JDATA.get(link):
        JDATA[link] = []
    for phone in list(LOADED):
        if phone in JDATA[link]:
            continue
        task.append(join_chat(link, mute, clients=[phone]))
        JDATA[link].append(phone)
        if len(task) >= count:
            break
    await asyncio.gather(*task)


async def sched_leave(link, count):
    task = []
    if not LDATA.get(link):
        LDATA[link] = []
    for phone in list(LOADED):
        if phone in LDATA[link]:
            continue
        task.append(leave_chat(link, clients=[phone]))
        LDATA[link].append(phone)
        if len(task) >= count:
            break
    await asyncio.gather(*task)


def get_sec(inp):
    if inp.isdigit():
        return int(inp)
    elif inp.endswith("s"):
        return int(inp[:-1])
    elif inp.endswith("m"):
        return int(inp[:-1]) * 60
    elif inp.endswith("h"):
        return int(inp[:-1]) * 60 * 60


####################################################################
######################## COMMANDS ##################################
####################################################################


@bot.on(events.NewMessage(pattern="^/start"))
async def _(e):
    await e.reply(
        f"Hello Sir!!!\n\nTOTAL SESSIONS: {len(session)}\nTOTAL CONNECTED: {len(LOADED)}\nERROR CONNECTING: {len(UNLOADED)}"
    )


@bot.on(events.NewMessage(pattern="^/load ?(.*)"))
async def _(e):
    if not e.sender_id in admin:
        return
    cnt = e.pattern_match.group(1) or None
    if cnt and cnt.isdigit():
        cnt = int(cnt)
    x = await e.reply(f"Loading {cnt if cnt else 'All' } Sessions...")
    num = await load_all(num=cnt)
    await x.edit(
        f"Sucessfully loaded {num} Clients.\n\nTOTAL SESSIONS: {len(session)}\nTOTAL CONNECTED: {len(LOADED)}\nERROR CONNECTING: {len(UNLOADED)}"
    )


@bot.on(events.NewMessage(pattern="^/end"))
async def _(e):
    if not e.sender_id in admin:
        return
    x = await e.reply("Disconnecting...")
    stop_interval()
    await disc_all()
    await x.edit("All Disconnected & Intervals Stopped.")


@bot.on(events.NewMessage(pattern="^/stop"))
async def _(e):
    if not e.sender_id in admin:
        return
    stop_interval()
    await e.reply("All Intervals Stopped")


@bot.on(events.NewMessage(pattern="^/leave (.*)"))
async def _(e):
    if not e.sender_id in admin:
        return
    pat = e.pattern_match.group(1)
    if not pat:
        return
    inp = pat.split()
    if len(inp) == 2:
        link, num = inp
        interval = None
    elif len(inp) == 3:
        link, num, interval = inp
    else:
        return
    num = int(num)
    if not interval:
        x = await e.reply(f"Leaving {link}")
        nn = await leave_chat(link, clients=LOADED, num=num)
        await x.edit(f"{nn} clients left.")
    else:
        interval_time = get_sec(interval)
        if not interval_time:
            return await e.reply("Wrong Interval time format.")
        await e.reply(
            f"PROCESS STARTED\n\n{num} client will left {link} on interval of {interval}"
        )
        await sched_leave(link, num)
        schd = AsyncIOScheduler()
        schd.add_job(
            sched_leave, trigger="interval", args=[link, num], seconds=interval_time
        )
        schd.start()
        SCHED.append(schd)


@bot.on(events.NewMessage(pattern="^/join (.*)"))
async def _(e):
    if not e.sender_id in admin:
        return
    mute = False
    pat = e.pattern_match.group(1)
    if not pat:
        return
    inp = pat.split()
    if len(inp) == 2:
        link, num = inp
        interval = None
    elif len(inp) == 3:
        link, num, interval = inp
    else:
        return
    num = int(num)
    if not interval:
        x = await e.reply(f"Joining {link}")
        nn = await join_chat(link, mute, num, clients=LOADED)
        await x.edit(f"{nn} clients joined {link}")
    else:
        interval_time = get_sec(interval)
        if not interval_time:
            return await e.reply("Wrong Interval time format.")
        await e.reply(
            f"PROCESS STARTED\n\n{num} client will join {link} on interval of {interval}"
        )
        await sched_join(link, mute, num)
        schd = AsyncIOScheduler()
        schd.add_job(
            sched_join,
            trigger="interval",
            args=[link, mute, num],
            seconds=interval_time,
        )
        schd.start()
        SCHED.append(schd)


@bot.on(events.NewMessage(pattern="^/joinmute (.*)"))
async def _(e):
    if not e.sender_id in admin:
        return
    mute = True
    pat = e.pattern_match.group(1)
    if not pat:
        return
    inp = pat.split()
    if len(inp) == 2:
        link, num = inp
        interval = None
    elif len(inp) == 3:
        link, num, interval = inp
    else:
        return
    num = int(num)
    if not interval:
        x = await e.reply(f"Joining {link}")
        nn = await join_chat(link, mute, num, clients=LOADED)
        await x.edit(f"{nn} clients joined {link}")
    else:
        interval_time = get_sec(interval)
        if not interval_time:
            return await e.reply("Wrong Interval time format.")
        await e.reply(
            f"PROCESS STARTED\n\n{num} client will join {link} on interval of {interval}"
        )
        await sched_join(link, mute, num)
        schd = AsyncIOScheduler()
        schd.add_job(
            sched_join,
            trigger="interval",
            args=[link, mute, num],
            seconds=interval_time,
        )
        schd.start()
        SCHED.append(schd)


@bot.on(events.NewMessage(pattern="^/admin"))
async def _(e):
    await e.reply(admins)


@bot.on(events.NewMessage(pattern="^/help"))
async def _(e):
    await e.reply(
        """
Some following command

/start 
Start the bot

/load <number of acc>
Connect clients
__Note: without loading clients you cant use other func__


/join  <link> <count> <interval>
You can use without interval too
__Note: in interval put- 1h or 1m or 1s__

/joinmute  <link> <count> <interval>
You can use without interval too
__Note: in interval put- 1h or 1m or 1s__

/leave  <link> <count> <interval>
You can use without interval too
__Note: in interval put- 1h or 1m or 1s__

/end
Disconnect all clients

/stop
Stop all running Interval Process.

/exit
Stop Everything & Bot off

/admins
To get ids of admin who can use bot.
    """
    )


@bot.on(events.NewMessage(pattern="^/exit"))
async def _(e):
    if not e.sender_id in admin:
        return
    stop_interval()
    await disc_all()
    sys.exit()


####################################################################
######################### RUN-BOT ##################################
####################################################################

with bot:
    print("Bot Started")
    bot.run_until_disconnected()
