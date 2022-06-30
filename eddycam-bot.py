import logging
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
import sftpcrawler

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

with open('adsb.txt') as f:
    dump1090_url = f.readline().strip()

last_env_request_time = 0
last_history_request_time = 0
last_animation_request_time = 0
last_bonkmessage_time = 0
last_history_request = ""
env_cache = ""
aircraft_button_row_size = 3

def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text  # or whatever

def to_input_media_photo(url):
    image_request = requests.get(url)
    return InputMediaPhoto(media=bytes(image_request.content))

def grouper(n, iterable, fillvalue=None):
    "grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=fillvalue, *args)

def group_buttons(row_size, buttons):
    matrix = list(grouper(row_size, buttons))
    matrix = [[inner for inner in outer if inner is not None] for outer in matrix] # remove any Nones and convert to list
    return matrix

def create_aircraft_inlinebuttons(sorted_ac):
    buttons = [InlineKeyboardButton(ac.ident.strip(), callback_data=f"adsb_{ac.hex}") for ac in sorted_ac]
    return group_buttons(aircraft_button_row_size, buttons)

async def adsb_summary(update: Update, context: CallbackContext.DEFAULT_TYPE):
    aircraft = parse1090.parse_aircraft(dump1090_url)
    output = f"EddyRadio can currently see *{len(aircraft)}* transponders, of which *{len(parse1090.in_sky(aircraft))}* are in the air and *{len(parse1090.with_ident(aircraft))}* have a valid ident"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=output, parse_mode=ParseMode.MARKDOWN)

async def adsb_list(update: Update, context: CallbackContext.DEFAULT_TYPE):
    show_ground = (len(context.args) > 0 and context.args[0] == "ground")
    aircraft = parse1090.parse_aircraft(dump1090_url)
    filtered_aircraft = parse1090.with_ident(aircraft, True) if show_ground else parse1090.in_sky_and_ident(aircraft)
    filtered_aircraft.sort(key=lambda ac: ac.rssi, reverse=True)
    output = f"*Listing {len(filtered_aircraft)} aircraft in the air and with idents*\n"
    filtered_aircraft_text = [f"{ac.ident.strip()} at {str(ac.alt_baro).replace('ground', 'Ground / 0')}ft, {ac.rssi} dBm" for ac in filtered_aircraft]
    output = output + "\n".join(filtered_aircraft_text)
    keyboard = InlineKeyboardMarkup(create_aircraft_inlinebuttons(filtered_aircraft))
    await context.bot.send_message(chat_id=update.effective_chat.id, text=output, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def adsb_info_update(update: Update, context: CallbackContext.DEFAULT_TYPE):
    query = update.callback_query
    hex = remove_prefix(query.data, "adsb_")
    logging.info("Getting data for "+hex)
    aircraft = parse1090.parse_aircraft(dump1090_url)
    target_list = list(filter(lambda ac: (ac.hex == hex), aircraft))
    buttons = [[ InlineKeyboardButton("Refresh", callback_data=query.data) ]]
    if not target_list:
        await query.edit_message_text(text="Couldn't find the aircraft anymore :(")
        return
    target = target_list[0]
    if not (target.ident and target.ident.strip() and target.alt_baro):
        await query.edit_message_text(text="Detected, but not enough signal to decode anymore :(", reply_markup=InlineKeyboardMarkup(buttons))
        return
    squawk = target.squawk or "Unknown"
    gs = target.gs or "Unknown"
    heading = target.track or "Unknown"
    lat = format(target.lat, '.4f') if target.lat else "Unknown"
    lon = format(target.lon, '.4f') if target.lat else "Unknown"
    alt = str(target.alt_baro).replace("ground", "Ground / 0")
    output = f"*Ident:* {target.ident.strip()}\n*Altitude (barometric):* {alt}ft\n*Ground Speed:* {gs}kt\n*Squawk:* {squawk}\n*Heading:* {heading}°\n*Position:* {lat}°N, {lon}°E\n*Signal Strength:* {target.rssi} dBm\n[Find on FlightAware](https://flightaware.com/live/modes/{target.hex}/ident/{target.ident.strip()}/redirect)"
    if (target.lat and target.lon):
        buttons[0].append(InlineKeyboardButton("Map", callback_data=f"map_{lat}_{lon}"))
    keyboard = InlineKeyboardMarkup(buttons)
    await query.answer()
    await query.edit_message_text(text=output, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

async def adsb_map(update: Update, context: CallbackContext.DEFAULT_TYPE):
    query = update.callback_query
    latlon = remove_prefix(query.data, "map_").split("_", 1) # 0 is lat, 1 is lon
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

async def camera_history(update: Update, context: CallbackContext.DEFAULT_TYPE):
    try:
        camera_index = int(context.args[0]) if len(context.args) > 0 else 0
    except ValueError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Expected int or blank")
        return
    if (camera_index < 0 or camera_index >= sftpcrawler.num_cameras()):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Invalid camera ID")
        return
    days = sftpcrawler.list_days(camera_index)
    buttons = [InlineKeyboardButton(day[0], callback_data=f"cameralog_{day[1]}") for day in days[:14]]
    buttons_matrix = group_buttons(2, buttons)
    keyboard = InlineKeyboardMarkup(buttons_matrix)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Avaliable Dates for Camera {camera_index}", reply_markup=keyboard)

async def camera_history_browser(update: Update, context: CallbackContext.DEFAULT_TYPE):
    global last_history_request_time
    global last_history_request
    global last_bonkmessage_time
    global last_animation_request_time
    if (last_history_request_time > int(time.time()) - 5):
        if (last_bonkmessage_time < int(time.time() - 30)):
            last_bonkmessage_time = int(time.time())
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ratelimited - culprit is {update.effective_user.first_name} (id {update.effective_user.id})")
        return
    query = update.callback_query
    if (query.data == last_history_request):
        logging.warning("Ignored duplicate request")
        return
    last_history_request = query.data
    data = remove_prefix(query.data, "cameralog_").split("@")
    folder = data[0]
    image_id_requested = int(data[1]) if len(data) > 1 else None
    second_image_id_requested = int(data[2]) if len(data) > 2 else None
    cache_path = os.path.join(sys.argv[1], 'history.jpg')
    last_history_request_time = int(time.time())
    if not second_image_id_requested:
        # Regular request
        (id, max_id) = sftpcrawler.get_image(folder, cache_path, image_id_requested)
        # Build up allowed nav buttons
        minor_nav = []
        if (id >= 3):
            minor_nav.append(InlineKeyboardButton("<15m", callback_data=f"cameralog_{folder}@{id - 3}"))
        if (id >= 1):
            minor_nav.append(InlineKeyboardButton("<5m", callback_data=f"cameralog_{folder}@{id - 1}"))
        if (id <= max_id - 1):
            minor_nav.append(InlineKeyboardButton(">5m", callback_data=f"cameralog_{folder}@{id + 1}"))
        if (id <= max_id - 3):
            minor_nav.append(InlineKeyboardButton(">15m", callback_data=f"cameralog_{folder}@{id + 3}"))
        major_nav = []
        if (id >= 48):
            major_nav.append(InlineKeyboardButton("<<4h", callback_data=f"cameralog_{folder}@{id - 48}"))
        if (id >= 12):
            major_nav.append(InlineKeyboardButton("<<1h", callback_data=f"cameralog_{folder}@{id - 12}"))
        if (id <= max_id - 12):
            major_nav.append(InlineKeyboardButton(">>1h", callback_data=f"cameralog_{folder}@{id + 12}"))
        if (id <= max_id - 48):
            major_nav.append(InlineKeyboardButton(">>4h", callback_data=f"cameralog_{folder}@{id + 48}"))
        aux_nav = []
        if (id >= 36):
            aux_nav.append(InlineKeyboardButton("🎞️ -3h", callback_data=f"cameralog_{folder}@{id - 36}@{id}"))
        if (id <= max_id - 36):
            aux_nav.append(InlineKeyboardButton("🎞️ +3h", callback_data=f"cameralog_{folder}@{id}@{id + 36}"))
        aux_nav.append(InlineKeyboardButton("Save", callback_data=f"cameralog_{folder}@{id}@{id}"))
        keyboard = InlineKeyboardMarkup([minor_nav, major_nav, aux_nav])
        await query.answer()
        if (image_id_requested == None):
            # Fresh message
            await query.edit_message_text(text=f"Selected {folder}")
            await context.bot.send_photo(update.effective_chat.id, photo=open(cache_path, "rb"), reply_markup=keyboard)
        else:
            # Edit existing message
            photo_to_send = InputMediaPhoto(media=open(cache_path, "rb"))
            await query.edit_message_media(media=photo_to_send, reply_markup=keyboard)
    else:
        # Freeze or Animation request
        if second_image_id_requested == image_id_requested:
            # freeze by removing buttons
            if query.message.photo:
                old_image = query.message.photo[0].file_id
                await query.answer()
                await query.edit_message_media(media=InputMediaPhoto(old_image)) # no markup
                return
            else:
                return # message too old, ah well
        else:
            # animate!
            if (last_animation_request_time > int(time.time()) - 30):
                if (last_bonkmessage_time < int(time.time() - 10)):
                    last_bonkmessage_time = int(time.time())
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Animation is on cooldown - called by {update.effective_user.first_name} (id {update.effective_user.id})")
                return
            last_animation_request_time = int(time.time())
            animation_cache_path = os.path.join(sys.argv[1], 'camhistory')
            if (os.path.isdir(animation_cache_path)):
                # Clear out the directory
                for file in os.listdir(animation_cache_path):
                    os.unlink(os.path.join(animation_cache_path, file))
            else:
                os.mkdir(animation_cache_path)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Producing animation requested by {update.effective_user.first_name}...")
            await query.answer()
            sftpcrawler.get_images(folder, animation_cache_path, image_id_requested, second_image_id_requested)
            animation_video_cache = os.path.join(sys.argv[1], 'animation_cache_recording.mp4')
            os.system(f'ffmpeg -y -framerate 8 -pattern_type glob -i "{animation_cache_path}/*.jpg"  -s:v 1280x720 -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p {animation_video_cache}')
            await context.bot.send_animation(update.effective_chat.id, open(animation_video_cache, "rb"), write_timeout=30)

async def button_handler(update: Update, context: CallbackContext.DEFAULT_TYPE):
    query = update.callback_query
    if (query.data.startswith("adsb_")):
        await adsb_info_update(update, context)
    if (query.data.startswith("map_")):
        await adsb_map(update, context)
    if (query.data.startswith("cameralog_")):
        await camera_history_browser(update, context)

if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()

    chat_filter = filters.Chat(chat_id=allowed_chats)

    application.add_handler(CommandHandler('camera_history', camera_history, filters=chat_filter))
    application.add_handler(CommandHandler('neko', neko))
    application.add_handler(CommandHandler('snapshot', snapshot, filters=chat_filter))
    application.add_handler(CommandHandler('clip', clip, filters=chat_filter))
    application.add_handler(CommandHandler('environment', environment, filters=chat_filter))
    application.add_handler(CommandHandler('adsb_list', adsb_list, filters=chat_filter))
    application.add_handler(CommandHandler('adsb_summary', adsb_summary, filters=chat_filter))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling()
