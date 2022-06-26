import logging
import requests
from telegram import Update, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CallbackContext, CommandHandler, filters
from qingping import qingping
import os
import sys
import time

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

last_env_request_time = 0

def to_input_media_photo(url):
    image_request = requests.get(url)
    return InputMediaPhoto(media = bytes(image_request.content))

async def environment(update: Update, context: CallbackContext.DEFAULT_TYPE):
    global last_env_request_time
    time_until_limit = last_env_request_time + 120 - int(time.time())
    if time_until_limit > 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ratelimit, try again in {time_until_limit}s")
        return
    result = list(qingping.get_device_info().items())[0][1]
    pretty = "*Environment in Eddy's Room (15min res)*\n" + qingping.airquality_pretty(result, True)
    last_env_request_time = int(time.time())
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


if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()

    filter = filters.Chat(chat_id=allowed_chats)

    environment_handler = CommandHandler('environment', environment, filters=filter)
    neko_handler = CommandHandler('neko', neko)
    snapshot_handler = CommandHandler('snapshot', snapshot, filters=filter)
    clip_handler = CommandHandler('clip', clip, filters=filter)
    application.add_handler(neko_handler)
    application.add_handler(snapshot_handler)
    application.add_handler(clip_handler)
    application.add_handler(environment_handler)

    application.run_polling()
