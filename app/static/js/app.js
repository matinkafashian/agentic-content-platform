(() => {
  document.querySelectorAll('[data-delivery-form]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (form.dataset.sending === 'true') {
        event.preventDefault();
        return;
      }
      if (event.defaultPrevented || event.submitter?.value !== 'send_now') return;
      form.dataset.sending = 'true';
      form.setAttribute('aria-busy', 'true');
      const stack = document.createElement('div');
      stack.className = 'toast-stack';
      const notice = document.createElement('div');
      notice.className = 'alert toast-notification';
      notice.setAttribute('role', 'status');
      notice.textContent = '⏳ پیام‌ها در حال ارسال هستند؛ لطفاً تا نمایش نتیجه این صفحه را باز نگه دارید.';
      stack.append(notice);
      document.body.append(stack);
      // Keep the submitter enabled so its delivery_action reaches the server.
      if (event.submitter) event.submitter.textContent = 'در حال ارسال…';
      window.addEventListener('pageshow', (pageEvent) => {
        if (pageEvent.persisted) window.location.reload();
      });
    });
  });
  const alerts = [
    ...document.querySelectorAll(
      ".alert[role='alert']:not([data-persistent]), .alert[role='status']:not([data-persistent])",
    ),
  ];
  if (alerts.length) {
    const stack = document.createElement("div");
    stack.className = "toast-stack";
    stack.setAttribute("aria-label", "اعلان‌های سامانه");
    document.body.append(stack);
    alerts.forEach((alert) => {
      alert.classList.add("toast-notification");
      const closeButton = document.createElement("button");
      closeButton.type = "button";
      closeButton.className = "toast-close";
      closeButton.setAttribute("aria-label", "بستن اعلان");
      closeButton.textContent = "×";
      const dismiss = () => {
        alert.classList.add("is-leaving");
        window.setTimeout(() => alert.remove(), 180);
      };
      closeButton.addEventListener("click", dismiss);
      alert.append(closeButton);
      stack.append(alert);
      if (!alert.classList.contains("alert-error")) {
        window.setTimeout(dismiss, 7000);
      }
    });
  }

  document.querySelectorAll("[data-long-running-form]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("[data-long-running-submit]");
      const status = form.parentElement?.querySelector("[data-operation-status]");
      const elapsed = status?.querySelector("[data-operation-elapsed]");
      if (!button || button.disabled) return;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = form.dataset.pendingLabel || "در حال پردازش…";
      if (status) status.hidden = false;
      const startedAt = Date.now();
      window.setInterval(() => {
        if (!elapsed) return;
        const seconds = Math.floor((Date.now() - startedAt) / 1000);
        elapsed.textContent = `${seconds.toLocaleString("fa-IR")} ثانیه`;
      }, 1000);
    });
  });

  document.querySelectorAll("[data-content-mode-form]").forEach((section) => {
    const form = section.closest("form");
    const radios = [...section.querySelectorAll("input[name='content_mode']")];
    const panels = [...section.querySelectorAll("[data-content-mode-panel]")];
    const submit = form?.querySelector("[data-content-mode-submit]");
    const updateMode = () => {
      const selected = radios.find((radio) => radio.checked)?.value || "ai";
      panels.forEach((panel) => {
        const active = panel.dataset.contentModePanel === selected;
        panel.hidden = !active;
        panel.querySelectorAll("textarea").forEach((field) => {
          field.disabled = !active;
          field.required = active && selected === "ai";
        });
      });
      if (submit) {
        submit.textContent = selected === "manual"
          ? "ثبت متن کامل من"
          : "ساخت پیش‌نویس با هوش مصنوعی";
      }
    };
    radios.forEach((radio) => radio.addEventListener("change", updateMode));
    updateMode();
  });

  document.querySelectorAll("[data-image-mode-select]").forEach((select) => {
    const form = select.closest("form");
    if (!form) return;
    const groups = [...form.querySelectorAll("[data-image-mode-fields]")];
    const submit = form.querySelector("[data-long-running-submit]");
    const updateMode = () => {
      groups.forEach((group) => {
        const active = group.dataset.imageModeFields === select.value;
        group.hidden = !active;
        group.querySelectorAll("input, select, textarea").forEach((field) => {
          field.disabled = !active;
          if (field.name === "overlay_text" || field.name === "topic" || field.name === "message") {
            field.required = active;
          }
        });
      });
      const cinematic = select.value === "cinematic";
      form.dataset.pendingLabel = cinematic
        ? "در حال ساخت پوستر سینمایی…"
        : "در حال ساخت نسخه استودیویی…";
      if (submit) {
        const hasExistingImage = submit.textContent.includes("دوباره");
        submit.textContent = cinematic
          ? `${hasExistingImage ? "ساخت دوباره" : "ساخت"} پوستر سینمایی`
          : `${hasExistingImage ? "ساخت دوباره" : "ساخت"} نسخه استودیویی`;
      }
    };
    select.addEventListener("change", updateMode);
    updateMode();
  });

  document.querySelectorAll("[data-publishing-platform]").forEach((select) => {
    const form = select.closest("form");
    const destination = form?.querySelector("[data-publishing-destination]");
    if (!destination) return;
    let defaults = {};
    try {
      defaults = JSON.parse(select.dataset.publishingDestinations || "{}");
    } catch (_error) {
      defaults = {};
    }
    let previousDefault = defaults[select.value] || "";
    select.addEventListener("change", () => {
      const nextDefault = defaults[select.value] || "";
      if (!destination.value.trim() || destination.value === previousDefault) {
        destination.value = nextDefault;
      }
      previousDefault = nextDefault;
    });
  });

  const imageLightboxTriggers = [...document.querySelectorAll("[data-image-lightbox]")];
  if (imageLightboxTriggers.length) {
    const lightbox = document.createElement("dialog");
    lightbox.className = "image-lightbox";
    lightbox.setAttribute("aria-label", "نمایش کامل تصویر");
    lightbox.innerHTML = `
      <div class="image-lightbox-shell">
        <div class="image-lightbox-toolbar">
          <strong data-image-lightbox-title></strong>
          <button type="button" class="image-lightbox-close" data-image-lightbox-close aria-label="بستن نمایش کامل">×</button>
        </div>
        <div class="image-lightbox-canvas">
          <img data-image-lightbox-preview alt="">
        </div>
      </div>`;
    document.body.append(lightbox);

    const preview = lightbox.querySelector("[data-image-lightbox-preview]");
    const title = lightbox.querySelector("[data-image-lightbox-title]");
    const closeButton = lightbox.querySelector("[data-image-lightbox-close]");
    let previousFocus;

    const closeLightbox = () => {
      if (lightbox.open) lightbox.close();
    };

    imageLightboxTriggers.forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const sourceImage = trigger.querySelector("img");
        if (!sourceImage || !preview || !title) return;
        previousFocus = trigger;
        preview.src = sourceImage.currentSrc || sourceImage.src;
        preview.alt = sourceImage.alt;
        title.textContent = trigger.dataset.imageTitle || sourceImage.alt;
        document.body.classList.add("has-open-lightbox");
        lightbox.showModal();
        closeButton?.focus();
      });
    });

    closeButton?.addEventListener("click", closeLightbox);
    lightbox.addEventListener("click", (event) => {
      if (event.target === lightbox) closeLightbox();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && lightbox.open) {
        event.preventDefault();
        closeLightbox();
      }
    });
    lightbox.addEventListener("close", () => {
      document.body.classList.remove("has-open-lightbox");
      if (preview) preview.removeAttribute("src");
      previousFocus?.focus();
    });
  }

  const toggle = document.querySelector("[data-nav-toggle]");
  const sidebar = document.querySelector("[data-sidebar]");
  const scrim = document.querySelector("[data-nav-scrim]");

  const closeNavigation = () => {
    if (!toggle || !sidebar || !scrim) return;
    sidebar.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "باز کردن منو");
    scrim.hidden = true;
  };

  if (toggle && sidebar && scrim) {
    toggle.addEventListener("click", () => {
      const willOpen = !sidebar.classList.contains("is-open");
      sidebar.classList.toggle("is-open", willOpen);
      toggle.setAttribute("aria-expanded", String(willOpen));
      toggle.setAttribute("aria-label", willOpen ? "بستن منو" : "باز کردن منو");
      scrim.hidden = !willOpen;
    });
    scrim.addEventListener("click", closeNavigation);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeNavigation();
    });
  }

  const imageInput = document.querySelector("[data-image-input]");
  const imagePreview = document.querySelector("[data-image-preview]");
  const uploadCopy = document.querySelector("[data-upload-copy]");
  const uploadZone = document.querySelector("[data-upload-zone]");
  let previewUrl;

  const previewFile = (file) => {
    if (!file || !imagePreview) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    imagePreview.src = previewUrl;
    imagePreview.hidden = false;
    uploadCopy?.classList.add("is-hidden");
  };

  imageInput?.addEventListener("change", () => previewFile(imageInput.files?.[0]));
  if (uploadZone && imageInput) {
    ["dragenter", "dragover"].forEach((name) => uploadZone.addEventListener(name, (event) => {
      event.preventDefault();
      uploadZone.classList.add("is-dragging");
    }));
    ["dragleave", "drop"].forEach((name) => uploadZone.addEventListener(name, (event) => {
      event.preventDefault();
      uploadZone.classList.remove("is-dragging");
    }));
    uploadZone.addEventListener("drop", (event) => {
      const file = event.dataTransfer?.files?.[0];
      if (!file) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      imageInput.files = transfer.files;
      previewFile(file);
    });
  }

  const attributeList = document.querySelector("[data-attribute-list]");
  document.querySelector("[data-add-attribute]")?.addEventListener("click", () => {
    if (!attributeList) return;
    const row = document.createElement("div");
    row.className = "attribute-row";
    row.innerHTML = '<input name="attribute_key" aria-label="نام ویژگی" placeholder="مثلاً رنگ"><input name="attribute_value" aria-label="مقدار ویژگی" placeholder="مثلاً گردویی"><button class="icon-button remove-row" type="button" data-remove-row aria-label="حذف این ویژگی">×</button>';
    attributeList.append(row);
    row.querySelector("input")?.focus();
  });
  attributeList?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-row]");
    if (!button) return;
    const rows = attributeList.querySelectorAll(".attribute-row");
    if (rows.length === 1) {
      rows[0].querySelectorAll("input").forEach((input) => { input.value = ""; });
      return;
    }
    button.closest(".attribute-row")?.remove();
  });
})();
