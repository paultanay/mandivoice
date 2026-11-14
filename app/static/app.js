const $ = (id) => document.getElementById(id);
const audioInput = $("audioInput");
const selectedAudio = $("selectedAudio");
const audioPreview = $("audioPreview");
const transcribeButton = $("transcribeButton");
const transcriptField = $("transcript");
const lineItems = $("lineItems");
const MAX_RECORDING_SECONDS = 30;
let selectedBlob = null;
let selectedName = "";
let previewUrl = "";
let mediaStream = null;
let audioContext = null;
let processor = null;
let recordingChunks = [];
let recordingStartedAt = 0;
let recordingTimer = null;
let audioDurationValid = true;
let detectedLanguageCode = null;
let readbackUrl = "";
let activeOrderDraft = null;
let interpretationIssues = [];

$("billDate").textContent = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
}).format(new Date());

function responseMessage(body, fallback) {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail))
    return body.detail.map((item) => item.msg).join(". ");
  return fallback;
}

function showMessage(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
}

function selectAudio(blob, name) {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  selectedBlob = blob;
  selectedName = name;
  previewUrl = URL.createObjectURL(blob);
  $("audioName").textContent = name;
  $("audioMeta").textContent =
    `${(blob.size / 1024).toFixed(0)} KB · ready to transcribe`;
  audioDurationValid = true;
  audioPreview.onloadedmetadata = () => {
    audioDurationValid =
      !Number.isFinite(audioPreview.duration) ||
      audioPreview.duration <= MAX_RECORDING_SECONDS;
    transcribeButton.disabled = !audioDurationValid;
    if (!audioDurationValid) {
      showMessage(
        $("transcribeMessage"),
        "Choose a recording that is 30 seconds or shorter.",
        true,
      );
    }
  };
  audioPreview.src = previewUrl;
  audioPreview.hidden = false;
  selectedAudio.hidden = false;
  transcribeButton.disabled = false;
  showMessage($("transcribeMessage"), "");
}

function clearAudio() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = "";
  selectedBlob = null;
  selectedName = "";
  audioInput.value = "";
  audioPreview.removeAttribute("src");
  audioPreview.hidden = true;
  selectedAudio.hidden = true;
  transcribeButton.disabled = true;
  showMessage($("transcribeMessage"), "");
}

function clearReadback() {
  if (readbackUrl) URL.revokeObjectURL(readbackUrl);
  readbackUrl = "";
  $("readbackAudio").removeAttribute("src");
  $("readbackAudio").hidden = true;
}

function getOpenClarifications(draft, items) {
  const lines = draft?.lines || [];
  const questions = draft?.clarifications || [];
  return [...new Set(questions)].filter((question) => {
    const normalized = question.toLocaleLowerCase();
    const matchingIndices = lines.flatMap((line, index) =>
      line.name && normalized.includes(line.name.toLocaleLowerCase())
        ? [index]
        : [],
    );
    if (!matchingIndices.length) return true;

    const asksPrice = /price|rate|cost/.test(normalized);
    const asksQuantity = /quantity|how many|count/.test(normalized);
    if (!asksPrice && !asksQuantity) return true;
    return matchingIndices.some((index) => {
      const line = lines[index];
      const item = items[index] || {};
      return (
        (asksPrice && (!item.unit_price?.trim() || !line.price_basis)) ||
        (asksQuantity && !item.quantity?.trim())
      );
    });
  });
}

function readBillItems(rows) {
  return rows.map((row) =>
    Object.fromEntries(
      [...row.querySelectorAll("input")].map((input) => [
        input.dataset.key,
        input.value.trim(),
      ]),
    ),
  );
}

function updateReviewControls() {
  const rows = [...lineItems.querySelectorAll(".item-row")];
  const items = readBillItems(rows);
  const complete =
    items.length > 0 &&
    items.every((item) => Object.values(item).every(Boolean));
  const openQuestions = activeOrderDraft
    ? getOpenClarifications(
        {
          ...activeOrderDraft,
          clarifications: [
            ...activeOrderDraft.clarifications,
            ...interpretationIssues,
          ],
        },
        items,
      )
    : [];
  const hasOpenQuestions = openQuestions.length > 0;
  $("calculateButton").disabled =
    !complete || !$("confirmOrder").checked || hasOpenQuestions;
  const hindiTranscript =
    detectedLanguageCode === "hi-IN" ||
    /[\u0900-\u097f]/.test(transcriptField.value);
  const advancedOrder =
    activeOrderDraft &&
    (activeOrderDraft.charges.length ||
      activeOrderDraft.returns.length ||
      activeOrderDraft.payments.length ||
      activeOrderDraft.order_discount_kind !== "none" ||
      activeOrderDraft.lines.some(
        (line) =>
          line.price_basis !== "unit" ||
          line.pack_size ||
          (line.price_unit && line.price_unit !== (line.unit || "unit")) ||
          line.tax_rate_percent !== null ||
          line.tax_inclusive ||
          line.discount_kind !== "none" ||
          Number(line.free_quantity || 0) > 0,
      ));
  $("readbackButton").disabled =
    !rows.length || !hindiTranscript || Boolean(advancedOrder);
  const readbackHint = $("readbackHint");
  readbackHint.hidden = !rows.length || !hindiTranscript || !advancedOrder;
}

function resetReviewState() {
  $("confirmOrder").checked = false;
  clearReadback();
  updateReviewControls();
}

function discardDraftForTranscriptEdit() {
  activeOrderDraft = null;
  interpretationIssues = [];
  $("orderDetails").hidden = true;
  $("orderDetails").replaceChildren();
  if (!lineItems.querySelector(".item-row")) return;
  lineItems.replaceChildren();
  showEmptyItems();
  $("gstRate").value = "0";
  $("subtotal").textContent = "₹0.00";
  $("gstAmount").textContent = "₹0.00";
  $("total").textContent = "₹0.00";
  resetReviewState();
}

function writeWav(samples, sampleRate) {
  const targetRate = 16000;
  const step = sampleRate / targetRate;
  const outputLength = Math.floor(samples.length / step);
  const pcm = new Int16Array(outputLength);
  for (let i = 0; i < outputLength; i += 1) {
    const start = i * step;
    const end = (i + 1) * step;
    let total = 0;
    let weight = 0;
    for (
      let sourceIndex = Math.floor(start);
      sourceIndex < Math.ceil(end);
      sourceIndex += 1
    ) {
      const overlap =
        Math.min(end, sourceIndex + 1) - Math.max(start, sourceIndex);
      total += samples[sourceIndex] * overlap;
      weight += overlap;
    }
    const sample = Math.max(-1, Math.min(1, total / weight));
    pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  const buffer = new ArrayBuffer(44 + pcm.byteLength);
  const view = new DataView(buffer);
  const write = (offset, text) => {
    for (let i = 0; i < text.length; i += 1)
      view.setUint8(offset + i, text.charCodeAt(i));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + pcm.byteLength, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, targetRate, true);
  view.setUint32(28, targetRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, pcm.byteLength, true);
  new Int16Array(buffer, 44).set(pcm);
  return new Blob([buffer], { type: "audio/wav" });
}

function setRecordingState(isRecording) {
  const button = $("recordButton");
  button.classList.toggle("is-recording", isRecording);
  button.querySelector("span:last-child").textContent = isRecording
    ? "Stop recording"
    : "Start recording";
  button.querySelector(".record-button-icon").textContent = isRecording
    ? "■"
    : "●";
  $("recordCard").classList.toggle("is-recording", isRecording);
  $("recordTitle").textContent = isRecording
    ? "Listening to your order"
    : "Ready when you are";
  $("recordHint").textContent = isRecording
    ? "Speak clearly, then stop when you’re done."
    : "Use your own words. Include a quantity and price for each item.";
  $("recordingProgress").hidden = !isRecording;
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
    showMessage(
      $("transcribeMessage"),
      "Microphone recording is unavailable in this browser. Choose an audio file instead.",
      true,
    );
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(mediaStream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    recordingChunks = [];
    processor.onaudioprocess = (event) => {
      recordingChunks.push(
        new Float32Array(event.inputBuffer.getChannelData(0)),
      );
      event.outputBuffer.getChannelData(0).fill(0);
    };
    source.connect(processor);
    processor.connect(audioContext.destination);
    recordingStartedAt = Date.now();
    setRecordingState(true);
    showMessage($("transcribeMessage"), "");
    recordingTimer = window.setInterval(updateRecordingTime, 250);
    updateRecordingTime();
  } catch {
    showMessage(
      $("transcribeMessage"),
      "Microphone access was not available. Allow access or choose an audio file.",
      true,
    );
    stopTracks();
  }
}

function updateRecordingTime() {
  const seconds = Math.min(
    MAX_RECORDING_SECONDS,
    Math.floor((Date.now() - recordingStartedAt) / 1000),
  );
  $("recordingTime").textContent = `00:${String(seconds).padStart(2, "0")}`;
  if (seconds >= MAX_RECORDING_SECONDS) stopRecording();
}

function stopTracks() {
  if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop());
  mediaStream = null;
}

async function stopRecording() {
  if (!audioContext) return;
  window.clearInterval(recordingTimer);
  processor?.disconnect();
  stopTracks();
  const sampleRate = audioContext.sampleRate;
  const samples = new Float32Array(
    recordingChunks.reduce((sum, chunk) => sum + chunk.length, 0),
  );
  let offset = 0;
  for (const chunk of recordingChunks) {
    samples.set(chunk, offset);
    offset += chunk.length;
  }
  await audioContext.close();
  audioContext = null;
  processor = null;
  setRecordingState(false);
  if (!samples.length) {
    showMessage(
      $("transcribeMessage"),
      "No audio was captured. Try again or choose an audio file.",
      true,
    );
    return;
  }
  selectAudio(writeWav(samples, sampleRate), "Microphone recording.wav");
}

$("recordButton").addEventListener("click", () =>
  audioContext ? stopRecording() : startRecording(),
);

audioInput.addEventListener("change", () => {
  const file = audioInput.files?.[0];
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) {
    clearAudio();
    showMessage(
      $("transcribeMessage"),
      "Choose an audio file smaller than 20 MB.",
      true,
    );
    return;
  }
  selectAudio(file, file.name);
});
$("removeAudio").addEventListener("click", clearAudio);

transcribeButton.addEventListener("click", async () => {
  if (!selectedBlob) return;
  if (!audioDurationValid) return;
  transcribeButton.disabled = true;
  transcribeButton.innerHTML =
    '<span class="spinner" aria-hidden="true"></span> Transcribing…';
  showMessage($("transcribeMessage"), "Sending audio to Gnani Prisma…");
  try {
    const form = new FormData();
    form.append("audio_file", selectedBlob, selectedName);
    const response = await fetch("/api/transcribe", {
      method: "POST",
      body: form,
    });
    const body = await response.json();
    if (!response.ok)
      throw new Error(
        responseMessage(body, "Transcription failed. Try again."),
      );
    transcriptField.value = body.transcript;
    detectedLanguageCode = body.detected_language_code;
    updateCharacterCount();
    $("languageLabel").textContent = body.detected_language_code
      ? `Detected language: ${body.detected_language_code}`
      : "Transcript ready · check names and numbers";
    await parseAndApply(body.transcript);
    transcriptField.focus();
  } catch (error) {
    showMessage(
      $("transcribeMessage"),
      error.message || "Could not transcribe this recording.",
      true,
    );
  } finally {
    transcribeButton.disabled = !selectedBlob || !audioDurationValid;
    transcribeButton.innerHTML =
      'Transcribe with Prisma <span aria-hidden="true">→</span>';
  }
});

function updateCharacterCount() {
  const count = transcriptField.value.length;
  $("characterCount").textContent = `${count} / 4000`;
  if (!$("languageLabel").textContent.startsWith("Detected language:")) {
    $("languageLabel").textContent = count
      ? "Transcript · edit as needed"
      : "Your transcript will appear here";
  }
}
transcriptField.addEventListener("input", () => {
  updateCharacterCount();
  discardDraftForTranscriptEdit();
});

function addLineItem(item = {}, sourceLine = null, draftIndex = null) {
  const row = document.createElement("div");
  row.className = "item-row";
  if (draftIndex !== null) row.dataset.draftIndex = String(draftIndex);
  const priceUnit = sourceLine?.price_unit || sourceLine?.unit || "unit";
  const priceLabel = sourceLine
    ? sourceLine.price_basis === "line_total"
      ? "Line total in rupees"
      : sourceLine.price_basis === "pack"
        ? "Price per pack in rupees"
        : sourceLine.price_basis === "unit"
          ? `Price per ${priceUnit} in rupees`
          : "Price (basis unclear) in rupees"
    : "Price per unit in rupees";
  for (const field of [
    { key: "name", label: "Item name", placeholder: "Item" },
    { key: "quantity", label: "Quantity", placeholder: "1", numeric: true },
    {
      key: "unit_price",
      label: priceLabel,
      placeholder: "0.00",
      numeric: true,
    },
  ]) {
    const input = document.createElement("input");
    input.className = `item-input${field.numeric ? " numeric" : ""}`;
    input.type = field.numeric ? "number" : "text";
    if (field.numeric) {
      input.min = "0.01";
      input.step = "any";
      input.inputMode = "decimal";
    }
    input.maxLength = field.numeric ? 20 : 80;
    input.placeholder = field.placeholder;
    input.value = item[field.key] ?? "";
    input.dataset.key = field.key;
    input.setAttribute("aria-label", field.label);
    row.append(input);
  }
  if (sourceLine?.source_quote) {
    const evidence = document.createElement("small");
    evidence.className = "item-evidence";
    evidence.textContent = `Heard: “${sourceLine.source_quote}”`;
    row.append(evidence);
  }
  const remove = document.createElement("button");
  remove.className = "remove-item";
  remove.type = "button";
  remove.textContent = "×";
  remove.setAttribute("aria-label", "Remove item");
  remove.addEventListener("click", () => {
    row.remove();
    if (!lineItems.children.length) showEmptyItems();
    resetReviewState();
  });
  row.append(remove);
  lineItems.append(row);
  updateReviewControls();
  return row;
}
function showEmptyItems() {
  lineItems.innerHTML =
    '<div class="empty-items">No items yet. Use a transcript or click “Add an item” below.</div>';
}
showEmptyItems();

$("addItemButton").addEventListener("click", () => {
  if (lineItems.querySelector(".empty-items")) lineItems.innerHTML = "";
  if (activeOrderDraft) {
    activeOrderDraft.lines.push({
      name: "",
      name_evidence: "",
      quantity: "",
      quantity_evidence: null,
      unit: null,
      unit_evidence: null,
      price_unit: null,
      price_unit_evidence: null,
      pack_size: null,
      pack_size_evidence: null,
      unit_price: "",
      unit_price_evidence: null,
      price_basis: "unit",
      tax_rate_percent: null,
      tax_evidence: null,
      tax_inclusive: false,
      discount_kind: "none",
      discount_value: null,
      discount_evidence: null,
      free_quantity: "0",
      free_quantity_evidence: null,
      source_quote: "",
    });
    const index = activeOrderDraft.lines.length - 1;
    addLineItem({}, null, index).querySelector("input").focus();
    showOrderDetails({ status: "ready_for_review", draft: activeOrderDraft });
    return;
  }
  addLineItem().querySelector("input").focus();
});

function addDraftEditor(entry, label, value, onChange, options = {}) {
  const field = document.createElement("label");
  field.className = "order-edit-field";
  const caption = document.createElement("span");
  caption.textContent = label;
  field.append(caption);
  let input;
  if (options.choices) {
    input = document.createElement("select");
    for (const choice of options.choices) {
      const option = document.createElement("option");
      option.value = choice.value;
      option.textContent = choice.label;
      input.append(option);
    }
    input.value = options.choices.some((choice) => choice.value === value)
      ? value
      : (options.choices[0]?.value ?? "");
  } else if (options.checkbox) {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(value);
  } else {
    input = document.createElement("input");
    input.type = options.numeric ? "number" : "text";
    input.value = value ?? "";
    if (options.numeric) {
      input.min = "0";
      input.step = "any";
      input.inputMode = "decimal";
    }
  }
  const eventName = options.choices || options.checkbox ? "change" : "input";
  input.addEventListener(eventName, () => {
    onChange(options.checkbox ? input.checked : input.value.trim() || null);
    $("confirmOrder").checked = false;
    clearReadback();
    updateReviewControls();
  });
  field.append(input);
  entry.append(field);
}

function appendOrderDetail(
  list,
  label,
  quote = "",
  editors = null,
  removeAction = null,
) {
  const entry = document.createElement("li");
  entry.textContent = label;
  if (quote) {
    const evidence = document.createElement("small");
    evidence.className = "order-detail-quote";
    evidence.textContent = `Heard: “${quote}”`;
    entry.append(evidence);
  }
  if (editors) {
    const grid = document.createElement("div");
    grid.className = "order-edit-grid";
    for (const editor of editors) addDraftEditor(grid, ...editor);
    entry.append(grid);
  }
  if (removeAction) {
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "order-remove-action";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      removeAction();
      $("confirmOrder").checked = false;
      showOrderDetails({ status: "ready_for_review", draft });
      updateReviewControls();
    });
    entry.append(remove);
  }
  list.append(entry);
}

function appendDraftAction(list, label, action) {
  const entry = document.createElement("li");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "order-add-action";
  button.textContent = label;
  button.addEventListener("click", () => {
    action();
    $("confirmOrder").checked = false;
    showOrderDetails({ status: "ready_for_review", draft: activeOrderDraft });
    updateReviewControls();
  });
  entry.append(button);
  list.append(entry);
}

function showOrderDetails(body) {
  const panel = $("orderDetails");
  panel.replaceChildren();
  panel.hidden = false;
  panel.classList.toggle("structured-order", Boolean(body.draft));
  const heading = document.createElement("p");
  heading.className = "order-detail-heading";
  heading.textContent =
    body.status === "ready_for_review"
      ? "Structured draft. Check every value."
      : "Review needed before a total can be trusted.";
  panel.append(heading);
  const list = document.createElement("ul");
  list.className = "order-detail-list";
  const draft = body.draft;
  for (const [index, line] of draft.lines.entries()) {
    const priceUnit = line.price_unit || line.unit || "unit";
    const priceBasis =
      line.price_basis === "line_total"
        ? "for the line"
        : line.price_basis === "pack"
          ? "per pack"
          : line.price_basis === "unit"
            ? `per ${priceUnit}`
            : "with unclear price basis";
    let description = `${line.name}: ${line.quantity ?? "quantity missing"} ${line.unit || ""} at ₹${line.unit_price ?? "price missing"} ${priceBasis}`;
    if (line.pack_size) description += `; pack size ${line.pack_size}`;
    if (line.tax_rate_percent !== null)
      description += `; GST ${line.tax_rate_percent}%${line.tax_inclusive ? " included" : " added"}`;
    else if (draft.default_tax_rate_percent !== null)
      description += `; GST ${draft.default_tax_rate_percent}%`;
    if (line.discount_kind !== "none")
      description += `; discount ${line.discount_value} ${line.discount_kind}`;
    if (Number(line.free_quantity || 0) > 0)
      description += `; ${line.free_quantity} free`;
    appendOrderDetail(list, description, line.source_quote, [
      [
        "Unit",
        line.unit,
        (value) => {
          line.unit = value;
        },
      ],
      [
        "Price unit",
        line.price_unit,
        (value) => {
          line.price_unit = value;
        },
      ],
      [
        "Package size",
        line.pack_size,
        (value) => {
          line.pack_size = value;
        },
      ],
      [
        "Price basis",
        line.price_basis,
        (value) => {
          line.price_basis = value;
        },
        {
          choices: [
            { value: "unit", label: "Per unit" },
            { value: "pack", label: "Per pack" },
            { value: "line_total", label: "Line total" },
          ],
        },
      ],
      [
        "Item GST %",
        line.tax_rate_percent,
        (value) => {
          line.tax_rate_percent = value;
        },
        { numeric: true },
      ],
      [
        "Price includes GST",
        line.tax_inclusive,
        (value) => {
          line.tax_inclusive = value;
        },
        { checkbox: true },
      ],
      [
        "Discount type",
        line.discount_kind,
        (value) => {
          line.discount_kind = value;
        },
        {
          choices: [
            { value: "none", label: "No discount" },
            { value: "percent", label: "Percent" },
            { value: "amount", label: "Rupees" },
          ],
        },
      ],
      [
        "Discount value",
        line.discount_value,
        (value) => {
          line.discount_value = value;
        },
        { numeric: true },
      ],
      [
        "Free quantity",
        line.free_quantity,
        (value) => {
          line.free_quantity = value || "0";
        },
        { numeric: true },
      ],
    ]);
  }
  appendOrderDetail(
    list,
    `Order discount: ${draft.order_discount_value ?? "none"} ${draft.order_discount_kind}`,
    draft.order_discount_evidence,
    [
      [
        "Discount type",
        draft.order_discount_kind,
        (value) => {
          draft.order_discount_kind = value;
        },
        {
          choices: [
            { value: "none", label: "No discount" },
            { value: "percent", label: "Percent" },
            { value: "amount", label: "Rupees" },
          ],
        },
      ],
      [
        "Discount value",
        draft.order_discount_value,
        (value) => {
          draft.order_discount_value = value;
        },
        { numeric: true },
      ],
      [
        "Apply after tax",
        draft.order_discount_after_tax,
        (value) => {
          draft.order_discount_after_tax = value;
        },
        { checkbox: true },
      ],
      [
        "Round bill to rupee",
        draft.round_off,
        (value) => {
          draft.round_off = value;
        },
        { checkbox: true },
      ],
    ],
  );
  for (const [index, charge] of draft.charges.entries())
    appendOrderDetail(
      list,
      `Charge: ${charge.name}, ₹${charge.amount ?? "missing"}`,
      charge.source_quote,
      [
        [
          "Charge name",
          charge.name,
          (value) => {
            charge.name = value || "Other charge";
          },
        ],
        [
          "Amount",
          charge.amount,
          (value) => {
            charge.amount = value;
          },
          { numeric: true },
        ],
        [
          "Tax rate %",
          charge.tax_rate_percent,
          (value) => {
            charge.tax_rate_percent = value;
          },
          { numeric: true },
        ],
        [
          "Amount includes tax",
          charge.tax_inclusive,
          (value) => {
            charge.tax_inclusive = value;
          },
          { checkbox: true },
        ],
      ],
      () => draft.charges.splice(index, 1),
    );
  for (const [index, returned] of draft.returns.entries())
    appendOrderDetail(
      list,
      `Return: ${returned.name}, ₹${returned.amount ?? "missing"}`,
      returned.source_quote,
      [
        [
          "Return name",
          returned.name,
          (value) => {
            returned.name = value || "Returned goods";
          },
        ],
        [
          "Amount",
          returned.amount,
          (value) => {
            returned.amount = value;
          },
          { numeric: true },
        ],
        [
          "Tax rate %",
          returned.tax_rate_percent,
          (value) => {
            returned.tax_rate_percent = value;
          },
          { numeric: true },
        ],
        [
          "Amount includes tax",
          returned.tax_inclusive,
          (value) => {
            returned.tax_inclusive = value;
          },
          { checkbox: true },
        ],
      ],
      () => draft.returns.splice(index, 1),
    );
  if (draft.previous_balance !== null)
    appendOrderDetail(
      list,
      `Previous balance: ₹${draft.previous_balance}`,
      draft.previous_balance_evidence,
      [
        [
          "Previous balance",
          draft.previous_balance,
          (value) => {
            draft.previous_balance = value;
          },
          { numeric: true },
        ],
      ],
      () => {
        draft.previous_balance = null;
        draft.previous_balance_evidence = null;
      },
    );
  for (const [index, payment] of draft.payments.entries())
    appendOrderDetail(
      list,
      `Payment: ${payment.method}, ₹${payment.amount ?? "missing"}`,
      payment.source_quote,
      [
        [
          "Payment method",
          payment.method,
          (value) => {
            payment.method = value || "other";
          },
        ],
        [
          "Amount received",
          payment.amount,
          (value) => {
            payment.amount = value;
          },
          { numeric: true },
        ],
      ],
      () => draft.payments.splice(index, 1),
    );
  if (draft.customer_gstin !== null)
    appendOrderDetail(
      list,
      `Customer GSTIN: ${draft.customer_gstin}`,
      draft.customer_gstin_evidence,
      [
        [
          "Customer GSTIN",
          draft.customer_gstin,
          (value) => {
            draft.customer_gstin = value;
          },
        ],
      ],
      () => {
        draft.customer_gstin = null;
        draft.customer_gstin_evidence = null;
      },
    );
  appendDraftAction(list, "Add charge", () =>
    draft.charges.push({
      name: "",
      amount: null,
      tax_rate_percent: null,
      tax_inclusive: false,
      source_quote: "",
    }),
  );
  appendDraftAction(list, "Add return", () =>
    draft.returns.push({
      name: "",
      amount: null,
      tax_rate_percent: null,
      tax_inclusive: false,
      source_quote: "",
    }),
  );
  appendDraftAction(list, "Add payment", () =>
    draft.payments.push({
      method: "other",
      amount: null,
      source_quote: "",
    }),
  );
  if (draft.previous_balance === null) {
    appendDraftAction(list, "Add previous balance", () => {
      draft.previous_balance = "0";
      draft.previous_balance_evidence = null;
    });
  }
  if (draft.customer_gstin === null) {
    appendDraftAction(list, "Add customer GSTIN", () => {
      draft.customer_gstin = "";
      draft.customer_gstin_evidence = null;
    });
  }
  if (!draft.lines.length)
    appendOrderDetail(
      list,
      "No item could be verified from the transcript. Add an item or switch to manual entry.",
    );
  panel.append(list);
  const visibleItems = readBillItems([
    ...lineItems.querySelectorAll(".item-row"),
  ]);
  const issueMessages = getOpenClarifications(
    {
      ...draft,
      clarifications: [...draft.clarifications, ...interpretationIssues],
    },
    visibleItems,
  );
  if (issueMessages.length) {
    const issues = document.createElement("ul");
    issues.className = "order-issues";
    for (const question of issueMessages) appendOrderDetail(issues, question);
    panel.append(issues);
  }
  if (draft.unsupported_requests.length) {
    const unsupported = document.createElement("section");
    unsupported.className = "unsupported-requests";
    const label = document.createElement("strong");
    label.textContent = "This app cannot perform these requests";
    unsupported.append(label);
    const list = document.createElement("ul");
    for (const request of draft.unsupported_requests)
      appendOrderDetail(list, request);
    unsupported.append(list);
    panel.append(unsupported);
  }
  if (issueMessages.length) {
    const manual = document.createElement("button");
    manual.type = "button";
    manual.className = "button button-quiet manual-order-button";
    manual.textContent = "Discard this draft and enter manually";
    manual.addEventListener("click", () => {
      activeOrderDraft = null;
      interpretationIssues = [];
      panel.hidden = true;
      lineItems.replaceChildren();
      showEmptyItems();
      $("gstRate").value = "0";
      resetReviewState();
      $("addItemButton").click();
    });
    panel.append(manual);
  }
}

async function parseAndApply(transcript) {
  const response = await fetch("/api/orders/interpret", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });
  const body = await response.json();
  if (!response.ok)
    throw new Error(responseMessage(body, "Could not read this transcript."));
  activeOrderDraft = body.draft;
  interpretationIssues = body.issues || [];
  if (!activeOrderDraft)
    throw new Error("The order service returned no draft.");
  lineItems.replaceChildren();
  activeOrderDraft.lines.forEach((line, index) => {
    addLineItem(
      { name: line.name, quantity: line.quantity, unit_price: line.unit_price },
      line,
      index,
    );
  });
  if (!activeOrderDraft.lines.length) showEmptyItems();
  $("gstRate").value = activeOrderDraft.default_tax_rate_percent || "0";
  detectedLanguageCode =
    detectedLanguageCode ||
    (/^[\u0900-\u097f\s.,!?;:]+$/.test(transcript) ? "hi-IN" : null);
  if (body.calculation) {
    $("subtotal").textContent = formatRupees(body.calculation.subtotal);
    $("gstAmount").textContent = formatRupees(body.calculation.tax_amount);
    $("total").textContent = formatRupees(body.calculation.amount_due);
  } else {
    $("subtotal").textContent = "—";
    $("gstAmount").textContent = "—";
    $("total").textContent = "—";
  }
  showOrderDetails(body);
  resetReviewState();
  showMessage(
    $("transcribeMessage"),
    body.status === "ready_for_review"
      ? "Order structured. Check the values and source phrases before confirming."
      : "The transcript is ready, but the draft needs clarification or a manual correction.",
  );
}

$("parseButton").addEventListener("click", async () => {
  const transcript = transcriptField.value.trim();
  if (!transcript) {
    showMessage($("transcribeMessage"), "Record or type an order first.", true);
    transcriptField.focus();
    return;
  }
  const button = $("parseButton");
  button.disabled = true;
  try {
    await parseAndApply(transcript);
  } catch (error) {
    showMessage($("transcribeMessage"), error.message, true);
  } finally {
    button.disabled = false;
  }
});

function formatRupees(value) {
  return `₹${value}`;
}
async function calculateBill() {
  const rows = [...lineItems.querySelectorAll(".item-row")];
  const items = readBillItems(rows);
  if (!items.length) {
    throw new Error(
      "Add an item first. Enter its quantity and price, then calculate the bill.",
    );
  }
  if (!$("confirmOrder").checked) {
    throw new Error(
      "Review the transcript and line items, then check the confirmation box.",
    );
  }
  let response;
  if (activeOrderDraft) {
    activeOrderDraft.clarifications = getOpenClarifications(
      {
        ...activeOrderDraft,
        clarifications: [
          ...activeOrderDraft.clarifications,
          ...interpretationIssues,
        ],
      },
      items,
    );
    interpretationIssues = activeOrderDraft.clarifications;
    const previousLines = activeOrderDraft.lines;
    activeOrderDraft.lines = items.map((item, index) => {
      const row = rows[index];
      const draftIndex = Number(row?.dataset.draftIndex);
      const original = Number.isInteger(draftIndex)
        ? previousLines[draftIndex]
        : null;
      if (row) row.dataset.draftIndex = String(index);
      return {
        ...(original || {
          name_evidence: "",
          quantity_evidence: null,
          unit: null,
          unit_evidence: null,
          price_unit: null,
          price_unit_evidence: null,
          pack_size: null,
          pack_size_evidence: null,
          unit_price_evidence: null,
          price_basis: "unit",
          tax_rate_percent: null,
          tax_evidence: null,
          tax_inclusive: false,
          discount_kind: "none",
          discount_value: null,
          discount_evidence: null,
          free_quantity: "0",
          free_quantity_evidence: null,
          source_quote: "",
        }),
        name: item.name,
        quantity: item.quantity,
        unit_price: item.unit_price,
      };
    });
    activeOrderDraft.default_tax_rate_percent = $("gstRate").value || null;
    response = await fetch("/api/orders/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draft: activeOrderDraft, review_confirmed: true }),
    });
  } else {
    response = await fetch("/api/bills/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, gst_percent: $("gstRate").value || "0" }),
    });
  }
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      responseMessage(body, "Check the item details and try again."),
    );
  $("subtotal").textContent = formatRupees(body.subtotal);
  $("gstAmount").textContent = formatRupees(body.tax_amount ?? body.gst_amount);
  $("total").textContent = formatRupees(body.amount_due ?? body.total);
  if (activeOrderDraft) {
    showOrderDetails({
      status: "ready_for_review",
      draft: activeOrderDraft,
      calculation: body,
      issues: [],
    });
  }
  showMessage($("billMessage"), "");
}
$("confirmOrder").addEventListener("change", updateReviewControls);
lineItems.addEventListener("input", () => {
  $("confirmOrder").checked = false;
  clearReadback();
  if (activeOrderDraft)
    showOrderDetails({
      status: "ready_for_review",
      draft: activeOrderDraft,
    });
  updateReviewControls();
});
$("gstRate").addEventListener("input", () => {
  $("confirmOrder").checked = false;
  clearReadback();
  updateReviewControls();
});
$("calculateButton").addEventListener("click", async () => {
  const button = $("calculateButton");
  button.disabled = true;
  try {
    await calculateBill();
    button.querySelector("span").textContent = "✓";
    window.setTimeout(() => {
      button.querySelector("span").textContent = "→";
    }, 1200);
  } catch (error) {
    showMessage($("billMessage"), error.message, true);
  } finally {
    button.disabled = false;
  }
});
$("readbackButton").addEventListener("click", async () => {
  const button = $("readbackButton");
  button.disabled = true;
  button.textContent = "Preparing read-back…";
  try {
    const items = readBillItems([...lineItems.querySelectorAll(".item-row")]);
    const response = await fetch("/api/orders/readback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, gst_percent: $("gstRate").value || "0" }),
    });
    if (!response.ok) {
      const body = await response.json();
      throw new Error(
        responseMessage(body, "Could not prepare the Hindi read-back."),
      );
    }
    clearReadback();
    readbackUrl = URL.createObjectURL(await response.blob());
    $("readbackAudio").src = readbackUrl;
    $("readbackAudio").hidden = false;
    showMessage(
      $("transcribeMessage"),
      "Play the read-back and compare it with the order you heard.",
    );
  } catch (error) {
    showMessage($("transcribeMessage"), error.message, true);
  } finally {
    button.textContent = "Hear order read-back ♫";
    updateReviewControls();
  }
});
