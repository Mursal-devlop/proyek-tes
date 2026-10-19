
import os
import re
import base64
import shutil
import asyncio
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests
from google import genai
from google.genai import types
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==================================================
# KONFIGURASI
# ==================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Model dapat diganti lewat Environment Variable.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR / "workspace"

GITHUB_API_URL = "https://api.github.com"

SYSTEM_INSTRUCTION = """
Kamu adalah web developer profesional.

Buat website lengkap dalam satu file index.html berdasarkan permintaan pengguna.

Ketentuan:
1. Gunakan HTML5, Tailwind CSS melalui CDN, dan JavaScript jika diperlukan.
2. Buat desain modern, responsif, rapi, dan mudah digunakan.
3. Pastikan struktur HTML lengkap dan valid.
4. Tambahkan konten yang relevan dengan permintaan pengguna.
5. Gunakan ikon dari CDN jika diperlukan.
6. Jangan membuat file terpisah.
7. Output hanya kode HTML, tanpa Markdown, tanpa penjelasan.
8. HTML harus dimulai dengan <!DOCTYPE html> dan diakhiri dengan </html>.
9. Jangan mengarang hasil integrasi backend yang sebenarnya belum tersedia.
"""

CLASSIFIER_INSTRUCTION = """
Kamu adalah pengklasifikasi niat (intent) pesan pengguna.

Tentukan apakah pesan pengguna meminta dibuatkan website/halaman web.

Balas HANYA dengan satu kata, tanpa penjelasan:
- WEBSITE : pengguna meminta dibuatkan website/halaman web secara langsung.
            Contoh: "buatkan website toko", "bikin landing page", "buatkan
            portfolio html".
- CHAT    : semua permintaan lain, termasuk sapaan, pertanyaan umum,
            tugas sekolah, matematika, coding, curhat, terjemahan, dan
            pertanyaan "bagaimana cara membuat website" (hanya tanya,
            bukan minta dibuatkan).
"""

CHAT_INSTRUCTION = """
Kamu adalah asisten AI yang ramah, sopan, dan membantu, seperti chatbot
pada umumnya.

Aturan:
1. Jawab dengan bahasa yang sama dengan pengguna (default Bahasa Indonesia).
2. Jika pengguna menyapa, balas sapaan dengan ramah dan tawarkan bantuan.
3. Jika pengguna meminta bantuan tugas sekolah (matematika, IPA, IPS,
   bahasa, sejarah, dsb), bantu selesaikan dengan langkah yang jelas.
   Untuk soal hitungan, tunjukkan cara penyelesaiannya, bukan hanya hasil.
4. Jawab dengan jelas, ringkas, dan terstruktur. Gunakan poin bila perlu.
5. Jangan mengarang fakta. Jika tidak tahu, katakan dengan jujur.
6. Jangan menampilkan kode HTML website kecuali diminta secara eksplisit.
"""


# ==================================================
# VALIDASI KONFIGURASI
# ==================================================

def validate_config():
    required = {
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "GITHUB_TOKEN": GITHUB_TOKEN,
        "GITHUB_USERNAME": GITHUB_USERNAME,
        "GEMINI_API_KEY": GEMINI_API_KEY,
    }

    missing = [
        name for name, value in required.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Environment variable belum diisi: "
            + ", ".join(missing)
        )


# ==================================================
# GEMINI AI
# ==================================================

def _call_gemini_sync(
    system_instruction,
    user_prompt,
    temperature,
    max_output_tokens,
    previous_interaction_id=None,
    store=False,
):
    client = genai.Client(api_key=GEMINI_API_KEY)

    # API Gemini terbaru menyarankan Interactions API.
    # Jika SDK lama, fallback ke generate_content.
    if hasattr(client, "interactions"):
        kwargs = {
            "model": GEMINI_MODEL,
            "input": user_prompt,
            "system_instruction": system_instruction,
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
            "store": store,
        }
        if previous_interaction_id:
            kwargs["previous_interaction_id"] = previous_interaction_id

        response = client.interactions.create(**kwargs)

        return (
            getattr(response, "output_text", None),
            getattr(response, "id", None),
            response,
        )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    return getattr(response, "text", None), None, response


async def _call_gemini(
    system_instruction,
    user_prompt,
    temperature=0.4,
    max_output_tokens=16000,
    previous_interaction_id=None,
    store=False,
):
    return await asyncio.to_thread(
        _call_gemini_sync,
        system_instruction,
        user_prompt,
        temperature,
        max_output_tokens,
        previous_interaction_id,
        store,
    )


async def classify_request(user_prompt: str) -> str:
    try:
        text, _, _ = await _call_gemini(
            CLASSIFIER_INSTRUCTION,
            user_prompt,
            temperature=0.0,
            max_output_tokens=8,
        )
    except Exception:
        return "chat"

    if text and "website" in text.lower():
        return "website"

    return "chat"


async def answer_general(user_prompt, previous_interaction_id=None):
    text, interaction_id, _ = await _call_gemini(
        CHAT_INSTRUCTION,
        user_prompt,
        temperature=0.7,
        max_output_tokens=4000,
        previous_interaction_id=previous_interaction_id,
        store=True,
    )

    if not text or not text.strip():
        raise RuntimeError("Gemini tidak menghasilkan jawaban.")

    return text.strip(), interaction_id


async def generate_html_with_gemini(user_prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY belum diatur di Environment Variables."
        )

    try:
        raw_html, _, response = await _call_gemini(
            SYSTEM_INSTRUCTION,
            user_prompt,
            temperature=0.4,
            max_output_tokens=16000,
        )

        if not raw_html or not raw_html.strip():
            status = getattr(response, "status", "")
            errors = getattr(response, "errors", None)
            raise RuntimeError(
                "Gemini tidak menghasilkan kode HTML"
                + (f" (status: {status})" if status else "")
                + (f" ({errors})" if errors else "")
                + ". Coba prompt yang lebih jelas."
            )

        # Membersihkan Markdown fence jika model tetap menghasilkannya.
        clean_html = raw_html.strip()
        clean_html = re.sub(
            r"^```(?:html)?\s*",
            "",
            clean_html,
            flags=re.IGNORECASE,
        )
        clean_html = re.sub(
            r"\s*```$",
            "",
            clean_html,
        ).strip()

        # Ambil hanya dokumen HTML-nya, buang teks tambahan di luar tag.
        lower_html = clean_html.lower()
        start = lower_html.find("<!doctype")
        if start == -1:
            start = lower_html.find("<html")
        end = lower_html.rfind("</html>")

        if start == -1:
            raise RuntimeError(
                "Hasil Gemini bukan dokumen HTML lengkap."
            )

        if end == -1:
            raise RuntimeError(
                "Kode HTML terpotong atau tidak memiliki penutup </html>. "
                "Coba prompt yang lebih sederhana."
            )

        if end < start:
            raise RuntimeError(
                "Struktur HTML dari Gemini tidak valid. "
                "Coba prompt yang lebih sederhana."
            )

        clean_html = clean_html[start:end + len("</html>")].strip()

        return clean_html

    except Exception as exc:
        raise RuntimeError(
            f"Gagal menghasilkan HTML dengan Gemini: {exc}"
        ) from exc


# ==================================================
# GITHUB
# ==================================================

def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def create_github_repo(repo_name: str) -> str:
    def create():
        response = requests.post(
            f"{GITHUB_API_URL}/user/repos",
            headers=github_headers(),
            json={
                "name": repo_name,
                "private": False,
                "auto_init": False,
                "description": "Website generated by Telegram AI Bot",
            },
            timeout=30,
        )

        if response.status_code == 201:
            data = response.json()
            return data["html_url"]

        # Jangan menganggap semua HTTP 422 sebagai sukses.
        # 422 juga bisa berarti nama repository bermasalah.
        if response.status_code == 422:
            check = requests.get(
                f"{GITHUB_API_URL}/repos/"
                f"{quote(GITHUB_USERNAME, safe='')}/"
                f"{quote(repo_name, safe='')}",
                headers=github_headers(),
                timeout=30,
            )

            if check.status_code == 200:
                return check.json()["html_url"]

        try:
            message = response.json().get(
                "message", response.text
            )
        except ValueError:
            message = response.text

        raise RuntimeError(
            f"GitHub gagal membuat repository "
            f"(HTTP {response.status_code}): {message}"
        )

    return await asyncio.to_thread(create)


async def push_to_github(work_dir: Path, repo_name: str):
    if shutil.which("git") is None:
        raise RuntimeError(
            "Git tidak ditemukan. Pastikan git sudah terpasang "
            "di server/container."
        )

    # Autentikasi Git melalui header, bukan token di URL remote.
    # Dengan begitu token tidak tertulis di konfigurasi origin.
    repo_url = (
        f"https://github.com/"
        f"{quote(GITHUB_USERNAME, safe='')}/"
        f"{quote(repo_name, safe='')}.git"
    )

    def run_git(args):
        return subprocess.run(
            ["git", *args],
            cwd=str(work_dir),
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def push():
        run_git(["init"])
        run_git(["config", "user.name", "AI Bot"])
        run_git(["config", "user.email", "bot@ai.local"])
        run_git(["add", "index.html"])

        run_git([
            "commit",
            "--allow-empty",
            "-m",
            "Generate website with Gemini AI",
        ])

        run_git(["branch", "-M", "main"])

        # Mendukung pengulangan proses pada workspace yang sama.
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
        )

        if remote.returncode == 0:
            run_git(["remote", "set-url", "origin", repo_url])
        else:
            run_git(["remote", "add", "origin", repo_url])

        auth_value = f"x-access-token:{GITHUB_TOKEN}"
        basic_auth = base64.b64encode(
            auth_value.encode("utf-8")
        ).decode("ascii")

        # GitHub menerima autentikasi HTTPS melalui HTTP extra header.
        # Jangan mencetak header ini ke log karena berisi token.
        run_git([
            "-c",
            f"http.https://github.com/.extraheader="
            f"AUTHORIZATION: basic {basic_auth}",
            "push",
            "-u",
            "origin",
            "main",
        ])

    await asyncio.to_thread(push)


async def enable_github_pages(repo_name: str) -> str:
    owner = quote(GITHUB_USERNAME, safe="")
    repo = quote(repo_name, safe="")
    pages_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pages"

    def enable():
        response = requests.post(
            pages_url,
            headers=github_headers(),
            json={"source": {"branch": "main", "path": "/"}},
            timeout=30,
        )

        if response.status_code in (200, 201):
            return response.json().get("html_url")

        # 409 = Pages sudah aktif. Ambil URL-nya saja.
        if response.status_code == 409:
            check = requests.get(
                pages_url,
                headers=github_headers(),
                timeout=30,
            )
            if check.status_code == 200:
                return check.json().get("html_url")

        try:
            message = response.json().get(
                "message", response.text
            )
        except ValueError:
            message = response.text

        raise RuntimeError(
            f"GitHub Pages gagal diaktifkan "
            f"(HTTP {response.status_code}): {message}"
        )

    return await asyncio.to_thread(enable)


# ==================================================
# PERINTAH TELEGRAM
# ==================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.message:
        await update.message.reply_text(
            "Halo! Aku asisten AI. Kamu bisa:\n\n"
            "1. Ngobrol santai atau tanya apa saja.\n"
            "2. Minta bantuan tugas sekolah (matematika, IPA, IPS, "
            "bahasa, dsb) — akan dijelaskan langkahnya.\n"
            "3. Minta dibuatkan website. Contoh:\n"
            "\"Buat website toko kopi modern dengan katalog produk.\"\n"
            "Website akan otomatis diunggah ke GitHub Pages dan "
            "aku kirim link-nya."
        )


def redact_secrets(text: str) -> str:
    """Hapus token/kredensial dari teks sebelum dikirim ke pengguna."""
    if not text:
        return ""

    for secret in (GITHUB_TOKEN, GEMINI_API_KEY, TELEGRAM_TOKEN):
        if secret:
            text = text.replace(secret, "***")

    text = re.sub(
        r"(AUTHORIZATION:\s*basic\s+)\S+",
        r"\1***",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"https://[^@\s]+@github\.com",
        "https://***@github.com",
        text,
        flags=re.IGNORECASE,
    )
    return text


TELEGRAM_MAX_MESSAGE = 4000


async def send_long_message(message, text: str):
    chunks = [
        text[i:i + TELEGRAM_MAX_MESSAGE]
        for i in range(0, len(text), TELEGRAM_MAX_MESSAGE)
    ] or [""]

    for chunk in chunks:
        await message.reply_text(chunk)


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    user_prompt = update.message.text.strip()
    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    if not user_prompt:
        return

    try:
        await context.bot.send_chat_action(
            chat_id=chat_id,
            action="typing",
        )
    except TelegramError:
        pass

    intent = await classify_request(user_prompt)

    if intent != "website":
        chat_data = (
            context.chat_data
            if context and context.chat_data is not None
            else {}
        )

        try:
            answer, interaction_id = await answer_general(
                user_prompt,
                chat_data.get("last_interaction_id"),
            )

            if interaction_id:
                chat_data["last_interaction_id"] = interaction_id

            await send_long_message(update.message, answer)

        except Exception as exc:
            detail = redact_secrets(str(exc))[:2500]
            await update.message.reply_text(
                f"❌ Terjadi kesalahan:\n{detail}"
            )

        return

    status_msg = await update.message.reply_text(
        "⏳ [1/3] Menyiapkan workspace..."
    )

    work_dir = WORKSPACE_DIR / f"{chat_id}_{message_id}"
    repo_name = f"web-ai-{chat_id}-{message_id}"

    try:
        work_dir.mkdir(parents=True, exist_ok=True)

        await status_msg.edit_text(
            "🤖 [2/3] Gemini sedang membuat website..."
        )

        html_code = await generate_html_with_gemini(user_prompt)

        index_path = work_dir / "index.html"
        index_path.write_text(html_code, encoding="utf-8")

        await status_msg.edit_text(
            "🐙 [3/3] Menyiapkan repository dan mengunggah ke GitHub..."
        )

        repo_url = await create_github_repo(repo_name)
        await push_to_github(work_dir, repo_name)

        await status_msg.edit_text(
            "🌐 Mengaktifkan GitHub Pages agar link bisa langsung dibuka..."
        )

        pages_url = None
        pages_error = None
        try:
            pages_url = await enable_github_pages(repo_name)
        except Exception as exc:
            pages_error = redact_secrets(str(exc))

        if pages_url:
            await status_msg.edit_text(
                "✅ Website berhasil dibuat dan dipublikasikan!\n\n"
                f"🌐 Link website (langsung buka):\n{pages_url}\n\n"
                "⏳ Catatan: jika link belum terbuka, tunggu 1-2 menit "
                "karena GitHub Pages sedang proses build pertama.\n\n"
                f"📦 Repository:\n{repo_url}"
            )
        else:
            await status_msg.edit_text(
                "✅ Website berhasil dibuat dan diunggah!\n\n"
                f"📦 Repository:\n{repo_url}\n\n"
                "⚠️ GitHub Pages gagal diaktifkan otomatis. "
                "Aktifkan manual di Settings → Pages "
                "(Branch: main, Folder: /root).\n\n"
                f"Detail: {pages_error[:300]}"
            )

    except subprocess.CalledProcessError as exc:
        # Output Git dapat berisi detail teknis. Jangan kirim
        # environment variable atau kredensial ke pengguna.
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        detail = redact_secrets(detail)[-1200:]

        await status_msg.edit_text(
            "❌ Proses Git gagal.\n\n"
            f"Detail:\n{detail}"
        )

    except Exception as exc:
        detail = redact_secrets(str(exc))[:2500]
        try:
            await status_msg.edit_text(
                f"❌ Terjadi kesalahan:\n{detail}"
            )
        except TelegramError:
            await update.message.reply_text(
                f"❌ Terjadi kesalahan:\n{detail}"
            )


# ==================================================
# MENJALANKAN BOT
# ==================================================

def main():
    validate_config()

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    print(f"Bot aktif. Model Gemini: {GEMINI_MODEL}")
    app.run_polling()


if __name__ == "__main__":
    main()
