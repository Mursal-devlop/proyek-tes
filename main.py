import os
import subprocess
import glob
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")

async def create_github_repo(repo_name: str):
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "name": repo_name,
        "private": False,
        "auto_init": False
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code in [201, 422]:
        return f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
    else:
        raise Exception(f"Gagal membuat repo GitHub: {response.json().get('message')}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = update.message.text
    chat_id = update.message.chat.id
    message_id = update.message.message_id
    
    status_msg = await update.message.reply_text("⏳ [1/3] Menyiapkan workspace...")

    work_dir = os.path.abspath(f"./workspace_{chat_id}_{message_id}")
    os.makedirs(work_dir, exist_ok=True)

    repo_name = f"web-ai-{chat_id}-{message_id}"

    try:
        # Buat instruksi ringkas agar OpenCode paham
        enhanced_prompt = (
            f"Build a complete, single-page responsive website based on this request: {user_prompt}. "
            f"Use HTML, Tailwind CSS via CDN, and JavaScript. "
            f"Save the primary file directly as index.html in the working directory."
        )

        await status_msg.edit_text("🤖 [2/3] OpenCode AI sedang merancang & menulis kode...")

        # FIX: Panggil opencode dengan flag -p atau prompt argument yang tepat
        # Jika opencode milikmu memakai 'opencode prompt', jalankan via shell yang sudah diclean
        process = subprocess.run(
            ["opencode", "-p", enhanced_prompt], 
            cwd=work_dir, 
            capture_output=True, 
            text=True
        )

        # Jika opsi flag -p gagal, coba tanpa flag tetapi dipisah dengan benar
        if process.returncode != 0:
            clean_prompt = user_prompt.replace('"', '').replace("'", "")
            process = subprocess.run(
                f'opencode "Create a single page website for: {clean_prompt}"', 
                shell=True, 
                cwd=work_dir, 
                capture_output=True, 
                text=True
            )

        # Cek apakah file HTML berhasil dibuat
        html_files = glob.glob(f"{work_dir}/**/*.html", recursive=True)
        if not html_files:
            all_files = os.listdir(work_dir)
            err_log = process.stderr[:300] if process.stderr else process.stdout[:300]
            await status_msg.edit_text(
                f"❌ **OpenCode gagal membuat file HTML.**\n\n"
                f"📂 Isi folder: `{all_files}`\n"
                f"⚠️ Error Log: `{err_log}`",
                parse_mode="Markdown"
            )
            return

        target_html = html_files[0]
        index_path = os.path.join(work_dir, "index.html")
        if target_html != index_path:
            os.rename(target_html, index_path)

        await status_msg.edit_text("🐙 [3/3] Membuat repository & mengunggah ke GitHub...")

        # Buat Repo & Push
        repo_url = await create_github_repo(repo_name)
        auth_repo_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        
        commands = [
            ["git", "init"],
            ["git", "config", "user.name", "AI Bot"],
            ["git", "config", "user.email", "bot@ai.local"],
            ["git", "add", "."],
            ["git", "commit", "-m", "Initial commit from Telegram AI Bot"],
            ["git", "branch", "-M", "main"],
            ["git", "remote", "add", "origin", auth_repo_url],
            ["git", "push", "-u", "origin", "main"]
        ]

        for cmd in commands:
            subprocess.run(cmd, cwd=work_dir, check=True, capture_output=True)

        await status_msg.edit_text(
            f"✅ **Website Berhasil Dibuat & Diunggah ke GitHub!**\n\n"
            f"📦 **Repository GitHub Kamu:**\n{repo_url}",
            parse_mode="Markdown"
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()