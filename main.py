import os
import re
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory
from threading import Thread
import yt_dlp

app = Flask(__name__)
DOWNLOAD_FOLDER = 'download_temp'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

progress_data = {}

def slugify(value):
    # إزالة الرموز التعبيرية وكل الأحرف غير الأبجدية الرقمية والمسافات والشرطات
    value = re.sub(r'[^\w\s-]', '', value, flags=re.UNICODE)
    return value.strip().replace(' ', '_')

def update_progress(task_id, d):
    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
        downloaded_bytes = d.get('downloaded_bytes', 0)
        percentage = (downloaded_bytes / total_bytes) * 100
        progress_data[task_id]['progress'] = percentage

def download_worker(task_id, url, is_mp3):
    try:
        cookie_path = os.path.join(os.getcwd(), 'cookies.txt')
        if not os.path.isfile(cookie_path):
            raise FileNotFoundError('ملف الكوكيز cookies.txt غير موجود. الرجاء التأكد من وضعه في مجلد التطبيق.')

        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
            'cookiefile': cookie_path,
            'nocheckcertificate': True
        }

        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)

        title = slugify(info.get('title', f'video_{uuid.uuid4()}'))
        formats = info.get('formats', [])

        if is_mp3:
            audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
            if not audio_formats:
                raise Exception('لا توجد صيغة صوت متاحة لهذا الفيديو.')
            best_audio = max(audio_formats, key=lambda f: f.get('abr') or 0)
            format_id = best_audio['format_id']

            ydl_opts_download = {
                'format': format_id,
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{title}.%(ext)s'),
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [lambda d: update_progress(task_id, d)],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'cookiefile': cookie_path,
                'nocheckcertificate': True,
            }

        else:
            video_audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') != 'none']
            if video_audio_formats:
                best_format = max(video_audio_formats, key=lambda f: f.get('height') or 0)
                format_id = best_format['format_id']
            else:
                best_video = max([f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none'], key=lambda f: f.get('height') or 0, default=None)
                best_audio = max([f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none'], key=lambda f: f.get('abr') or 0, default=None)
                if best_video and best_audio:
                    format_id = f"{best_video['format_id']}+{best_audio['format_id']}"
                else:
                    format_id = 'best'

            ydl_opts_download = {
                'format': format_id,
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{title}.%(ext)s'),
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [lambda d: update_progress(task_id, d)],
                'cookiefile': cookie_path,
                'nocheckcertificate': True,
            }

        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            ydl.download([url])

        # تحديد الامتداد الحقيقي بناءً على الملفات الموجودة
        ext = 'mp3' if is_mp3 else 'mp4'
        actual_filename = f'{title}.{ext}'
        full_path = os.path.join(DOWNLOAD_FOLDER, actual_filename)

        # تأكيد وجود الملف
        if not os.path.exists(full_path):
            raise Exception(f'الملف {actual_filename} لم يتم العثور عليه بعد التحميل.')

        progress_data[task_id]['download_url'] = f'/download/{actual_filename}'
        progress_data[task_id]['progress'] = 100.0

    except Exception as e:
        progress_data[task_id]['error'] = str(e)
        progress_data[task_id]['progress'] = 0.0

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
    progress_data[task_id] = {'progress': 0.0, 'download_url': None, 'error': None}

    thread = Thread(target=download_worker, args=(task_id, url, is_mp3))
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/progress/<task_id>')
def get_progress(task_id):
    if task_id not in progress_data:
        return jsonify({'error': 'معرف المهمة غير صالح'})
    return jsonify(progress_data[task_id])

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)