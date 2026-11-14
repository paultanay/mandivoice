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

$("billDate").textContent = new Intl.DateTimeFormat("en-IN", {
  day: "numeric", month: "short", year: "numeric",
}).format(new Date());

function responseMessage(body, fallback) {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join(". ");
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
  $("audioMeta").textContent = `${(blob.size / 1024).toFixed(0)} KB · ready to transcribe`;
  audioDurationValid = true;
  audioPreview.onloadedmetadata = () => {
    audioDurationValid = !Number.isFinite(audioPreview.duration) || audioPreview.duration <= MAX_RECORDING_SECONDS;
    transcribeButton.disabled = !audioDurationValid;
    if (!audioDurationValid) {
      showMessage($("transcribeMessage"), "Choose a recording that is 30 seconds or shorter.", true);
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
    for (let sourceIndex = Math.floor(start); sourceIndex < Math.ceil(end); sourceIndex += 1) {
      const overlap = Math.min(end, sourceIndex + 1) - Math.max(start, sourceIndex);
      total += samples[sourceIndex] * overlap;
      weight += overlap;
    }
    const sample = Math.max(-1, Math.min(1, total / weight));
    pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  const buffer = new ArrayBuffer(44 + pcm.byteLength);
  const view = new DataView(buffer);
  const write = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  write(0, "RIFF"); view.setUint32(4, 36 + pcm.byteLength, true); write(8, "WAVE");
  write(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, targetRate, true);
  view.setUint32(28, targetRate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); write(36, "data"); view.setUint32(40, pcm.byteLength, true);
  new Int16Array(buffer, 44).set(pcm);
  return new Blob([buffer], { type: "audio/wav" });
}

function setRecordingState(isRecording) {
  const button = $("recordButton");
  button.classList.toggle("is-recording", isRecording);
  button.querySelector("span:last-child").textContent = isRecording ? "Stop recording" : "Start recording";
  button.querySelector(".record-button-icon").textContent = isRecording ? "■" : "●";
  $("recordCard").classList.toggle("is-recording", isRecording);
  $("recordTitle").textContent = isRecording ? "Listening to your order" : "Ready when you are";
  $("recordHint").textContent = isRecording ? "Speak clearly, then stop when you’re done." : "Use your own words. Include a quantity and price for each item.";
  $("recordingProgress").hidden = !isRecording;
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
    showMessage($("transcribeMessage"), "Microphone recording is unavailable in this browser. Choose an audio file instead.", true);
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(mediaStream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    recordingChunks = [];
    processor.onaudioprocess = (event) => {
      recordingChunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
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
    showMessage($("transcribeMessage"), "Microphone access was not available. Allow access or choose an audio file.", true);
    stopTracks();
  }
}

function updateRecordingTime() {
  const seconds = Math.min(MAX_RECORDING_SECONDS, Math.floor((Date.now() - recordingStartedAt) / 1000));
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
  const samples = new Float32Array(recordingChunks.reduce((sum, chunk) => sum + chunk.length, 0));
  let offset = 0;
  for (const chunk of recordingChunks) { samples.set(chunk, offset); offset += chunk.length; }
  await audioContext.close();
  audioContext = null;
  processor = null;
  setRecordingState(false);
  if (!samples.length) {
    showMessage($("transcribeMessage"), "No audio was captured. Try again or choose an audio file.", true);
    return;
  }
  selectAudio(writeWav(samples, sampleRate), "Microphone recording.wav");
}

$("recordButton").addEventListener("click", () => audioContext ? stopRecording() : startRecording());

audioInput.addEventListener("change", () => {
  const file = audioInput.files?.[0];
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) {
    clearAudio(); showMessage($("transcribeMessage"), "Choose an audio file smaller than 20 MB.", true); return;
  }
  selectAudio(file, file.name);
});
$("removeAudio").addEventListener("click", clearAudio);

transcribeButton.addEventListener("click", async () => {
  if (!selectedBlob) return;
  if (!audioDurationValid) return;
  transcribeButton.disabled = true;
  transcribeButton.innerHTML = '<span class="spinner" aria-hidden="true"></span> Transcribing…';
  showMessage($("transcribeMessage"), "Sending audio to Gnani Prisma…");
  try {
    const form = new FormData();
    form.append("audio_file", selectedBlob, selectedName);
    const response = await fetch("/api/transcribe", { method: "POST", body: form });
    const body = await response.json();
    if (!response.ok) throw new Error(responseMessage(body, "Transcription failed. Try again."));
    transcriptField.value = body.transcript;
    updateCharacterCount();
    $("languageLabel").textContent = body.detected_language_code ? `Detected language: ${body.detected_language_code}` : "Transcript ready · check names and numbers";
    showMessage($("transcribeMessage"), "Transcript ready. Check it before making a bill.");
    transcriptField.focus();
  } catch (error) {
    showMessage($("transcribeMessage"), error.message || "Could not transcribe this recording.", true);
  } finally {
    transcribeButton.disabled = !selectedBlob || !audioDurationValid;
    transcribeButton.innerHTML = 'Transcribe with Prisma <span aria-hidden="true">→</span>';
  }
});

function updateCharacterCount() {
  const count = transcriptField.value.length;
  $("characterCount").textContent = `${count} / 4000`;
  if (!$("languageLabel").textContent.startsWith("Detected language:")) {
    $("languageLabel").textContent = count ? "Transcript · edit as needed" : "Your transcript will appear here";
  }
}
transcriptField.addEventListener("input", updateCharacterCount);

function addLineItem(item = {}) {
  const row = document.createElement("div");
  row.className = "item-row";
  for (const field of [
    { key: "name", label: "Item name", placeholder: "Item" },
    { key: "quantity", label: "Quantity", placeholder: "1", numeric: true },
    { key: "unit_price", label: "Price per unit in rupees", placeholder: "0.00", numeric: true },
  ]) {
    const input = document.createElement("input");
    input.className = `item-input${field.numeric ? " numeric" : ""}`;
    input.type = field.numeric ? "number" : "text";
    if (field.numeric) { input.min = "0.01"; input.step = "any"; input.inputMode = "decimal"; }
    input.maxLength = field.numeric ? 20 : 80;
    input.placeholder = field.placeholder;
    input.value = item[field.key] ?? "";
    input.dataset.key = field.key;
    input.setAttribute("aria-label", field.label);
    row.append(input);
  }
  const remove = document.createElement("button");
  remove.className = "remove-item"; remove.type = "button"; remove.textContent = "×";
  remove.setAttribute("aria-label", "Remove item");
  remove.addEventListener("click", () => { row.remove(); if (!lineItems.children.length) showEmptyItems(); });
  row.append(remove);
  lineItems.append(row);
  return row;
}
function showEmptyItems() { lineItems.innerHTML = '<div class="empty-items">No items yet. Use a transcript or add the items below.</div>'; }
showEmptyItems();

$("addItemButton").addEventListener("click", () => {
  if (lineItems.querySelector(".empty-items")) lineItems.innerHTML = "";
  addLineItem().querySelector("input").focus();
});

$("parseButton").addEventListener("click", async () => {
  const transcript = transcriptField.value.trim();
  if (!transcript) { showMessage($("transcribeMessage"), "Record or type an order first.", true); transcriptField.focus(); return; }
  const button = $("parseButton"); button.disabled = true;
  try {
    const response = await fetch("/api/bills/parse", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ transcript }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(responseMessage(body, "Could not read this transcript."));
    if (!body.items.length) {
      showMessage($("transcribeMessage"), "No clear quantity-and-price lines found. Add the items yourself so nothing is guessed.", true); return;
    }
    lineItems.replaceChildren(); body.items.forEach(addLineItem);
    showMessage($("transcribeMessage"), `${body.items.length} item${body.items.length === 1 ? "" : "s"} found. Review each one and add anything missing.`);
    await calculateBill();
  } catch (error) { showMessage($("transcribeMessage"), error.message, true); }
  finally { button.disabled = false; }
});

function formatRupees(value) { return `₹${value}`; }
async function calculateBill() {
  const items = [...lineItems.querySelectorAll(".item-row")].map((row) => Object.fromEntries(
    [...row.querySelectorAll("input")].map((input) => [input.dataset.key, input.value.trim()]),
  ));
  const response = await fetch("/api/bills/calculate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, gst_percent: $("gstRate").value || "0" }),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(responseMessage(body, "Check the item details and try again."));
  $("subtotal").textContent = formatRupees(body.subtotal);
  $("gstAmount").textContent = formatRupees(body.gst_amount);
  $("total").textContent = formatRupees(body.total);
}
$("calculateButton").addEventListener("click", async () => {
  const button = $("calculateButton"); button.disabled = true;
  try {
    await calculateBill(); button.querySelector("span").textContent = "✓";
    window.setTimeout(() => { button.querySelector("span").textContent = "→"; }, 1200);
  } catch (error) { showMessage($("transcribeMessage"), error.message, true); }
  finally { button.disabled = false; }
});
$("gstRate").addEventListener("change", () => {
  if (lineItems.querySelector(".item-row")) calculateBill().catch((error) => showMessage($("transcribeMessage"), error.message, true));
});
