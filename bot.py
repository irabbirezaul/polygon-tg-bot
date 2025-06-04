import os
import json
import requests
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime

# Get tokens from environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
POLYGONSCAN_API_KEY = os.getenv("POLYGONSCAN_API_KEY")

# Store last transaction hashes per user/address to avoid duplicate alerts
last_tx_hashes = {}

# Load user addresses from file
def load_addresses():
    try:
        with open('addresses.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Save user addresses to file
def save_addresses(addresses):
    with open('addresses.json', 'w') as f:
        json.dump(addresses, f)

# /start command handler
async def start(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Hello {update.effective_user.first_name}! 👋\n\n"
        "Send me your Polygon address using:\n"
        "/setaddress 0xYourPolygonAddress\n\n"
        "I will notify you about your address's transactions."
    )

# /setaddress command handler
async def set_address(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    args = context.args

    if not args:
        await update.message.reply_text("❌ Please provide a Polygon address.\nUsage: /setaddress 0xYourPolygonAddress")
        return

    address = args[0].lower()
    if not address.startswith("0x") or len(address) != 42:
        await update.message.reply_text("❌ That doesn't look like a valid Polygon address.")
        return

    addresses = load_addresses()
    addresses[chat_id] = address
    save_addresses(addresses)

    await update.message.reply_text(f"✅ Polygon address set to:\n`{address}`\n\nI will start tracking it for you.", parse_mode="Markdown")

# /listaddresses command handler
async def list_addresses(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    addresses = load_addresses()
    if not addresses:
        await update.message.reply_text("📭 No addresses are being tracked yet.")
        return

    message = "📄 *Tracked Polygon Addresses:*\n\n"
    for chat_id, address in addresses.items():
        message += f"👤 `{chat_id}` ➝ `{address}`\n"
    await update.message.reply_text(message, parse_mode="Markdown")

# Periodic task to check transactions for all users
async def check_transactions(context: ContextTypes.DEFAULT_TYPE):
    addresses = load_addresses()

    for chat_id, address in addresses.items():
        url = (
            f"https://api.polygonscan.com/api"
            f"?module=account&action=txlist&address={address}"
            f"&sort=desc&apikey={POLYGONSCAN_API_KEY}"
        )
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
        except Exception as e:
            print(f"Error fetching txs for {address}: {e}")
            continue

        if data.get('status') == '1' and data.get('result'):
            txs = data['result']
            latest_tx = txs[0]
            key = f"{chat_id}_{address}"

            if latest_tx['hash'] != last_tx_hashes.get(key):
                last_tx_hashes[key] = latest_tx['hash']

                direction = "📥 Incoming" if latest_tx['to'].lower() == address else "📤 Outgoing"
                value_matic = int(latest_tx['value']) / 1e18
                timestamp = datetime.utcfromtimestamp(int(latest_tx['timeStamp'])).strftime('%Y-%m-%d %H:%M:%S UTC')

                message = (
                    f"🔔 *New Polygon Transaction Detected!*\n\n"
                    f"🔗 [Tx Hash](https://polygonscan.com/tx/{latest_tx['hash']})\n"
                    f"{direction}\n"
                    f"💰 Amount: {value_matic:.4f} MATIC\n"
                    f"⏰ Time: {timestamp}"
                )

                try:
                    await context.bot.send_message(chat_id=int(chat_id), text=message, parse_mode="Markdown")
                except Exception as e:
                    print(f"Error sending message to {chat_id}: {e}")

# Main function to run the bot
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setaddress", set_address))
    application.add_handler(CommandHandler("listaddresses", list_addresses))

    # Check transactions every 15 seconds
    application.job_queue.run_repeating(check_transactions, interval=15, first=5)

    application.run_polling()

if __name__ == '__main__':
    main()
