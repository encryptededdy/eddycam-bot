import logging
import requests
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CallbackContext, CommandHandler
import os
import sys

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

def to_input_media_photo(url):
    image_request = requests.get(url)
    return InputMediaPhoto(media = bytes(image_request.content))


async def neko(update: Update, context: CallbackContext.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="nyaa~")


async def snapshot(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if (update.effective_chat.id not in allowed_chats):
        print("Declined snapshot request from chat " + str(update.effective_chat.id))
        print(allowed_chats)
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="b...baka! You're not allowed to see my photos!")
        return
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
        await context.bot.send_photo(update.effective_chat.id, bytes(image_request.content), caption="here's your picture uwu")


async def clip(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if (update.effective_chat.id not in allowed_chats):
        print("Declined clip request from chat " + str(update.effective_chat.id))
        print(allowed_chats)
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="b...baka! You're not allowed to see my videos!")
        return
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

    neko_handler = CommandHandler('neko', neko)
    snapshot_handler = CommandHandler('snapshot', snapshot)
    clip_handler = CommandHandler('clip', clip)
    application.add_handler(neko_handler)
    application.add_handler(snapshot_handler)
    application.add_handler(clip_handler)

    application.run_polling()
