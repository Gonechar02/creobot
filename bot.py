import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Константы ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 547448838
SPREADSHEET_ID = '1NIiG7JZPabqAYz9GB45iP8KVbfkF_EhiutnzRDeKEGI'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Google Sheets ===
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ['GOOGLE_CREDS_JSON']), scope)
client = gspread.authorize(creds)

users_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Users")
transactions_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Transactions")

# === Меню ===
def main_menu_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Проверить заявки", callback_data='check_requests')],
        [InlineKeyboardButton("Баланс пользователей", callback_data='all_balances')],
        [InlineKeyboardButton("Общий долг", callback_data='total_debt')]
    ])

def main_menu_user():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Баланс", callback_data='check_balance')]
    ])

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = users_sheet.col_values(1)

    if user_id not in users:
        full_name = update.effective_user.full_name
        users_sheet.append_row([user_id, full_name, 0])

    if int(user_id) == ADMIN_ID:
        await update.message.reply_text("✅ Вы админ!", reply_markup=main_menu_admin())
    else:
        await update.message.reply_text("Добро пожаловать!", reply_markup=main_menu_user())

# === Обработка кнопок ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    if int(user_id) == ADMIN_ID:
        if query.data == 'check_requests':
            records = transactions_sheet.get_all_records()
            if not records:
                await query.edit_message_text("❌ Заявок нет.", reply_markup=main_menu_admin())
            else:
                text = "\n".join(
                    f"UserID: {r['UserID']}, Просмотры: {r['ViewsCount']}, Оплата: {r['Payment']} BYN"
                    for r in records[-5:]
                )
                await query.edit_message_text(f"📄 Последние заявки:\n{text}", reply_markup=main_menu_admin())

        elif query.data == 'all_balances':
            records = users_sheet.get_all_records()
            if not records:
                await query.edit_message_text("❌ Нет пользователей для отображения баланса.", reply_markup=main_menu_admin())
            else:
                text = "\n".join(
                    f"{r['Full Name']} ({r['UserID']}): {r['Balance']} BYN"
                    for r in records
                )
                await query.edit_message_text(f"💰 Балансы:\n{text}", reply_markup=main_menu_admin())

        elif query.data == 'total_debt':
            payments = transactions_sheet.col_values(3)[1:]  # без заголовка
            if not payments:
                await query.edit_message_text("✅ Долгов нет.", reply_markup=main_menu_admin())
            else:
                total = sum(float(p) for p in payments if p.strip())
                await query.edit_message_text(f"💸 Общий долг: {total} BYN", reply_markup=main_menu_admin())

    else:
        if query.data == 'check_balance':
            records = users_sheet.get_all_records()
            user_data = next((r for r in records if str(r['UserID']) == user_id), None)
            balance = user_data['Balance'] if user_data else 0
            await query.edit_message_text(f"Ваш баланс: {balance} BYN", reply_markup=main_menu_user())

# === Запуск ===
async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    await app.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
