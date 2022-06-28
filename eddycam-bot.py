import logging
from turtle import heading
import requests
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CallbackContext, CommandHandler, filters, CallbackQueryHandler
from qingping import qingping
from parse1090 import parse1090
import os
import sys
import time
import itertools

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

with open('imageurl.txt') as f:
    imageurls = list(filter(None, (line.rstrip() for line in f)))

with open('rtspurl.txt') as f:
    rtspurls = list(filter(None, (line.rstrip() for line in f)))

with open('key.txt') as f:
    token = f.readline().strip()

def process_chat_id(line):
    return int(line.strip())

with open('allowedchatid.txt') as f:
    allowed_chats = list(map(process_chat_id, f.readlines()))

dump1090_url = "http://localhost:8080/data/aircraft.json"
last_env_request_time = 0
env_cache = ""
aircraft_button_row_size = 3

def to_input_media_photo(url):
    image_request = requests.get(url)
    return InputMediaPhoto(media=bytes(image_request.content))

def grouper(n, iterable, fillvalue=None):
    "grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=fillvalue, *args)

def create_aircraft_inlinebuttons(sorted_ac):
    buttons = [InlineKeyboardButton(ac.ident.strip(), callback_data=f"adsb_{ac.hex}") for ac in sorted_ac]
    matrix = list(grouper(aircraft_button_row_size, buttons))
    matrix = [[inner for inner in outer if inner is not None] for outer in matrix] # remove any Nones and convert to list
    return matrix

async def adsb_summary(update: Update, context: CallbackContext.DEFAULT_TYPE):
    aircraft = parse1090.parse_aircraft(dump1090_url)
    output = f"EddyRadio can currently see *{len(aircraft)}* transponders, of which *{len(parse1090.in_sky(aircraft))}* are in the air and *{len(parse1090.with_ident(aircraft))}* have a valid ident"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=output, parse_mode=ParseMode.MARKDOWN)

async def adsb_list(update: Update, context: CallbackContext.DEFAULT_TYPE):
    aircraft = parse1090.parse_aircraft(dump1090_url)
    filtered_aircraft = parse1090.in_sky_and_ident(aircraft)
    filtered_aircraft.sort(key=lambda ac: ac.rssi, reverse=True)
    output = f"*Listing {len(filtered_aircraft)} aircraft in the air and with idents*\n"
    filtered_aircraft_text = [f"{ac.ident.strip()} at {ac.alt_baro}ft, {ac.rssi} dBm" for ac in filtered_aircraft]
    output = output + "\n".join(filtered_aircraft_text)
    keyboard = InlineKeyboardMarkup(create_aircraft_inlinebuttons(filtered_aircraft))
    await context.bot.send_message(chat_id=update.effective_chat.id, text=output, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def adsb_info_update(update: Update, context: CallbackContext.DEFAULT_TYPE):
    query = update.callback_query
    hex = query.data.lstrip("adsb_")
    print("Getting data for "+hex)
    aircraft = parse1090.parse_aircraft(dump1090_url)
    target_list = list(filter(lambda ac: (ac.hex == hex), aircraft))
    if not target_list and ac.ident and ac.ident.strip() and ac.alt_baro:
        await query.edit_message_text(text="Couldn't find the aircraft anymore :(")
        return
    target = target_list[0]
    squawk = target.squawk or "Unknown"
    gs = target.gs or "Unknown"
    heading = target.track or "Unknown"
    lat = float(target.lat) or "Unknown"
    lon = float(target.lon) or "Unknown"
    output = f"*Ident:* {target.ident.strip()}\n*Altitude (barometric):* {target.alt_baro}ft\n*Ground Speed:* {gs}kt\n*Squawk:* {squawk}\n*Heading:* {heading}°\n*Position:* {lat:.4f}°N, {lon:.4f}°E\n*Signal Strength:* {target.rssi} dBm"
    buttons = [[ InlineKeyboardButton("Refresh", callback_data=query.data) ]]
    if (lat and lon):
        buttons[0].append(InlineKeyboardButton("Map", callback_data=f"map_{lat}_{lon}"))
    keyboard = InlineKeyboardMarkup(buttons)
    await query.answer()
    await query.edit_message_text(text=output, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

async def adsb_map(update: Update, context: CallbackContext.DEFAULT_TYPE):
    query = update.callback_query
    latlon = query.data.lstrip("map_").split("_", 1) # 0 is lat, 1 is lon
    await query.answer()
    await context.bot.send_location(chat_id=update.effective_chat.id, latitude=float(latlon[0]), longitude=float(latlon[1]), horizontal_accuracy=3)

async def environment(update: Update, context: CallbackContext.DEFAULT_TYPE):
    global last_env_request_time
    global env_cache
    time_until_limit = last_env_request_time + 120 - int(time.time())
    if time_until_limit > 0:
        pretty = f"*Environment in Eddy's Room (cached {time_until_limit}s)*\n" + env_cache
        await context.bot.send_message(chat_id=update.effective_chat.id, text=pretty, parse_mode=ParseMode.MARKDOWN)
        return
    try:
        result = list(qingping.get_device_info().items())[0][1]
    except requests.exceptions.Timeout:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Xiaomi API is crappy and timed out")
        return
    pretty = "*Environment in Eddy's Room (15min res)*\n" + qingping.airquality_pretty(result, True)
    last_env_request_time = int(time.time())
    env_cache = qingping.airquality_pretty(result, True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=pretty, parse_mode=ParseMode.MARKDOWN)

async def neko(update: Update, context: CallbackContext.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="nyaa~")


async def snapshot(update: Update, context: CallbackContext.DEFAULT_TYPE):
    isRaw = (len(context.args) > 1 and context.args[1] == "raw")
    try:
        camera_index = int(context.args[0]) if len(context.args) > 0 else -1
    except ValueError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Expected int or blank")
        return
    if (camera_index >= len(imageurls)):
         await context.bot.send_message(chat_id=update.effective_chat.id, text="Camera doesn't exist")
         return
    if (camera_index == -1):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Taking your pictures...")
        photos = list(map(to_input_media_photo, imageurls))
        await context.bot.send_media_group(update.effective_chat.id, photos)
    else:
        image_request = requests.get(imageurls[camera_index])
        if isRaw:
            await context.bot.send_document(update.effective_chat.id, bytes(image_request.content), caption="here's your picture uwu")
        else:
            await context.bot.send_photo(update.effective_chat.id, bytes(image_request.content), caption="here's your picture uwu", filename="eddycam.jpg")


async def clip(update: Update, context: CallbackContext.DEFAULT_TYPE):
    try:
        camera_index = int(context.args[0]) if len(context.args) > 0 else 0
    except ValueError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Expected int or blank")
        return
    if (camera_index >= len(rtspurls)):
         await context.bot.send_message(chat_id=update.effective_chat.id, text="Camera doesn't exist")
         return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'll record a 10s clip for you!...")
    path = os.path.join(sys.argv[1], 'rtsp_cache_recording.mp4')
    os.system(f'ffmpeg -y -rtsp_transport tcp -i "{rtspurls[camera_index]}" -c copy -t 10 {path}')
    await context.bot.send_video(update.effective_chat.id, open(path, "rb"), caption="here's your clip ^w^",
                                 write_timeout=60)

async def button_handler(update: Update, context: CallbackContext.DEFAULT_TYPE):
    query = update.callback_query
    if (query.data.startswith("adsb_")):
        await adsb_info_update(update, context)
    if (query.data.startswith("map_")):
        await adsb_map(update, context)

if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()

    chat_filter = filters.Chat(chat_id=allowed_chats)

    environment_handler = CommandHandler('environment', environment, filters=chat_filter)
    neko_handler = CommandHandler('neko', neko)
    snapshot_handler = CommandHandler('snapshot', snapshot, filters=chat_filter)
    clip_handler = CommandHandler('clip', clip, filters=chat_filter)
    adsb_summary_handler = CommandHandler('adsb_summary', adsb_summary, filters=chat_filter)
    adsb_list_handler = CommandHandler('adsb_list', adsb_list, filters=chat_filter)
    application.add_handler(neko_handler)
    application.add_handler(snapshot_handler)
    application.add_handler(clip_handler)
    application.add_handler(environment_handler)
    application.add_handler(adsb_list_handler)
    application.add_handler(adsb_summary_handler)
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling()
