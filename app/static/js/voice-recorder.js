(() => {
  const root = document.querySelector("[data-voice-recorder]");
  if (!root) return;

  const startButton = root.querySelector("[data-record-start]");
  const stopButton = root.querySelector("[data-record-stop]");
  const preview = root.querySelector("[data-record-preview]");
  const fileInput = root.querySelector("[data-record-file]");
  const durationInput = root.querySelector("[data-record-duration]");
  const saveButton = root.querySelector("[data-record-save]");
  const indicator = root.querySelector("[data-recording-indicator]");
  const message = root.querySelector("[data-record-message]");
  const maximumDuration = 600000;
  let recorder;
  let stream;
  let chunks = [];
  let startedAt = 0;
  let stopTimer;
  let previewUrl;

  const say = (text) => { message.textContent = text; };
  const revokePreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = undefined;
  };
  const stopTracks = () => {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = undefined;
  };
  const preferredMimeType = () => [
    "audio/webm;codecs=opus",
    "audio/ogg;codecs=opus",
    "audio/webm",
  ].find((type) => MediaRecorder.isTypeSupported(type));

  const showPreview = (blob) => {
    revokePreview();
    previewUrl = URL.createObjectURL(blob);
    preview.src = previewUrl;
    preview.hidden = false;
  };

  const finishRecording = () => {
    clearTimeout(stopTimer);
    stopTracks();
    const elapsed = Math.min(Date.now() - startedAt, maximumDuration);
    durationInput.value = String(elapsed);
    const mimeType = recorder.mimeType || "audio/webm";
    const extension = mimeType.includes("ogg") ? "ogg" : "webm";
    const blob = new Blob(chunks, { type: mimeType });
    if (!blob.size) {
      startButton.disabled = false;
      stopButton.disabled = true;
      saveButton.disabled = true;
      indicator.hidden = true;
      say("صدایی ثبت نشد. دوباره ضبط را شروع کنید و چند ثانیه صحبت کنید.");
      return;
    }
    const file = new File([blob], `recording.${extension}`, { type: mimeType });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    showPreview(blob);
    startButton.disabled = false;
    stopButton.disabled = true;
    saveButton.disabled = false;
    indicator.hidden = true;
    say("ضبط تمام شد. برای نگهداری این وویس، دکمه «ذخیره وویس» را بزنید.");
  };

  startButton.addEventListener("click", async () => {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      say("مرورگر شما ضبط مستقیم را پشتیبانی نمی‌کند. صفحه را با مرورگر به‌روز Chrome، Edge یا Firefox باز کنید.");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      fileInput.value = "";
      durationInput.value = "";
      saveButton.disabled = true;
      preview.hidden = true;
      revokePreview();
      const mimeType = preferredMimeType();
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener("stop", finishRecording, { once: true });
      recorder.addEventListener("error", () => {
        stopTracks();
        startButton.disabled = false;
        stopButton.disabled = true;
        saveButton.disabled = true;
        indicator.hidden = true;
        say("ضبط کامل نشد. دوباره تلاش کنید یا فایل صوتی را انتخاب کنید.");
      }, { once: true });
      recorder.start(1000);
      startedAt = Date.now();
      startButton.disabled = true;
      stopButton.disabled = false;
      indicator.hidden = false;
      say("ضبط شروع شد. حداکثر زمان مجاز ۱۰ دقیقه است.");
      stopTimer = setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, maximumDuration);
    } catch (_error) {
      stopTracks();
      say("دسترسی میکروفن داده نشد. اجازه میکروفن مرورگر را فعال و دوباره تلاش کنید.");
    }
  });

  stopButton.addEventListener("click", () => {
    if (recorder?.state === "recording") recorder.stop();
  });

  window.addEventListener("pagehide", () => {
    if (recorder?.state === "recording") recorder.stop();
    stopTracks();
    revokePreview();
  });
})();
