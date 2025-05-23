// زر لصق الرابط من الحافظة
document.getElementById('pasteBtn').addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    document.getElementById('urlInput').value = text;
  } catch (err) {
    alert('تعذر الوصول إلى الحافظة: ' + err);
  }
});

// التعامل مع نموذج التحميل
document.getElementById('downloadForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const url = document.getElementById('urlInput').value.trim();
  const format = document.getElementById('formatSelect').value;
  const progressBar = document.getElementById('progressBar');
  const progressPercent = document.getElementById('progressPercent');
  const loadingText = document.getElementById('loadingText');
  const downloadLink = document.getElementById('downloadLink');

  downloadLink.style.display = 'none';
  progressBar.style.display = 'block';
  progressBar.value = 0;
  progressPercent.textContent = '0%';
  loadingText.textContent = '⏳ جاري التحميل... الرجاء الانتظار';
  loadingText.style.color = '';

  if (!url) {
    alert('من فضلك أدخل رابط صحيح');
    return;
  }

  try {
    const response = await fetch('/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ url, format }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'حدث خطأ غير معروف');
    }

    const taskId = data.task_id;

    // متابعة التقدم
    const interval = setInterval(async () => {
      try {
        const progRes = await fetch(`/progress/${taskId}`);
        const progData = await progRes.json();

        if (progData.error) {
          clearInterval(interval);
          loadingText.textContent = '❌ حدث خطأ أثناء التنزيل: ' + progData.error;
          loadingText.style.color = 'red';
          progressBar.style.display = 'none';
          progressPercent.textContent = 'خطأ';
          return;
        }

        const progress = progData.progress || 0;
        progressBar.value = progress;
        progressPercent.textContent = progress.toFixed(1) + '%';
        loadingText.textContent = `⬇️ جاري التحميل... ${progress.toFixed(1)}%`;

        if (progress >= 100) {
          clearInterval(interval);
          loadingText.textContent = '✅ تم الانتهاء من التنزيل!';
          loadingText.style.color = 'green';
          if (progData.download_url) {
            downloadLink.href = progData.download_url;
            downloadLink.style.display = 'inline-block';
            downloadLink.textContent = '⬇️ تحميل الملف';
          }
        }
      } catch (err) {
        clearInterval(interval);
        loadingText.textContent = '❌ خطأ في جلب التقدم: ' + err.message;
        loadingText.style.color = 'red';
        progressBar.style.display = 'none';
        progressPercent.textContent = 'خطأ';
      }
    }, 1000);

  } catch (err) {
    loadingText.textContent = '❌ حدث خطأ: ' + err.message;
    loadingText.style.color = 'red';
    progressBar.style.display = 'none';
    progressPercent.textContent = 'خطأ';
  }
});