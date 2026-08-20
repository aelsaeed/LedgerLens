const elements = {
  demoButton: document.querySelector("#demoButton"),
  serviceStatus: document.querySelector("#serviceStatus"),
  fileInput: document.querySelector("#fileInput"),
  fileLabel: document.querySelector("#fileLabel"),
  dropZone: document.querySelector("#dropZone"),
  imageWrap: document.querySelector("#imageWrap"),
  imagePreview: document.querySelector("#imagePreview"),
  evidenceOverlay: document.querySelector("#evidenceOverlay"),
  sampleInvoice: document.querySelector("#sampleInvoice"),
  loadingState: document.querySelector("#loadingState"),
  errorState: document.querySelector("#errorState"),
  resultContent: document.querySelector("#resultContent"),
  scoreRing: document.querySelector("#scoreRing"),
  scoreValue: document.querySelector("#scoreValue"),
  reviewStatus: document.querySelector("#reviewStatus"),
  processingMeta: document.querySelector("#processingMeta"),
  fieldGrid: document.querySelector("#fieldGrid"),
  checksList: document.querySelector("#checksList"),
  checkCount: document.querySelector("#checkCount"),
  evidenceList: document.querySelector("#evidenceList"),
  evidenceTab: document.querySelector("#evidenceTab"),
  jsonTab: document.querySelector("#jsonTab"),
  evidencePanel: document.querySelector("#evidencePanel"),
  jsonPanel: document.querySelector("#jsonPanel"),
  jsonOutput: document.querySelector("#jsonOutput"),
  copyJson: document.querySelector("#copyJson"),
};

const fields = [
  ["vendor_name", "Vendor"],
  ["invoice_number", "Invoice number"],
  ["invoice_date", "Invoice date"],
  ["due_date", "Due date"],
  ["subtotal", "Subtotal"],
  ["tax_amount", "Tax"],
  ["total_amount", "Grand total"],
  ["currency", "Currency"],
  ["line_items", "Line items"],
];

let currentResult = null;
let previewUrl = null;

function makeElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatDate(value) {
  if (!value) return null;
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

function formatMoney(value, currency) {
  if (value === null || value === undefined) return null;
  const number = Number(value);
  if (Number.isNaN(number)) return value;
  if (!currency) return number.toFixed(2);
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
    }).format(number);
  } catch {
    return `${currency} ${number.toFixed(2)}`;
  }
}

function displayValue(key, result) {
  const value = result[key];
  if (key === "invoice_date" || key === "due_date") return formatDate(value);
  if (["subtotal", "tax_amount", "total_amount"].includes(key)) {
    return formatMoney(value, result.currency);
  }
  if (key === "line_items") {
    return value?.length ? `${value.length} item${value.length === 1 ? "" : "s"}` : null;
  }
  return value;
}

function humanizeCode(code) {
  return code
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function showState(state, message = "") {
  elements.loadingState.hidden = state !== "loading";
  elements.errorState.hidden = state !== "error";
  elements.resultContent.hidden = state !== "ready";
  if (state === "error") elements.errorState.textContent = message;
}

function selectEvidence(key) {
  switchTab("evidence");
  document.querySelectorAll(".evidence-item").forEach((item) => {
    item.classList.toggle("is-highlighted", item.dataset.field === key);
  });
  const target = elements.evidenceList.querySelector(`[data-field="${key}"]`);
  if (target) target.focus({ preventScroll: true });
  renderEvidenceBox(key);
}

function renderEvidenceBox(key) {
  elements.evidenceOverlay.replaceChildren();
  const box = currentResult?.quality?.evidence?.[key]?.bounding_box;
  if (!box || elements.imageWrap.hidden || !elements.imagePreview.naturalWidth) return;
  const marker = makeElement("span", "evidence-box");
  marker.style.left = `${(box.x / elements.imagePreview.naturalWidth) * 100}%`;
  marker.style.top = `${(box.y / elements.imagePreview.naturalHeight) * 100}%`;
  marker.style.width = `${(box.width / elements.imagePreview.naturalWidth) * 100}%`;
  marker.style.height = `${(box.height / elements.imagePreview.naturalHeight) * 100}%`;
  elements.evidenceOverlay.append(marker);
}

function renderFields(result) {
  elements.fieldGrid.replaceChildren();
  const evidence = result.quality?.evidence || {};
  fields.forEach(([key, label]) => {
    const value = displayValue(key, result);
    const card = makeElement("div", "field-card");
    card.append(makeElement("span", "field-label", label));
    card.append(makeElement("span", `field-value${value ? "" : " is-missing"}`, value || "Not found"));
    if (evidence[key]) {
      card.classList.add("has-evidence");
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", `${label}: ${value}. Show source evidence.`);
      card.addEventListener("click", () => selectEvidence(key));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectEvidence(key);
        }
      });
    }
    elements.fieldGrid.append(card);
  });
}

function renderChecks(result) {
  const quality = result.quality || { checks: [], warnings: [] };
  const checks = [...quality.checks];
  (quality.warnings || []).forEach((warning, index) => {
    checks.unshift({
      code: `REVIEW_NOTE_${index + 1}`,
      status: "warning",
      message: warning,
      delta: null,
    });
  });
  elements.checksList.replaceChildren();
  elements.checkCount.textContent = `${checks.length} check${checks.length === 1 ? "" : "s"}`;
  checks.forEach((check) => {
    const row = makeElement("div", `check-row ${check.status}`);
    const symbol = check.status === "pass" ? "✓" : check.status === "warning" ? "!" : "–";
    row.append(makeElement("span", "check-icon", symbol));
    const copy = makeElement("div", "check-copy");
    copy.append(makeElement("strong", "", humanizeCode(check.code.replace(/_\d+$/, ""))));
    copy.append(makeElement("p", "", check.message));
    row.append(copy);
    row.append(
      makeElement(
        "span",
        "check-delta",
        check.delta !== null && check.delta !== undefined ? `Δ ${check.delta}` : check.status,
      ),
    );
    elements.checksList.append(row);
  });
}

function renderEvidence(result) {
  elements.evidenceList.replaceChildren();
  const evidence = result.quality?.evidence || {};
  Object.entries(evidence).forEach(([key, item]) => {
    const card = makeElement("article", "evidence-item");
    card.dataset.field = key;
    card.tabIndex = -1;
    const metadata = makeElement("div", "evidence-meta");
    metadata.append(makeElement("span", "", key.replaceAll("_", " ")));
    const confidence =
      item.confidence === null || item.confidence === undefined
        ? item.method.replaceAll("_", " ")
        : `${Math.round(item.confidence * 100)}% OCR`;
    metadata.append(makeElement("span", "", confidence));
    card.append(metadata, makeElement("p", "", `“${item.source_text}”`));
    elements.evidenceList.append(card);
  });
}

function renderResult(result) {
  currentResult = result;
  const quality = result.quality || { score: 0, review_required: true };
  elements.scoreRing.style.setProperty("--score", quality.score);
  elements.scoreValue.textContent = quality.score;
  elements.reviewStatus.textContent = quality.review_required ? "Review required" : "Ready to automate";
  elements.reviewStatus.classList.toggle("needs-review", quality.review_required);
  elements.reviewStatus.classList.toggle("is-clear", !quality.review_required);

  const processing = result.processing;
  if (processing) {
    const details = [
      processing.ocr_engine === "provided_text" ? "Audited text" : processing.ocr_engine,
      `${Math.round(processing.duration_ms)} ms`,
    ];
    if (processing.ocr_confidence !== null && processing.ocr_confidence !== undefined) {
      details.push(`${Math.round(processing.ocr_confidence * 100)}% OCR`);
    }
    elements.processingMeta.textContent = details.join(" · ");
  }

  renderFields(result);
  renderChecks(result);
  renderEvidence(result);
  elements.jsonOutput.textContent = JSON.stringify(result, null, 2);
  showState("ready");
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with status ${response.status}.`);
  }
  return payload;
}

async function loadDemo() {
  showState("loading");
  elements.fileLabel.textContent = "northstar-cloud-demo.txt";
  elements.sampleInvoice.hidden = false;
  elements.imageWrap.hidden = true;
  elements.evidenceOverlay.replaceChildren();
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
  try {
    renderResult(await requestJson("/api/v1/demo"));
  } catch (error) {
    showState("error", error.message);
  }
}

async function updateHealth() {
  try {
    const health = await requestJson("/api/v1/health");
    const available = health.ocr === "available";
    elements.serviceStatus.classList.toggle("is-unavailable", !available);
    elements.serviceStatus.querySelector("span").textContent = available
      ? "OCR ready"
      : "Text mode ready";
  } catch {
    elements.serviceStatus.classList.add("is-unavailable");
    elements.serviceStatus.querySelector("span").textContent = "Status unavailable";
  }
}

async function scanFile(file) {
  if (!file) return;
  const supported = ["image/png", "image/jpeg", "image/tiff", "image/webp", "image/bmp"];
  if (!supported.includes(file.type)) {
    showState("error", "Choose a PNG, JPEG, TIFF, WebP, or BMP image.");
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showState("error", "This file is larger than the 10 MB upload limit.");
    return;
  }

  elements.fileLabel.textContent = file.name;
  elements.sampleInvoice.hidden = true;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  elements.imagePreview.src = previewUrl;
  elements.imageWrap.hidden = false;
  elements.evidenceOverlay.replaceChildren();
  showState("loading");

  const form = new FormData();
  form.append("file", file);
  try {
    renderResult(await requestJson("/api/v1/scan", { method: "POST", body: form }));
  } catch (error) {
    showState("error", error.message);
  } finally {
    elements.fileInput.value = "";
  }
}

function switchTab(tabName) {
  const evidenceSelected = tabName === "evidence";
  elements.evidenceTab.classList.toggle("is-active", evidenceSelected);
  elements.jsonTab.classList.toggle("is-active", !evidenceSelected);
  elements.evidenceTab.setAttribute("aria-selected", String(evidenceSelected));
  elements.jsonTab.setAttribute("aria-selected", String(!evidenceSelected));
  elements.evidencePanel.hidden = !evidenceSelected;
  elements.jsonPanel.hidden = evidenceSelected;
}

elements.fileInput.addEventListener("change", (event) => scanFile(event.target.files[0]));
elements.demoButton.addEventListener("click", loadDemo);
elements.evidenceTab.addEventListener("click", () => switchTab("evidence"));
elements.jsonTab.addEventListener("click", () => switchTab("json"));

[elements.evidenceTab, elements.jsonTab].forEach((tab) => {
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const target = tab === elements.evidenceTab ? elements.jsonTab : elements.evidenceTab;
    target.focus();
    switchTab(target === elements.evidenceTab ? "evidence" : "json");
  });
});

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("is-dragging");
  });
});

elements.dropZone.addEventListener("drop", (event) => scanFile(event.dataTransfer.files[0]));

elements.copyJson.addEventListener("click", async () => {
  if (!currentResult) return;
  try {
    await navigator.clipboard.writeText(JSON.stringify(currentResult, null, 2));
    elements.copyJson.textContent = "Copied";
    window.setTimeout(() => {
      elements.copyJson.textContent = "Copy JSON";
    }, 1500);
  } catch {
    elements.copyJson.textContent = "Copy unavailable";
  }
});

loadDemo();
updateHealth();
