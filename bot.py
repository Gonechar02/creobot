# bot.py (обновлённый)
import logging
import os
import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ['GOOGLE_CREDS_JSON']), scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = '1NIiG7JZPabqAYz9GB45iP8KVbfkF_EhiutnzRDeKEGI'
ADMIN_ID = 547448838

(START, AWAIT_NAME, SELECT_PLATFORM, AWAIT_LINK, AWAIT_VIEWS, CONFIRM) = range(6)
user_state = {}

PLATFORM_KPI = {
    'YouTube Shorts': {'step': 7500, 'rate': 1},
    'TikTok': {'step': 7500, 'rate': 1},
    'Instagram': {'step': 5000, 'rate': 1},
}


def start(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
    users = sheet.col_values(1)

    if user_id not in users:
        update.message.reply_text("Добро пожаловать! Введите ваше имя и фамилию для регистрации:")
        return AWAIT_NAME
    else:
        update.message.reply_text("Выберите действие:", reply_markup=main_menu())
        return START


def handle_name(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    full_name = update.message.text.strip()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
    sheet.append_row([user_id, full_name, 0])
    update.message.reply_text(f"Спасибо, {full_name}! Вы зарегистрированы.", reply_markup=main_menu())
    return START


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("Баланс", callback_data='check_balance')]
    ])


def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    if query.data == 'add_video':
        user_state[user_id] = {}
        query.edit_message_text("Выберите платформу:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("YouTube Shorts", callback_data='plat_YT')],
            [InlineKeyboardButton("TikTok", callback_data='plat_TT')],
            [InlineKeyboardButton("Instagram", callback_data='plat_IG')]
        ]))
        return SELECT_PLATFORM

    elif query.data == 'check_balance':
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        records = sheet.get_all_records()
        record = next((r for r in records if r['UserID'] == str(user_id)), None)
        balance = record['Balance'] if record else 0
        query.edit_message_text(f"Ваш баланс: {balance:.2f} BYN", reply_markup=main_menu())
        return START

    return START


def select_platform(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    platform_map = {'plat_YT': 'YouTube Shorts', 'plat_TT': 'TikTok', 'plat_IG': 'Instagram'}
    platform = platform_map.get(query.data)
    user_state[user_id]['platform'] = platform
    query.edit_message_text("Отправьте ссылку на видео:")
    return AWAIT_LINK


def handle_link(update: Update, context: CallbackContext):
    link = update.message.text.strip()
    user_id = str(update.effective_user.id)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Videos")
    links = sheet.col_values(3)

    if link in links:
        update.message.reply_text("Вы уже добавляли эту ссылку.")
        return START

    user_state[update.effective_user.id]['link'] = link
    update.message.reply_text("Введите точное количество просмотров:")
    return AWAIT_VIEWS


def handle_views(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        views = int(update.message.text.strip())
    except ValueError:
        update.message.reply_text("Введите число просмотров цифрами.")
        return AWAIT_VIEWS

    data = user_state.get(user_id, {})
    platform = data.get('platform')
    link = data.get('link')

    if not platform or not link:
        update.message.reply_text("Произошла ошибка. Попробуйте заново.")
        return START

    kpi = PLATFORM_KPI[platform]
    if views < 15000:
        update.message.reply_text("У вас недостаточно просмотров для KPI.")
        return START

    units = views // kpi['step']
    payment = units * kpi['rate']
    user_state[user_id]['views'] = views
    user_state[user_id]['payment'] = payment

    # отправляем админу на проверку
    context.bot.send_message(
        ADMIN_ID,
        f"Заявка от @{update.effective_user.username or user_id}\nПлатформа: {platform}\nСсылка: {link}\nПросмотры: {views}\nKPI: {'ДА' if units else 'НЕТ'}\nНачисление: {payment} BYN"
    )

    update.message.reply_text(f"Заявка отправлена на проверку. Возможная выплата: {payment} BYN")
    
    # сохраняем в таблицу
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Videos")
    sheet.append_row([str(user_id), platform, link, views, 'YES' if units else 'NO', payment, str(datetime.now().date())])

    # обновляем баланс
    if units:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        users = sheet.get_all_records()
        for i, u in enumerate(users, start=2):
            if u['UserID'] == str(user_id):
                new_balance = float(u['Balance']) + payment
                sheet.update_cell(i, 3, new_balance)
                break

    return START


def error_handler(update: Update, context: CallbackContext):
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    if update and update.effective_message:
        update.effective_message.reply_text("Произошла ошибка. Попробуйте позже.")


def main():
    updater = Updater("7600973416:AAF4p1J96D2At_9fQHKTPNZ3CS4vc_mb39s")
    dp = updater.dispatcher

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

    dp.add_handler(conv_handler)
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
