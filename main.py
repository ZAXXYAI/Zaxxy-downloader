import os
import re
import uuid
import urllib.request
import tarfile
import platform
from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from werkzeug.utils import safe_join
from threading import Thread, Lock
import yt_dlp
import logging
from waitress import serve

app = Flask(__name__)

DOWNLOAD_FOLDER = '/tmp/download_temp' if platform.system() != 'Windows' else os.path.join(os.getcwd(), 'downloads_temp')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

progress_data = {}
progress_lock = Lock()

logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')

def ensure_ffmpeg():
    ffmpeg_filename = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    ffmpeg_dir = "ffmpeg_bin"
    ffmpeg_path = os.path.abspath(os.path.join(ffmpeg_dir, ffmpeg_filename))
    
    if not os.path.exists(ffmpeg_path):
        logging.info("FFmpeg غير موجود. بدء التحميل...")
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
        logging.info("FFmpeg تم تحميله بنجاح.")
    else:
        logging.info("FFmpeg موجود مسبقًا.")
    return ffmpeg_path

ffmpeg_local_path = ensure_ffmpeg()
os.environ["PATH"] = f"{os.path.dirname(ffmpeg_local_path)}{os.pathsep}{os.environ.get('PATH', '')}"

def slugify(value):
    value = re.sub(r'[^\w\s-]', '', value, flags=re.UNICODE)
    return value.strip().replace(' ', '_')

def update_progress(task_id, d):
    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
        downloaded_bytes = d.get('downloaded_bytes', 0)
        percentage = (downloaded_bytes / total_bytes) * 100
        with progress_lock:
            if task_id in progress_data:
                progress_data[task_id]['progress'] = percentage
                logging.debug(f"[مهمة {task_id}] نسبة التقدم: {percentage:.2f}%")

def download_worker(task_id, url, is_mp3):
    try:
        logging.debug(f"[مهمة {task_id}] مجلد التنزيل: {DOWNLOAD_FOLDER}")
        logging.debug(f"[مهمة {task_id}] المجلد موجود: {os.path.exists(DOWNLOAD_FOLDER)}")
        logging.debug(f"[مهمة {task_id}] المجلد قابل للكتابة: {os.access(DOWNLOAD_FOLDER, os.W_OK)}")

        cookie_path = os.path.join(os.getcwd(), 'cookies.txt')
        if not os.path.isfile(cookie_path):
            raise FileNotFoundError('ملف cookies.txt غير موجود. تأكد من وجوده في مجلد المشروع.')

        proxy_url = "http://nliaeayc:rbwz1px958d8@198.23.239.134:6540"

        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
            'cookiefile': cookie_path,
            'nocheckcertificate': True,
            'proxy': proxy_url
        }

        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)

        title = slugify(info.get('title', f'video_{uuid.uuid4()}'))
        formats = info.get('formats', [])

        if is_mp3:
            ydl_opts_download = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{title}.%(ext)s'),
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [lambda d: update_progress(task_id, d)],
                'cookiefile': cookie_path,
                'nocheckcertificate': True,
                'ffmpeg_location': ffmpeg_local_path,
                'proxy': proxy_url,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            ext = 'mp3'
        else:
            video_audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') != 'none']
            if video_audio_formats:
                best_format = max(video_audio_formats, key=lambda f: f.get('height') or 0)
                format_id = best_format['format_id']
                ext = best_format.get('ext', 'mp4')
            else:
                best_video = max([f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none'], key=lambda f: f.get('height') or 0, default=None)
                best_audio = max([f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none'], key=lambda f: f.get('abr') or 0, default=None)
                if best_video and best_audio:
                    format_id = f"{best_video['format_id']}+{best_audio['format_id']}"
                    ext = best_video.get('ext', 'mp4')
                else:
                    format_id = 'best'
                    ext = info.get('ext', 'mp4')

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

        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            ydl.download([url])

        actual_filename = f'{title}.{ext}'
        full_path = os.path.join(DOWNLOAD_FOLDER, actual_filename)

        if not os.path.exists(full_path):
            raise Exception(f'الملف {actual_filename} غير موجود بعد انتهاء التحميل.')

        with progress_lock:
            progress_data[task_id]['download_url'] = f'/download/{actual_filename}'
            progress_data[task_id]['progress'] = 100.0

        logging.info(f"[مهمة {task_id}] التحميل اكتمل: {actual_filename}")

    except Exception as e:
        with progress_lock:
            progress_data[task_id]['error'] = str(e)
            progress_data[task_id]['progress'] = 0.0
        logging.error(f"[مهمة {task_id}] خطأ أثناء التحميل: {e}")
        print(f"[خطأ المهمة {task_id}]: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    format_type = data.get('format')
    is_mp3 = format_type == 'mp3'

    task_id = str(uuid.uuid4())
    with progress_lock:
        progress_data[task_id] = {'progress': 0.0, 'download_url': None, 'error': None}

    thread = Thread(target=download_worker, args=(task_id, url, is_mp3))
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/progress/<task_id>')
def get_progress(task_id):
    with progress_lock:
        if task_id not in progress_data:
            return jsonify({'error': 'معرف المهمة غير صالح'})
        return jsonify(progress_data[task_id])

@app.route('/download/<path:filename>')
def download_file(filename):
    safe_path = safe_join(DOWNLOAD_FOLDER, filename)
    if not safe_path or not os.path.isfile(safe_path):
        abort(404)
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    serve(app, host='0.0.0.0', port=port)