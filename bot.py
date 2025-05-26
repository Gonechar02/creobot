import os
import json
import logging
import threading
from flask import Flask, request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === НАСТРОЙКИ ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 547448838
SPREADSHEET_ID = "1NIiG7JZPabqAYz9GB45iP8KVbfkF_EhiutnzRDeKEGI"

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === GOOGLE SHEETS ===
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ['GOOGLE_CREDS_JSON']), scope)
client = gspread.authorize(creds)
users_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
videos_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Videos")

# === СОСТОЯНИЯ ===
(START, AWAIT_NAME) = range(2)

# === КНОПКИ ===
def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Проверить заявки", callback_data='check_requests')],
        [InlineKeyboardButton("💳 Балансы", callback_data='all_balances')],
        [InlineKeyboardButton("💸 Общий долг", callback_data='total_debt')],
    ])

def user_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Баланс", callback_data='check_balance')],
    ])

# === ОБРАБОТЧИК /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = users_sheet.col_values(1)

    if user_id == str(ADMIN_ID):
        if user_id not in users:
            users_sheet.append_row([user_id, 'ADMIN', 0])
        await update.message.reply_text("✅ Вы админ!", reply_markup=admin_menu())
        return START

    if user_id not in users:
        await update.message.reply_text("Введите имя и фамилию:")
        return AWAIT_NAME

    await update.message.reply_text("Выберите действие:", reply_markup=user_menu())
    return START

# === РЕГИСТРАЦИЯ ИМЕНИ ===
async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    name = update.message.text.strip()
    users_sheet.append_row([user_id, name, 0])
    await update.message.reply_text(f"✅ Спасибо, {name}!", reply_markup=user_menu())
    return START

# === ОБРАБОТЧИК КНОПОК ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    if user_id == str(ADMIN_ID):
        if query.data == 'check_requests':
            records = videos_sheet.get_all_records()
            if not records:
                await query.edit_message_text("📅 Заявок нет.", reply_markup=admin_menu())
            else:
                latest = records[-5:]
                text = "\n\n".join([f"{r['Платформа']} | {r['Ссылка']} | {r['Просмотры']} | {r['Сумма']} BYN" for r in latest])
                await query.edit_message_text(f"Последние заявки:\n{text}", reply_markup=admin_menu())

        elif query.data == 'all_balances':
            data = users_sheet.get_all_records()
            if not data:
                await query.edit_message_text("🧑 Пользователей нет.", reply_markup=admin_menu())
            else:
                balances = "\n".join([f"{r['FullName']} — {r['Balance']} BYN" for r in data])
                await query.edit_message_text(f"Балансы:\n{balances}", reply_markup=admin_menu())

        elif query.data == 'total_debt':
            values = users_sheet.col_values(3)[1:]
            if not values:
                await query.edit_message_text("💸 Долгов нет.", reply_markup=admin_menu())
            else:
                total = sum(float(v or 0) for v in values)
                await query.edit_message_text(f"💸 Общий долг: {total} BYN", reply_markup=admin_menu())
        return START

    if query.data == 'check_balance':
        users = users_sheet.get_all_records()
        user = next((u for u in users if str(u['UserID']) == user_id), None)
        if user:
            await query.edit_message_text(f"💳 Ваш баланс: {user['Balance']} BYN", reply_markup=user_menu())
        else:
            await query.edit_message_text("❌ Вы не зарегистрированы.")
        return START

# === FLASK и ВЕБХУК ===
flask_app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

@flask_app.route('/')
def root():
    return 'Bot is alive.'

@flask_app.route(f'/{TOKEN}', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return 'ok'

def flask_thread():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# === ЗАПУСК ===
async def run():
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={AWAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)]},
        fallbacks=[]
    )
    application.add_handler(conv)
    application.add_handler(CallbackQueryHandler(handle_buttons))

    await application.initialize()
    await application.start()
    threading.Thread(target=flask_thread).start()

if __name__ == '__main__':
    import asyncio
    asyncio.run(run())
