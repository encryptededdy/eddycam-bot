import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackContext, CommandHandler
import os
import sys

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

with open('imageurl.txt') as f:
    imageurl = f.readline().strip()

with open('rtspurl.txt') as f:
    rtspurl = f.readline().strip()

with open('key.txt') as f:
    token = f.readline().strip()

def process_chat_id(line):
    return int(line.strip())

with open('allowedchatid.txt') as f:
    allowed_chats = list(map(process_chat_id, f.readlines()))

async def neko(update: Update, context: CallbackContext.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="nyaa~")

async def snapshot(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if (update.effective_chat.id not in allowed_chats):
        print("Declined snapshot request from chat " + str(update.effective_chat.id))
        print(allowed_chats)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="b...baka! You're not allowed to see my photos!")
        return
    image_request = requests.get(imageurl, stream=True)
    image_request.raw.decode_content = True
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Sure thing, senpai! Let me take a picture now!")
    await context.bot.send_photo(update.effective_chat.id, image_request.raw, caption="here's your picture uwu")

async def clip(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if (update.effective_chat.id not in allowed_chats):
        print("Declined clip request from chat " + str(update.effective_chat.id))
        print(allowed_chats)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="b...baka! You're not allowed to see my videos!")
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'll record a 10s clip for you!...")
    path = os.path.join(sys.argv[1], 'rtsp_cache_recording.mp4')
    os.system(f'ffmpeg -y -i "{rtspurl}" -c copy -t 10 {path}')
    await context.bot.send_video(update.effective_chat.id, open(path, "rb"), caption="here's your clip ^w^", write_timeout=60)

if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()
    
    neko_handler = CommandHandler('neko', neko)
    snapshot_handler = CommandHandler('snapshot', snapshot)
    clip_handler = CommandHandler('clip', clip)
    application.add_handler(neko_handler)
    application.add_handler(snapshot_handler)
    application.add_handler(clip_handler)
    
    application.run_polling()