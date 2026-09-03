(() => {
  const root = document.querySelector("[data-voice-recorder]");
  if (!root) return;

  const startButton = root.querySelector("[data-record-start]");
  const stopButton = root.querySelector("[data-record-stop]");
  const preview = root.querySelector("[data-record-preview]");
  const previewWrap = root.querySelector("[data-record-preview-wrap]");
  const fileInput = root.querySelector("[data-record-file]");
  const durationInput = root.querySelector("[data-record-duration]");
  const saveButton = root.querySelector("[data-record-save]");
  const indicator = root.querySelector("[data-recording-indicator]");
  const timer = root.querySelector("[data-record-timer]");
  const message = root.querySelector("[data-record-message]");
  const unsavedWarning = root.querySelector("[data-record-unsaved]");
  const discardButton = root.querySelector("[data-record-discard]");
  const bundleButtons = document.querySelectorAll("[data-bundle-create]");
  const maximumDuration = 600000;
  let recorder;
  let stream;
  let chunks = [];
  let startedAt = 0;
  let stopTimer;
  let timerInterval;
  let previewUrl;

  const say = (text) => { message.textContent = text; };
  const formatTime = (milliseconds) => {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    const number = (value) => value.toLocaleString("fa-IR", {
      minimumIntegerDigits: 2,
      useGrouping: false,
    });
    return `${number(minutes)}:${number(seconds)}`;
  };
  const updateTimer = (milliseconds) => {
    timer.textContent = formatTime(milliseconds);
    timer.setAttribute("datetime", `PT${Math.floor(milliseconds / 1000)}S`);
  };
  const stopClock = () => {
    clearInterval(timerInterval);
    timerInterval = undefined;
  };
  const revokePreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = undefined;
  };
  const stopTracks = () => {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = undefined;
  };
  const blockBundle = (blocked) => {
    bundleButtons.forEach((button) => {
      button.disabled = blocked;
      if (blocked) {
        button.setAttribute("aria-describedby", "voice-unsaved-note");
      } else {
        button.removeAttribute("aria-describedby");
      }
    });
  };
  const showUnsavedState = (visible) => {
    if (unsavedWarning) {
      unsavedWarning.hidden = !visible;
      unsavedWarning.id = "voice-unsaved-note";
    }
    if (discardButton) discardButton.hidden = !visible;
    blockBundle(visible);
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
    previewWrap.hidden = false;
  };

  const finishRecording = () => {
    clearTimeout(stopTimer);
    stopClock();
    stopTracks();
    const elapsed = Math.min(Date.now() - startedAt, maximumDuration);
    updateTimer(elapsed);
    durationInput.value = String(elapsed);
    const mimeType = recorder.mimeType || "audio/webm";
    const extension = mimeType.includes("ogg") ? "ogg" : "webm";
    const blob = new Blob(chunks, { type: mimeType });
    if (!blob.size) {
      startButton.disabled = false;
      stopButton.disabled = true;
      saveButton.disabled = true;
      indicator.hidden = true;
      showUnsavedState(false);
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
    showUnsavedState(true);
    say("ضبط تمام شد. برای اضافه‌شدن به بسته نهایی، دکمه «ذخیره و پیوست وویس» را بزنید.");
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
      previewWrap.hidden = true;
      revokePreview();
      showUnsavedState(false);
      blockBundle(true);
      const mimeType = preferredMimeType();
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener("stop", finishRecording, { once: true });
      recorder.addEventListener("error", () => {
        stopTracks();
        stopClock();
        startButton.disabled = false;
        stopButton.disabled = true;
        saveButton.disabled = true;
        indicator.hidden = true;
        showUnsavedState(false);
        say("ضبط کامل نشد. دوباره تلاش کنید.");
      }, { once: true });
      recorder.start(1000);
      startedAt = Date.now();
      updateTimer(0);
      timerInterval = setInterval(() => {
        updateTimer(Math.min(Date.now() - startedAt, maximumDuration));
      }, 250);
      startButton.disabled = true;
      stopButton.disabled = false;
      indicator.hidden = false;
      say("ضبط شروع شد. حداکثر زمان مجاز ۱۰ دقیقه است.");
      stopTimer = setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, maximumDuration);
    } catch (_error) {
      stopTracks();
      stopClock();
      startButton.disabled = false;
      stopButton.disabled = true;
      indicator.hidden = true;
      showUnsavedState(false);
      say("دسترسی میکروفن داده نشد. اجازه میکروفن مرورگر را فعال و دوباره تلاش کنید.");
    }
  });

  stopButton.addEventListener("click", () => {
    if (recorder?.state === "recording") recorder.stop();
  });

  discardButton?.addEventListener("click", () => {
    chunks = [];
    fileInput.value = "";
    durationInput.value = "";
    preview.removeAttribute("src");
    preview.hidden = true;
    previewWrap.hidden = true;
    saveButton.disabled = true;
    revokePreview();
    showUnsavedState(false);
    updateTimer(0);
    say("ضبط فعلی کنار گذاشته شد. بسته نهایی می‌تواند بدون وویس ساخته شود.");
  });

  window.addEventListener("pagehide", () => {
    if (recorder?.state === "recording") recorder.stop();
    stopTracks();
    stopClock();
    revokePreview();
  });
})();
