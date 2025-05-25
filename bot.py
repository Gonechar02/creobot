import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройки Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = '1NIiG7JZPabqAYz9GB45iP8KVbfkF_EhiutnzRDeKEGI'
ADMIN_ID = '547448838'  # Telegram ID администратора

START, AWAIT_NAME = range(2)

def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("Мой баланс", callback_data='check_balance')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton("📋 Все заявки", callback_data='admin_view_requests')],
        [InlineKeyboardButton("💰 Балансы пользователей", callback_data='admin_balances')]
    ]
    return InlineKeyboardMarkup(keyboard)

def start(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id

    if str(user_id) == ADMIN_ID:
        update.message.reply_text("👑 Привет, Администратор! Выберите действие:", reply_markup=get_admin_menu())
        return START

    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        records = sheet.get_all_records()
        user_registered = any(record['UserID'] == str(user_id) for record in records)
        if user_registered:
            update.message.reply_text("Выберите действие:", reply_markup=get_main_menu_keyboard())
            return START
        else:
            update.message.reply_text("Введите ваше имя и фамилию:")
            return AWAIT_NAME
    except Exception as e:
        logger.error(f"Ошибка при проверке регистрации: {e}")
        update.message.reply_text("Ошибка. Попробуйте позже.")
        return START

def handle_name(update: Update, context: CallbackContext) -> int:
    full_name = update.message.text.strip()
    user_id = update.effective_user.id
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        sheet.append_row([str(user_id), full_name, 0])
        update.message.reply_text(f"Спасибо, {full_name}! Вы зарегистрированы.", reply_markup=get_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")
        update.message.reply_text("Ошибка при регистрации.")
    return START

def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Ошибка обработки запроса:", exc_info=context.error)
    if update and update.effective_message:
        update.effective_message.reply_text("Произошла ошибка. Попробуйте позже.")

def main() -> None:
    updater = Updater("7600973416:AAF4p1J96D2At_9fQHKTPNZ3CS4vc_mb39s")
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_name), group=AWAIT_NAME)
    dp.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
