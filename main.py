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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def generate_with_gemini_fallback(prompt_text: str) -> str:
    """Fallback jika OpenCode error: Panggil Gemini API langsung via HTTP Request"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    system_instruction = (
        "You are an expert web developer. Create a complete, single-file HTML website with Tailwind CSS (via CDN) "
        "and JavaScript based on the user's request. Output ONLY valid HTML code starting with <!DOCTYPE html> and ending with </html>. "
        "Do not include Markdown formatting or extra text outside the HTML code."
    )
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_instruction}\n\nUser Request: {prompt_text}"}]
            }
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        raw_html = data['candidates'][0]['content']['parts'][0]['text']
        # Clean markdown code blocks if present
        clean_html = re.sub(r'```html\s*', '', raw_html, flags=re.IGNORECASE)
        clean_html = re.sub(r'```\s*$', '', clean_html).strip()
        return clean_html
    else:
        raise Exception(f"Gemini API Error {response.status_code}: {response.text}")

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
        await status_msg.edit_text("🤖 [2/3] AI sedang merancang & menulis kode HTML...")

        html_content = None

        # 1. Coba eksekusi via OpenCode dengan file prompt untuk menghindari error ENAMETOOLONG
        prompt_file = os.path.join(work_dir, "prompt.txt")
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(user_prompt)

        try:
            process = subprocess.run(
                f'opencode < "{prompt_file}"', 
                shell=True, 
                cwd=work_dir, 
                capture_output=True, 
                text=True,
                timeout=30
            )
            # Cek jika ada file HTML hasil opencode
            html_files = glob.glob(f"{work_dir}/**/*.html", recursive=True)
            if html_files:
                with open(html_files[0], "r", encoding="utf-8") as f:
                    html_content = f.read()
        except Exception:
            pass

        # 2. Jika OpenCode gagal/tidak menghasilkan HTML, gunakan Gemini API langsung
        if not html_content:
            html_content = await generate_with_gemini_fallback(user_prompt)

        # Simpan hasil akhir ke index.html
        index_path = os.path.join(work_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        await status_msg.edit_text("🐙 [3/3] Membuat repository & mengunggah ke GitHub...")

        # 3. Buat Repository di GitHub & Push
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