import os
import subprocess
import re
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def generate_html_with_gemini(user_prompt: str) -> str:
    """Memanggil Google Gemini API menggunakan endpoint model terbaru"""
    # Menggunakan model gemini-2.5-flash / gemini-2.0-flash terbaru
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    system_instruction = (
        "You are an expert web developer. Create a complete, single-file modern responsive HTML website "
        "using Tailwind CSS (via CDN: <script src='https://cdn.tailwindcss.com'></script>) and JavaScript based on the user's request. "
        "IMPORTANT: Output ONLY valid, clean HTML code starting with <!DOCTYPE html> and ending with </html>. "
        "Do NOT include markdown block markers like ```html or any explanatory prose."
    )
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_instruction}\n\nUser Request: {user_prompt}"}]
            }
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    
    # Fallback ke gemini-2.0-flash jika gemini-2.5-flash belum tersedia di region tertentu
    if response.status_code == 404:
        url_fallback = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=){GEMINI_API_KEY}"
        response = requests.post(url_fallback, headers=headers, json=payload, timeout=60)

    if response.status_code == 200:
        data = response.json()
        raw_html = data['candidates'][0]['content']['parts'][0]['text']
        
        # Bersihkan format markdown ```html
        clean_html = re.sub(r'```html\s*', '', raw_html, flags=re.IGNORECASE)
        clean_html = re.sub(r'```\s*$', '', clean_html).strip()
        return clean_html
    else:
        raise Exception(f"Gemini API Error ({response.status_code}): {response.text}")

async def create_github_repo(repo_name: str):
    """Membuat Repository publik baru di GitHub"""
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

        # 1. Minta Gemini API merancang website
        html_code = await generate_html_with_gemini(user_prompt)

        # 2. Simpan hasilnya langsung ke file index.html
        index_path = os.path.join(work_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html_code)

        await status_msg.edit_text("🐙 [3/3] Membuat repository & mengunggah ke GitHub...")

        # 3. Buat Repo di GitHub & Push kodenya
        repo_url = await create_github_repo(repo_name)
        auth_repo_url = f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com/{GITHUB_USERNAME}/{repo_name}.git"
        
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
            f"💡 *Kamu bisa melihat file index.html di GitHub tersebut.*",
            parse_mode="Markdown"
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

if __name__ == "__main__":
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()