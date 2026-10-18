import os
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Token dari Telegram Father & Netlify Token
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NETLIFY_AUTH_TOKEN = os.getenv("NETLIFY_AUTH_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    chat_id = update.message.chat.id
    
    await update.message.reply_text("Sedang memproses dan membuat website kamu...")

    # Folder kerja untuk project web
    work_dir = f"./workspace_{chat_id}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        # 1. Panggil OpenCode CLI untuk generate web berdasarkan pesan Telegram
        cmd_opencode = f'opencode "{user_prompt}"'
        subprocess.run(cmd_opencode, shell=True, cwd=work_dir, check=True)

        await update.message.reply_text("Web selesai dibuat! Mengunggah ke Netlify...")

        # 2. Deploy otomatis folder ke Netlify via Netlify CLI
        cmd_deploy = f'npx netlify-cli deploy --dir=. --prod --auth={NETLIFY_AUTH_TOKEN}'
        result = subprocess.run(cmd_deploy, shell=True, cwd=work_dir, capture_output=True, text=True)

        # Ambil URL hasil deploy dari output terminal
        await update.message.reply_text(f"Website kamu sudah aktif!\nCek di sini: {result.stdout}")

    except Exception as e:
        await update.message.reply_text(f"Terjadi kesalahan: {str(e)}")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()