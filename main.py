import os
import subprocess
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NETLIFY_AUTH_TOKEN = os.getenv("NETLIFY_AUTH_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    chat_id = update.message.chat.id
    
    # 1. Kirim pesan awal dan simpan objek alasannya ke variabel 'status_msg'
    status_msg = await update.message.reply_text("⏳ [1/3] Menyiapkan environment dan prompt...")

    work_dir = f"./workspace_{chat_id}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        # Step 1: Menyusun Prompt
        enhanced_prompt = (
            f"You are an expert web developer. Build a complete, responsive, and highly modern website "
            f"using HTML, Tailwind CSS via CDN (<script src='https://cdn.tailwindcss.com'></script>), and JavaScript "
            f"based on this request: {user_prompt}. "
            f"Include proper layout, navigation bar, hero section, features/content, interactive elements, and a footer. "
            f"Make sure all files are properly created and the primary page is saved in index.html."
        )

        # 2. Update status saat AI mulai merancang & menulis kode
        await status_msg.edit_text("🤖 [2/3] OpenCode AI sedang merancang & menulis file website...")

        # Jalankan OpenCode
        subprocess.run(["opencode", enhanced_prompt], cwd=work_dir, check=True)

        # 3. Update status saat proses mengunggah ke Netlify
        await status_msg.edit_text("🚀 [3/3] Kode selesai dibuat! Sedang mengunggah ke Netlify...")

        # Jalankan Deployment Netlify
        cmd_deploy = f"npx netlify-cli deploy --dir=. --prod --auth={NETLIFY_AUTH_TOKEN}"
        result = subprocess.run(cmd_deploy, shell=True, cwd=work_dir, capture_output=True, text=True)

        # Ekstraksi URL Netlify dari log
        url_match = re.search(r'https?://[^\s]+\.netlify\.app', result.stdout)
        site_url = url_match.group(0) if url_match else "Website berhasil di-deploy!"

        # 4. Update status akhir menjadi pesan sukses beserta link website
        await status_msg.edit_text(
            f"✅ **Website Kamu Sudah Aktif!**\n\n"
            f"🔗 Klik link di bawah untuk melihat:\n{site_url}",
            parse_mode="Markdown"
        )

    except subprocess.CalledProcessError as e:
        await status_msg.edit_text(f"❌ Gagal menjalankan OpenCode/Deploy. Exit code: {e.returncode}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()