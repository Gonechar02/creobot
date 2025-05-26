import os
import json
import logging
import threading
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Настройки ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 547448838
SPREADSHEET_ID = '1NIiG7JZPabqAYz9GB45iP8KVbfkF_EhiutnzRDeKEGI'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets auth
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ['GOOGLE_CREDS_JSON']), scope)
client = gspread.authorize(creds)

PLATFORM_KPI = {
    'YouTube Shorts': {'step': 7500, 'rate': 1},
    'TikTok': {'step': 7500, 'rate': 1},
    'Instagram': {'step': 5000, 'rate': 1},
}

(START, AWAIT_NAME, SELECT_PLATFORM, AWAIT_LINK, AWAIT_VIEWS) = range(5)
user_state = {}

# === Flask App ===
flask_app = Flask(__name__)

# === Интерфейсы ===
def main_menu_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Проверить заявки", callback_data='check_requests')],
        [InlineKeyboardButton("Баланс пользователей", callback_data='all_balances')],
        [InlineKeyboardButton("Общий долг", callback_data='total_debt')]
    ])

def main_menu_user():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("Баланс", callback_data='check_balance')]
    ])

# === Хендлеры ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
    users = sheet.col_values(1)

    if int(user_id) == ADMIN_ID:
        if user_id not in users:
            sheet.append_row([user_id, 'ADMIN', 0])
        await update.message.reply_text("\u2705 Вы админ!", reply_markup=main_menu_admin())
        return START

    if user_id not in users:
        await update.message.reply_text("Введите имя и фамилию для регистрации:")
        return AWAIT_NAME
    else:
        await update.message.reply_text("Выберите действие:", reply_markup=main_menu_user())
        return START

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    full_name = update.message.text.strip()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
    sheet.append_row([user_id, full_name, 0])
    await update.message.reply_text(f"Спасибо, {full_name}! Вы зарегистрированы.", reply_markup=main_menu_user())
    return START

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    if user_id == str(ADMIN_ID):
        if query.data == 'check_requests':
            sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Videos")
            data = sheet.get_all_records()[-5:]
            text = "\n\n".join([f"{row['Платформа']} - {row['Ссылка']} - {row['Просмотры']} - {row['Сумма']} BYN" for row in data])
            await query.edit_message_text(f"Последние заявки:\n{text}", reply_markup=main_menu_admin())

        elif query.data == 'all_balances':
            users_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
            data = users_sheet.get_all_records()
            text = "\n".join([f"{row['FullName']} ({row['UserID']}): {row['Balance']} BYN" for row in data])
            await query.edit_message_text(f"Балансы:\n{text}", reply_markup=main_menu_admin())

        elif query.data == 'total_debt':
            users_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
            balances = users_sheet.col_values(3)[1:]
            total = sum(float(b) for b in balances)
            await query.edit_message_text(f"Общий долг по выплатам: {total} BYN", reply_markup=main_menu_admin())

        return START

    if query.data == 'add_video':
        user_state[user_id] = {}
        await query.edit_message_text("Выберите платформу:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("YouTube Shorts", callback_data='plat_YT')],
            [InlineKeyboardButton("TikTok", callback_data='plat_TT')],
            [InlineKeyboardButton("Instagram", callback_data='plat_IG')],
        ]))
        return SELECT_PLATFORM

    elif query.data == 'check_balance':
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        records = sheet.get_all_records()
        record = next((r for r in records if str(r['UserID']) == user_id), None)
        balance = record['Balance'] if record else 0
        await query.edit_message_text(f"Ваш баланс: {balance} BYN", reply_markup=main_menu_user())
        return START

# === Flask Webhook Endpoint ===
@flask_app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return "ok"

@flask_app.route("/")
def index():
    return "Bot is running."

# === Запуск ===
application = Application.builder().token(TOKEN).build()

async def setup_bot():
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AWAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            # другие состояния пока заглушки
        },
        fallbacks=[]
    )
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    await application.initialize()
    await application.start()

if __name__ == "__main__":
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))).start()
    import asyncio
    asyncio.run(setup_bot())
