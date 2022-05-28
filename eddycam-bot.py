import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackContext, CommandHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

with open('imageurl.txt') as f:
    imageurl = f.readline().strip()

with open('key.txt') as f:
    token = f.readline().strip()

with open('allowedchatid.txt') as f:
    allowed_chat = int(f.readline().strip())

async def neko(update: Update, context: CallbackContext.DEFAULT_TYPE):
    print(update.effective_chat.id)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="nyaa~")

async def snapshot(update: Update, context: CallbackContext.DEFAULT_TYPE):
    image_request = requests.get(imageurl, stream=True)
    image_request.raw.decode_content = True
    if (update.effective_chat.id == allowed_chat):
        print(update.effective_chat.id)
        print(allowed_chat)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sure thing, senpai! Let me take a picture now!")
        await context.bot.send_photo(update.effective_chat.id, image_request.raw, caption="here's your picture uwu")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="b...baka! You're not allowed to see my photos!")

if __name__ == '__main__':
    application = ApplicationBuilder().token(token).build()
    
    neko_handler = CommandHandler('neko', neko)
    snapshot_handler = CommandHandler('snapshot', snapshot)
    application.add_handler(neko_handler)
    application.add_handler(snapshot_handler)
    
    application.run_polling()