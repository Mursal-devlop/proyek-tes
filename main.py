import os
import subprocess
import re
import glob
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NETLIFY_AUTH_TOKEN = os.getenv("NETLIFY_AUTH_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    chat_id = update.message.chat.id
    
    status_msg = await update.message.reply_text("⏳ [1/3] Menyiapkan workspace...")

    work_dir = os.path.abspath(f"./workspace_{chat_id}")
    os.makedirs(work_dir, exist_ok=True)

    try:
        enhanced_prompt = (
            f"Build a complete, single-page responsive website based on this request: '{user_prompt}'. "
            f"Use HTML, Tailwind CSS via CDN (<script src='https://cdn.tailwindcss.com'></script>), and JavaScript. "
            f"IMPORTANT: Save the main file directly as 'index.html' in the working directory."
        )

        await status_msg.edit_text("🤖 [2/3] OpenCode sedang memproses kode...")

        # Jalankan OpenCode dan tangkap log jika terjadi error
        process = subprocess.run(
            ["opencode", enhanced_prompt],
            cwd=work_dir,
            capture_output=True,
            text=True
        )

        # Cek apakah ada file .html yang berhasil dibuat oleh OpenCode
        html_files = glob.glob(f"{work_dir}/**/*.html", recursive=True)

        if not html_files:
            # Jika tidak ada file HTML, tampilkan isi folder dan log error
            all_files = os.listdir(work_dir)
            error_log = process.stderr[:300] if process.stderr else "Tidak ada log error terminal."
            await status_msg.edit_text(
                f"❌ **OpenCode gagal membuat file HTML.**\n\n"
                f"📂 Isi folder workspace: `{all_files}`\n"
                f"⚠️ Error Log: `{error_log}`\n\n"
                f"💡 *Pastikan GEMINI_API_KEY sudah dimasukkan di Variables Railway.*",
                parse_mode="Markdown"
            )
            return

        # Pastikan file HTML utama bernama index.html di direktori deploy
        target_html = html_files[0]
        deploy_dir = os.path.dirname(target_html)
        index_path = os.path.join(deploy_dir, "index.html")

        if target_html != index_path:
            os.rename(target_html, index_path)

        await status_msg.edit_text("🚀 [3/3] Mengunggah file ke Netlify...")

        # Deploy hanya direktori yang dipastikan berisi index.html
        cmd_deploy = f"npx netlify-cli deploy --dir={deploy_dir} --prod --auth={NETLIFY_AUTH_TOKEN}"
        result = subprocess.run(cmd_deploy, shell=True, capture_output=True, text=True)

        # Ambil link live Netlify dari output
        url_match = re.search(r'https://[a-zA-Z0-9-]+\.netlify\.app', result.stdout)
        
        if url_match:
            site_url = url_match.group(0)
            await status_msg.edit_text(
                f"✅ **Website Kamu Berhasil Aktif!**\n\n"
                f"🔗 Link Website:\n{site_url}",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(
                f"⚠️ **Netlify Deploy Log:**\n```\n{result.stdout[-400:]}\n```",
                parse_mode="Markdown"
            )

    except Exception as e:
        await status_msg.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()