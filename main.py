import os
import re
import uuid
import urllib.request
import tarfile
import platform
import logging
from threading import Thread, Lock
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from werkzeug.utils import safe_join
import yt_dlp
from waitress import serve

# إعداد التطبيق
app = Flask(__name__)

# مجلد التحميل المؤقت
DOWNLOAD_FOLDER = '/tmp/download_temp' if platform.system() != 'Windows' else os.path.join(os.getcwd(), 'downloads_temp')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# بيانات تقدم التحميل
progress_data = {}
progress_lock = Lock()

# إعداد السجل (اللوق)
logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')

# قائمة البروكسيات
PROXIES = [
    
    "http://nliaeayc:rbwz1px958d8@154.36.110.199:6853",
]

# تحميل ffmpeg إذا لم يكن موجودًا
def ensure_ffmpeg():
    ffmpeg_filename = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    ffmpeg_dir = "ffmpeg_bin"
    ffmpeg_path = os.path.abspath(os.path.join(ffmpeg_dir, ffmpeg_filename))

    if not os.path.exists(ffmpeg_path):
        logging.info("FFmpeg غير موجود. سيتم تحميله...")
        os.makedirs(ffmpeg_dir, exist_ok=True)
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        tar_path = "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, tar_path)

        with tarfile.open(tar_path) as tar:
            for member in tar.getmembers():
                if member.name.endswith(ffmpeg_filename) or (platform.system() != "Windows" and member.name.endswith("ffmpeg")):
                    member.name = os.path.basename(member.name)
                    tar.extract(member, ffmpeg_dir)
                    break

        if platform.system() != "Windows":
            os.chmod(ffmpeg_path, 0o755)

        os.remove(tar_path)
        logging.info("تم تحميل FFmpeg بنجاح.")
    else:
        logging.info("FFmpeg موجود بالفعل.")
    
    return ffmpeg_path

# تهيئة ffmpeg
ffmpeg_local_path = ensure_ffmpeg()
os.environ["PATH"] = f"{os.path.dirname(ffmpeg_local_path)}{os.pathsep}{os.environ.get('PATH', '')}"

# دالة لتنسيق اسم الملف
def slugify(value):
    value = re.sub(r'[^\w\s-]', '', value, flags=re.UNICODE)
    return value.strip().replace(' ', '_')

# تحديث نسبة التقدم
def update_progress(task_id, d):
    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
        downloaded_bytes = d.get('downloaded_bytes', 0)
        percentage = (downloaded_bytes / total_bytes) * 100

        with progress_lock:
            if task_id in progress_data:
                progress_data[task_id]['progress'] = percentage
                logging.debug(f"[مهمة {task_id}] التقدم: {percentage:.2f}%")

# العامل المسؤول عن التحميل
def download_worker(task_id, url, is_mp3):
    try:
        logging.debug(f"[مهمة {task_id}] بدء التحميل")
        cookie_path = os.path.join(os.getcwd(), 'cookies.txt')
        if not os.path.isfile(cookie_path):
            raise FileNotFoundError('ملف cookies.txt غير موجود.')

        info = None
        for proxy_url in PROXIES:
            try:
                ydl_opts_info = {
                    'quiet': True,
                    'no_warnings': True,
                    'cookiefile': cookie_path,
                    'nocheckcertificate': True,
                    'proxy': proxy_url
                }
                with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                    info = ydl.extract_info(url, download=False)
                break
            except Exception:
                continue

        if not info:
            raise Exception("فشل في جلب معلومات الفيديو من جميع البروكسيات.")

        title = slugify(info.get('title', f'video_{uuid.uuid4()}'))
        formats = info.get('formats', [])

        ext, format_id = ('mp3', 'bestaudio/best') if is_mp3 else ('mp4', 'best')
        if not is_mp3:
            if 'youtube.com' in url or 'youtu.be' in url:
                format_id = 'bestvideo+bestaudio/best'
                ext = 'mp4'
            else:
                video_audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') != 'none']
                if video_audio_formats:
                    best_format = max(video_audio_formats, key=lambda f: f.get('height') or 0)
                    format_id = best_format['format_id']
                    ext = best_format.get('ext', 'mp4')

        download_success = False
        for proxy_url in PROXIES:
            try:
                ydl_opts_download = {
                    'format': format_id,
                    'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{title}.%(ext)s'),
                    'noplaylist': True,
                    'quiet': True,
                    'no_warnings': True,
                    'progress_hooks': [lambda d: update_progress(task_id, d)],
                    'cookiefile': cookie_path,
                    'nocheckcertificate': True,
                    'ffmpeg_location': ffmpeg_local_path,
                    'proxy': proxy_url
                }
                if is_mp3:
                    ydl_opts_download['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]

                with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
                    ydl.download([url])

                download_success = True
                break
            except Exception:
                continue

        if not download_success:
            raise Exception("فشل في تحميل الفيديو باستخدام جميع البروكسيات.")

        actual_filename = f'{title}.{ext}'
        full_path = os.path.join(DOWNLOAD_FOLDER, actual_filename)
        if not os.path.exists(full_path):
            raise Exception(f'الملف {actual_filename} غير موجود بعد التحميل.')

        with progress_lock:
            progress_data[task_id]['download_url'] = f'/download/{actual_filename}'
            progress_data[task_id]['progress'] = 100.0

        logging.info(f"[مهمة {task_id}] التحميل اكتمل: {actual_filename}")

    except Exception as e:
        with progress_lock:
            progress_data[task_id]['error'] = str(e)
            progress_data[task_id]['progress'] = 0.0
        logging.error(f"[مهمة {task_id}] خطأ: {e}")

# الصفحة الرئيسية
@app.route('/')
def index():
    return render_template('index.html')

# بدء عملية التحميل
@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    format_type = data.get('format')
    is_mp3 = format_type == 'mp3'

    task_id = str(uuid.uuid4())
    with progress_lock:
        progress_data[task_id] = {'progress': 0.0, 'download_url': None, 'error': None}

    Thread(target=download_worker, args=(task_id, url, is_mp3)).start()

    return jsonify({'task_id': task_id})

# جلب حالة التقدم
@app.route('/progress/<task_id>')
def get_progress(task_id):
    with progress_lock:
        return jsonify(progress_data.get(task_id, {'error': 'معرف المهمة غير صالح'}))

# تحميل الملف النهائي
@app.route('/download/<path:filename>')
def download_file(filename):
    safe_path = safe_join(DOWNLOAD_FOLDER, filename)
    if not safe_path or not os.path.isfile(safe_path):
        abort(404)
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)

# تشغيل السيرفر
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    serve(app, host='0.0.0.0', port=port)