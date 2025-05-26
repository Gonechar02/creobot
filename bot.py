import os
import json
import logging
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

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ['GOOGLE_CREDS_JSON']), scope)
client = gspread.authorize(creds)

PLATFORM_KPI = {
    'YouTube Shorts': {'step': 7500, 'rate': 1},
    'TikTok': {'step': 7500, 'rate': 1},
    'Instagram': {'step': 5000, 'rate': 1},
}

(START, AWAIT_NAME) = range(2)

def main_menu_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Проверить заявки", callback_data='check_requests')],
        [InlineKeyboardButton("📅 Баланс пользователей", callback_data='all_balances')],
        [InlineKeyboardButton("💸 Общий долг", callback_data='total_debt')]
    ])

def main_menu_user():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("💳 Баланс", callback_data='check_balance')]
    ])

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
            data = sheet.get_all_records()
            if not data:
                await query.edit_message_text("❌ Заявок нет.", reply_markup=main_menu_admin())
            else:
                text = "\n\n".join([f"{row['Платформа']} - {row['Ссылка']} - {row['Просмотры']} - {row['Сумма']} BYN" for row in data[-5:]])
                await query.edit_message_text(f"Последние заявки:\n{text}", reply_markup=main_menu_admin())

        elif query.data == 'all_balances':
            users_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
            data = users_sheet.get_all_records()
            if not data:
                await query.edit_message_text("❌ Пользователей нет.", reply_markup=main_menu_admin())
            else:
                text = "\n".join([f"{row['FullName']} ({row['UserID']}): {row['Balance']} BYN" for row in data])
                await query.edit_message_text(f"Балансы:\n{text}", reply_markup=main_menu_admin())

        elif query.data == 'total_debt':
            users_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
            balances = users_sheet.col_values(3)[1:]
            if not balances:
                await query.edit_message_text("❌ Долгов нет.", reply_markup=main_menu_admin())
            else:
                total = sum(float(b) for b in balances)
                await query.edit_message_text(f"💸 Общий долг по выплатам: {total} BYN", reply_markup=main_menu_admin())

        return START

    if query.data == 'add_video':
        await query.edit_message_text("📅 Добавление видео пока недоступно.", reply_markup=main_menu_user())
        return START

    elif query.data == 'check_balance':
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
        records = sheet.get_all_records()
        record = next((r for r in records if str(r['UserID']) == user_id), None)
        if not record:
            await query.edit_message_text("Пользователь не найден.", reply_markup=main_menu_user())
        else:
            balance = record['Balance']
            await query.edit_message_text(f"💳 Ваш баланс: {balance} BYN", reply_markup=main_menu_user())
        return START

async def main():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AWAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
        },
        fallbacks=[]
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_handler))

    await application.initialize()
    await application.start()
    await application.updater.start_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=f"https://creobot.onrender.com/{TOKEN}"
    )
    await application.updater.idle()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
