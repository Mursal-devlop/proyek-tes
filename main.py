import os
import subprocess
import glob
import re
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
        clean_prompt = user_prompt.replace('"', '').replace("'", "")
        prompt = (
            f"Generate a single-file responsive website HTML page using Tailwind CSS for: {clean_prompt}. "
            f"Output ONLY valid HTML code including <!DOCTYPE html>."
        )

        await status_msg.edit_text("🤖 [2/3] OpenCode AI sedang merancang & menulis kode...")

        # 1. Jalankan OpenCode dan tangkap output teksnya
        process = subprocess.run(
            f'opencode "{prompt}"', 
            shell=True, 
            cwd=work_dir, 
            capture_output=True, 
            text=True
        )

        # 2. Cek apakah ada file .html yang langsung terbuat di workspace
        html_files = glob.glob(f"{work_dir}/**/*.html", recursive=True)

        # Jika OpenCode tidak membuat file, tetapi mengembalikan teks kode HTML di stdout
        if not html_files and process.stdout:
            stdout_text = process.stdout
            # Ekstrak kode HTML dari output (jika dibungkus ```html ... ```)
            html_match = re.search(r'<!DOCTYPE html>.*</html>', stdout_text, re.DOTALL | re.IGNORECASE)
            if not html_match:
                html_match = re.search(r'<html.*</html>', stdout_text, re.DOTALL | re.IGNORECASE)

            if html_match:
                code_content = html_match.group(0)
            elif "<head>" in stdout_text or "<body>" in stdout_text:
                code_content = stdout_text
            else:
                code_content = None

            if code_content:
                # Tulis langsung kode HTML yang ditangkap ke file index.html
                index_path = os.path.join(work_dir, "index.html")
                with open(index_path, "w", encoding="utf-8") as f:
                    f.write(code_content)
                html_files = [index_path]

        # 3. Jika tetap tidak ada file HTML dan tidak ada output valid
        if not html_files:
            all_files = os.listdir(work_dir)
            log_output = (process.stderr or process.stdout or "Tidak ada output")[:300]
            await status_msg.edit_text(
                f"❌ **OpenCode tidak menghasilkan file atau kode HTML.**\n\n"
                f"📂 Isi folder: `{all_files}`\n"
                f"⚠️ Output/Log Terminal: `{log_output}`\n\n"
                f"💡 *Pastikan `GEMINI_API_KEY` sudah terpasang di Variables Railway.*",
                parse_mode="Markdown"
            )
            return

        target_html = html_files[0]
        index_path = os.path.join(work_dir, "index.html")
        if target_html != index_path:
            os.rename(target_html, index_path)

        await status_msg.edit_text("🐙 [3/3] Membuat repository & mengunggah ke GitHub...")

        # 4. Buat Repository di GitHub dan Push
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