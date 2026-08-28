(() => {
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
