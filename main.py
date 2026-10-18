import os
import subprocess
import re
import glob
import shutil
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
NETLIFY_AUTH_TOKEN = os.getenv("NETLIFY_AUTH_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    chat_id = update.message.chat.id
    
    status_msg = await update.message.reply_text("⏳ [1/3] Menyiapkan environment dan prompt...")

    work_dir = f"./workspace_{chat_id}"
    os.makedirs(work_dir, exist_ok=True)

    try:
        # Prompt yang mewajibkan pembuatan index.html di root folder
        enhanced_prompt = (
            f"You are an expert web developer. Build a complete, responsive, and highly modern website "
            f"using HTML, Tailwind CSS via CDN (<script src='https://cdn.tailwindcss.com'></script>), and JavaScript "
            f"based on this request: {user_prompt}. "
            f"CRITICAL REQUIREMENT: You MUST create a primary file named 'index.html' directly in the working directory. "
            f"Do not put it inside a subfolder unless necessary, and ensure index.html exists."
        )

        await status_msg.edit_text("🤖 [2/3] OpenCode AI sedang merancang & menulis file website...")

        # Panggil OpenCode CLI
        subprocess.run(["opencode", enhanced_prompt], cwd=work_dir, check=True)

        # FIX 404: Cari dan pastikan file index.html tersedia
        deploy_dir = work_dir
        index_path = os.path.join(work_dir, "index.html")

        if not os.path.exists(index_path):
            # Cari file .html apa saja yang mungkin dibuat OpenCode (termasuk di sub-folder)
            html_files = glob.glob(f"{work_dir}/**/*.html", recursive=True)
            if html_files:
                # Ambil file HTML pertama dan gunakan foldernya sebagai deploy_dir
                target_html = html_files[0]
                target_dir = os.path.dirname(target_html)
                
                # Ubah nama file menjadi index.html jika namanya beda
                new_index_path = os.path.join(target_dir, "index.html")
                if target_html != new_index_path:
                    os.rename(target_html, new_index_path)
                
                deploy_dir = target_dir

        await status_msg.edit_text("🚀 [3/3] Kode selesai dibuat! Sedang mengunggah ke Netlify...")

        # Deploy folder yang dipastikan berisi index.html
        cmd_deploy = f"npx netlify-cli deploy --dir={deploy_dir} --prod --auth={NETLIFY_AUTH_TOKEN}"
        result = subprocess.run(cmd_deploy, shell=True, capture_output=True, text=True)

        url_match = re.search(r'https?://[^\s]+\.netlify\.app', result.stdout)
        site_url = url_match.group(0) if url_match else "Website berhasil di-deploy!"

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