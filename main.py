import os
import subprocess
import requests
from google import genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def generate_html_with_gemini(user_prompt: str) -> str:
    """Memanggil Gemini API menggunakan SDK resmi google-genai"""
    clean_key = GEMINI_API_KEY.strip() if GEMINI_API_KEY else ""
    if not clean_key:
        raise Exception("GEMINI_API_KEY belum terpasang di Variables Railway.")

    # Inisialisasi client resmi dari Google
    client = genai.Client(api_key=clean_key)
    
    system_instruction = (
        "You are an expert web developer. Create a complete, single-file modern responsive HTML website "
        "using Tailwind CSS (via CDN: <script src='https://cdn.tailwindcss.com'></script>) and JavaScript based on the user's request. "
        "IMPORTANT: Output ONLY valid, clean HTML code starting with <!DOCTYPE html> and ending with </html>. "
        "Do NOT include markdown block markers like ```html or any explanatory prose."
    )

    try:
        # Panggil model gemini-2.5-flash via SDK resmi
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"{system_instruction}\n\nUser Request: {user_prompt}"
        )
        
        raw_html = response.text
        # Bersihkan format markdown jika ada
        clean_html = raw_html.replace('```html', '').replace('```HTML', '').replace('```', '').strip()
        return clean_html

    except Exception as e:
        raise Exception(f"Gagal memanggil Gemini SDK: {str(e)}")

async def create_github_repo(repo_name: str):
    clean_token = GITHUB_TOKEN.strip() if GITHUB_TOKEN else ""
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {clean_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "name": repo_name,
        "private": False,
        "auto_init": False
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
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
        await status_msg.edit_text("🤖 [2/3] Gemini AI sedang merancang & menulis kode HTML...")

        # 1. Panggil Gemini SDK
        html_code = await generate_html_with_gemini(user_prompt)

        # 2. Simpan ke index.html
        index_path = os.path.join(work_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html_code)

        await status_msg.edit_text("🐙 [3/3] Membuat repository & mengunggah ke GitHub...")

        # 3. Buat Repo di GitHub & Push
        repo_url = await create_github_repo(repo_name)
        clean_token = GITHUB_TOKEN.strip() if GITHUB_TOKEN else ""
        auth_repo_url = f"https://{GITHUB_USERNAME}:{clean_token}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        
        commands = [
            ["git", "init"],
            ["git", "config", "user.name", "AI Bot"],
            ["git", "config", "user.email", "bot@ai.local"],
            ["git", "add", "."],
            ["git", "commit", "-m", f"Generated website for prompt: {user_prompt[:50]}"],
            ["git", "branch", "-M", "main"],
            ["git", "remote", "add", "origin", auth_repo_url],
            ["git", "push", "-u", "origin", "main"]
        ]

        for cmd in commands:
            subprocess.run(cmd, cwd=work_dir, check=True, capture_output=True)

        await status_msg.edit_text(
            f"✅ **Website Berhasil Dibuat & Diunggah ke GitHub!**\n\n"
            f"📦 **Repository GitHub Kamu:**\n{repo_url}\n\n"
            f"💡 *Kamu bisa melihat file index.html di dalam repository tersebut.*",
            parse_mode="Markdown"
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()