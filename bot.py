import os
import json
import logging
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# === Настройки ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 547448838

SPREADSHEET_ID = '1NIiG7JZPabqAYz9GB45iP8KVbfkF_EhiutnzRDeKEGI'

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ['GOOGLE_CREDS_JSON']), scope)
client = gspread.authorize(creds)

# === Состояния ===
(START, AWAIT_NAME, SELECT_PLATFORM, AWAIT_LINK, AWAIT_VIEWS) = range(5)
user_state = {}

PLATFORM_KPI = {
    'YouTube Shorts': {'step': 7500, 'rate': 1},
    'TikTok': {'step': 7500, 'rate': 1},
    'Instagram': {'step': 5000, 'rate': 1},
}

# === Flask + Webhook ===
flask_app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

@flask_app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return "ok"

@flask_app.route("/")
def index():
    return "Bot is running."

# === Меню ===
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("Баланс", callback_data='check_balance')]
    ])

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
    users = sheet.col_values(1)

    if int(user_id) == ADMIN_ID:
        await update.message.reply_text("✅ Вы админ!")
    else:
        await update.message.reply_text("👤 Вы обычный пользователь.")

    if user_id not in users:
        await update.message.reply_text("Введите имя и фамилию для регистрации:")
        return AWAIT_NAME
    else:
        await update.message.reply_text("Выберите действие:", reply_markup=main_menu())
        return START

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    full_name = update.message.text.strip()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
    sheet.append_row([user_id, full_name, 0])
    await update.message.reply_text(f"Спасибо, {full_name}! Вы зарегистрированы.", reply_markup=main_menu())
    return START

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

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
        record = next((r for r in records if str(r['UserID']) == str(user_id)), None)
        balance = record['Balance'] if record else 0
        await query.edit_message_text(f"Ваш баланс: {balance} BYN", reply_markup=main_menu())
        return START

async def select_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    platform_map = {'plat_YT': 'YouTube Shorts', 'plat_TT': 'TikTok', 'plat_IG': 'Instagram'}
    platform = platform_map.get(query.data)
    user_state[user_id]['platform'] = platform
    await query.edit_message_text("Отправьте ссылку на видео:")
    return AWAIT_LINK

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    user_id = str(update.effective_user.id)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Videos")
    links = sheet.col_values(3)

    if link in links:
        await update.message.reply_text("Вы уже добавляли эту ссылку.")
        return START

    user_state[update.effective_user.id]['link'] = link
    await update.message.reply_text("Введите количество просмотров:")
    return AWAIT_VIEWS

async def handle_views(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        views = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите число.")
        return AWAIT_VIEWS

    platform = user_state[user_id].get('platform')
    link = user_state[user_id].get('link')

    if not platform or not link:
        await update.message.reply_text("Ошибка. Начните заново.")
        return START

    kpi = PLATFORM_KPI[platform]
    units = views // kpi['step']
    payment = units * kpi['rate']

    await context.bot.send_message(ADMIN_ID, f"Заявка от @{update.effective_user.username}:\n"
                                             f"Платформа: {platform}\nСсылка: {link}\nПросмотры: {views}\n"
                                             f"KPI: {'ДА' if units else 'НЕТ'}\nСумма: {payment} BYN")

    await update.message.reply_text(f"Заявка отправлена. Выплата: {payment} BYN")

    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Videos")
    sheet.append_row([str(user_id), platform, link, views, 'YES' if units else 'NO', payment, str(datetime.now().date())])

    if units:
        users_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        users = users_sheet.get_all_records()
        for i, u in enumerate(users, start=2):
            if str(u['UserID']) == str(user_id):
                new_balance = float(u['Balance']) + payment
                users_sheet.update_cell(i, 3, new_balance)
                break

    return START

# === Обработчики ===
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        AWAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
        SELECT_PLATFORM: [CallbackQueryHandler(select_platform, pattern='^plat_')],
        AWAIT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)],
        AWAIT_VIEWS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_views)],
    },
    fallbacks=[]
)

application.add_handler(conv_handler)
application.add_handler(CallbackQueryHandler(button_handler))
