import os
import json
import logging
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, CallbackContext

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets авторизация
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ['GOOGLE_CREDS_JSON']), scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = '1NIiG7JZPabqAYz9GB45iP8KVbfkF_EhiutnzRDeKEGI'
ADMIN_ID = 547448838

# Состояния
(START, AWAIT_NAME, SELECT_PLATFORM, AWAIT_LINK, AWAIT_VIEWS) = range(5)
user_state = {}

PLATFORM_KPI = {
    'YouTube Shorts': {'step': 7500, 'rate': 1},
    'TikTok': {'step': 7500, 'rate': 1},
    'Instagram': {'step': 5000, 'rate': 1},
}

# Telegram
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot, None, workers=4, use_context=True)

# Главное меню
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("Баланс", callback_data='check_balance')]
    ])

# Команда /start
def start(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
    users = sheet.col_values(1)

    if int(user_id) != ADMIN_ID:
        logger.info(f"Обычный пользователь: {user_id}")
    else:
        logger.info("Запущено админом")

    if user_id not in users:
        update.message.reply_text("Введите имя и фамилию для регистрации:")
        return AWAIT_NAME
    else:
        update.message.reply_text("Выберите действие:", reply_markup=main_menu())
        return START

# Обработка имени
def handle_name(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    full_name = update.message.text.strip()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
    sheet.append_row([user_id, full_name, 0])
    update.message.reply_text(f"Спасибо, {full_name}! Вы зарегистрированы.", reply_markup=main_menu())
    return START

# Обработка кнопок
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()

    if query.data == 'add_video':
        user_state[user_id] = {}
        query.edit_message_text("Выберите платформу:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("YouTube Shorts", callback_data='plat_YT')],
            [InlineKeyboardButton("TikTok", callback_data='plat_TT')],
            [InlineKeyboardButton("Instagram", callback_data='plat_IG')],
        ]))
        return SELECT_PLATFORM

    elif query.data == 'check_balance':
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        records = sheet.get_all_records()
        record = next((r for r in records if r['UserID'] == str(user_id)), None)
        balance = record['Balance'] if record else 0
        query.edit_message_text(f"Ваш баланс: {balance} BYN", reply_markup=main_menu())
        return START

# Выбор платформы
def select_platform(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()

    platform_map = {'plat_YT': 'YouTube Shorts', 'plat_TT': 'TikTok', 'plat_IG': 'Instagram'}
    platform = platform_map.get(query.data)
    user_state[user_id]['platform'] = platform
    query.edit_message_text("Отправьте ссылку на видео:")
    return AWAIT_LINK

# Ссылка на видео
def handle_link(update: Update, context: CallbackContext):
    link = update.message.text.strip()
    user_id = str(update.effective_user.id)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Videos")
    links = sheet.col_values(3)

    if link in links:
        update.message.reply_text("Вы уже добавляли эту ссылку.")
        return START

    user_state[update.effective_user.id]['link'] = link
    update.message.reply_text("Введите количество просмотров:")
    return AWAIT_VIEWS

# Просмотры
def handle_views(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        views = int(update.message.text.strip())
    except ValueError:
        update.message.reply_text("Введите число.")
        return AWAIT_VIEWS

    platform = user_state[user_id].get('platform')
    link = user_state[user_id].get('link')

    if not platform or not link:
        update.message.reply_text("Ошибка. Начните заново.")
        return START

    kpi = PLATFORM_KPI[platform]
    units = views // kpi['step']
    payment = units * kpi['rate']

    context.bot.send_message(ADMIN_ID, f"Заявка от @{update.effective_user.username}:\n"
                                       f"Платформа: {platform}\nСсылка: {link}\nПросмотры: {views}\n"
                                       f"KPI: {'ДА' if units else 'НЕТ'}\nСумма: {payment} BYN")

    update.message.reply_text(f"Заявка отправлена. Выплата: {payment} BYN")

    # Сохраняем в таблицу
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Videos")
    sheet.append_row([str(user_id), platform, link, views, 'YES' if units else 'NO', payment, str(datetime.now().date())])

    # Обновляем баланс
    if units:
        users_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        users = users_sheet.get_all_records()
        for i, u in enumerate(users, start=2):
            if u['UserID'] == str(user_id):
                new_balance = float(u['Balance']) + payment
                users_sheet.update_cell(i, 3, new_balance)
                break

    return START

# Webhook для Telegram
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

# Проверка
@app.route('/')
def index():
    return "Bot is running."

# Обработчики
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        AWAIT_NAME: [MessageHandler(Filters.text & ~Filters.command, handle_name)],
        SELECT_PLATFORM: [CallbackQueryHandler(select_platform, pattern='^plat_')],
        AWAIT_LINK: [MessageHandler(Filters.text & ~Filters.command, handle_link)],
        AWAIT_VIEWS: [MessageHandler(Filters.text & ~Filters.command, handle_views)],
    },
    fallbacks=[]
)

dispatcher.add_handler(conv_handler)
dispatcher.add_handler(CallbackQueryHandler(button_handler))

# Запуск
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 10000)))
