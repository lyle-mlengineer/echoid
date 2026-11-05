(() => {
  const API = "/api/v1";
  const accessKey = "echoid.access";
  const guestKey = "echoid.guest";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const accessToken = () => sessionStorage.getItem(accessKey);

  function toast(message, isError = false) {
    const region = $(".toast-region");
    if (!region) return;
    const item = document.createElement("div");
    item.className = `toast${isError ? " is-error" : ""}`;
    item.textContent = message;
    region.append(item);
    window.setTimeout(() => item.remove(), 4800);
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (accessToken()) headers.set("Authorization", `Bearer ${accessToken()}`);
    else if (sessionStorage.getItem(guestKey)) {
      headers.set("X-Guest-Token", sessionStorage.getItem(guestKey));
    }
    const response = await fetch(`${API}${path}`, { ...options, headers });
    const type = response.headers.get("content-type") || "";
    const payload = type.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = payload && typeof payload === "object" ? payload.detail : payload;
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg).join(", ")
        : String(detail || `Request failed (${response.status}).`);
      throw new Error(message);
    }
    return payload;
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function formatDate(value, options = { dateStyle: "medium" }) {
    if (!value) return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "—" : new Intl.DateTimeFormat(undefined, options).format(parsed);
  }

  function formatDuration(seconds) {
    if (!Number.isFinite(seconds)) return "Audio transcript";
    const minutes = Math.floor(seconds / 60);
    const rest = Math.floor(seconds % 60).toString().padStart(2, "0");
    return `${minutes}:${rest} min`;
  }

  function redirectToLogin() {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    location.href = `/login?next=${next}`;
  }

  async function ensureGuest() {
    if (sessionStorage.getItem(guestKey)) return;
    const session = await api("/auth/guest", { method: "POST" });
    sessionStorage.setItem(guestKey, session.guest_token);
  }

  function downloadBlob(blob, filename) {
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(href), 1000);
  }

  async function exportGeneration(id, format, fallbackName = "transcript") {
    const token = accessToken();
    if (!token) {
      toast("Create an account or log in to download transcripts.", true);
      redirectToLogin();
      return;
    }
    const response = await fetch(`${API}/generations/${encodeURIComponent(id)}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Download failed (${response.status}).`);
    }
    const blob = await response.blob();
    const filename = response.headers.get("content-disposition")?.match(/filename="?([^";]+)"?/i)?.[1]
      || `${fallbackName}.${format}`;
    downloadBlob(blob, filename);
  }

  function renderTranscript(container, segments, onSpeakerClick, speakerProfiles = []) {
    container.replaceChildren();
    const speakerColors = new Map();
    segments.forEach((segment) => {
      const row = make("article", "transcript-segment");
      if (!speakerColors.has(segment.speaker)) speakerColors.set(segment.speaker, speakerColors.size % 6 + 1);
      row.classList.add(`speaker-tone-${speakerColors.get(segment.speaker)}`);
      const speaker = make("button", "segment-speaker");
      speaker.type = "button";
      speaker.title = `Rename ${segment.speaker}`;
      speaker.setAttribute("aria-label", `Rename speaker ${segment.speaker}`);
      speaker.addEventListener("click", () => onSpeakerClick(segment.speaker));
      const initials = segment.speaker.trim().charAt(0).toLocaleUpperCase() || "?";
      const profile = speakerProfiles.find((item) => item.name.toLocaleLowerCase() === segment.speaker.toLocaleLowerCase());
      const avatar = profile?.image_data
        ? make("img", "speaker-avatar", undefined)
        : make("span", "speaker-avatar", initials);
      if (profile?.image_data) {
        avatar.src = profile.image_data;
        avatar.alt = "";
      }
      avatar.setAttribute("aria-hidden", "true");
      speaker.append(avatar, make("span", "speaker-name", segment.speaker));
      row.append(
        make("span", "segment-time", formatDuration(segment.start_seconds).replace(" min", "")),
        speaker,
        make("p", "segment-text", segment.text),
      );
      container.append(row);
    });
  }

  function generationRow(record, withActions = true) {
    const row = make("article", "generation-row");
    row.dataset.filename = record.filename.toLowerCase();
    row.append(make("span", "generation-file-icon", "♫"));
    const main = make("div", "generation-main");
    main.append(make("b", "", record.filename), make("small", "", `${formatDate(record.created_at)} · ${record.segments.length} speaker turn${record.segments.length === 1 ? "" : "s"}`));
    row.append(main);
    const meta = make("div", "generation-meta");
    meta.append(make("span", "status-tag", record.status || "completed"));
    if (withActions) {
      const actions = make("div", "row-actions");
      const open = make("a", "icon-button", "↗");
      open.href = `/studio?generation=${encodeURIComponent(record.id)}`;
      open.title = "Open transcript";
      const remove = make("button", "icon-button danger", "×");
      remove.type = "button";
      remove.title = "Delete transcript";
      remove.dataset.deleteGeneration = record.id;
      actions.append(open, remove);
      meta.append(actions);
    }
    row.append(meta);
    return row;
  }

  async function confirmDelete(id) {
    if (!window.confirm("Delete this transcript and its uploaded audio? This cannot be undone.")) return;
    await api(`/generations/${encodeURIComponent(id)}`, { method: "DELETE" });
    toast("Transcript deleted.");
    await Promise.all([loadDashboard(), loadGallery()]);
  }

  async function loadDashboard() {
    const list = $("[data-generation-list]");
    if (!list) return;
    try {
      const [user, generations] = await Promise.all([
        api("/auth/me"),
        api("/generations"),
      ]);
      const credits = $("[data-credit-balance]");
      if (credits) credits.textContent = user.credits.toLocaleString();
      const count = $("[data-generation-count]");
      if (count) count.textContent = generations.length.toLocaleString();
      const last = $("[data-last-activity]");
      if (last) last.textContent = generations.length
        ? formatDate(generations[0].created_at, { month: "short", day: "numeric" })
        : "Not yet";
      list.replaceChildren();
      if (!generations.length) {
        const empty = make("div", "empty-state");
        empty.append(make("b", "", "Your first conversation is waiting."));
        empty.append(document.createTextNode("Upload an audio file and EchoID will take it from here."));
        const start = make("a", "button button-primary", "Start a transcript ↗");
        start.href = "/studio";
        empty.append(start);
        list.append(empty);
      } else {
        generations.slice(0, 5).forEach((item) => list.append(generationRow(item)));
      }
    } catch (error) {
      if (error.message.includes("token") || error.message.includes("Sign in")) redirectToLogin();
      else list.replaceChildren(make("div", "empty-state", error.message));
    }
  }

  async function loadGallery() {
    const grid = $("[data-gallery-grid]");
    if (!grid) return;
    try {
      const generations = await api("/generations");
      const count = $("[data-gallery-count]");
      if (count) count.textContent = generations.length.toLocaleString();
      grid.replaceChildren();
      if (!generations.length) {
        const empty = make("div", "empty-state");
        empty.append(make("b", "", "A little quiet in here."));
        empty.append(document.createTextNode("Your saved conversations will show up here."));
        const start = make("a", "button button-primary", "Make your first transcript ↗");
        start.href = "/studio";
        empty.append(start);
        grid.append(empty);
        return;
      }
      generations.forEach((record) => grid.append(galleryCard(record)));
      filterGallery();
    } catch (error) {
      grid.replaceChildren(make("div", "empty-state", error.message));
      if (error.message.includes("token") || error.message.includes("Sign in")) redirectToLogin();
    }
  }

  function galleryCard(record) {
    const card = make("article", "gallery-card");
    card.dataset.filename = record.filename.toLowerCase();
    const top = make("div", "gallery-card-top");
    top.append(make("span", "generation-file-icon", "♫"), make("span", "status-tag", record.status));
    card.append(top, make("h3", "", record.filename));
    const meta = make("div", "gallery-card-meta");
    meta.append(make("span", "", formatDate(record.created_at)), make("span", "", formatDuration(record.duration_seconds)));
    card.append(meta);
    const preview = make("p", "gallery-card-preview", record.segments[0]?.text || "No transcript text.");
    card.append(preview);
    const actions = make("div", "gallery-card-actions");
    const open = make("a", "button button-primary", "Open transcript ↗");
    open.href = `/studio?generation=${encodeURIComponent(record.id)}`;
    const remove = make("button", "icon-button danger", "×");
    remove.type = "button";
    remove.title = "Delete transcript";
    remove.dataset.deleteGeneration = record.id;
    actions.append(open, remove);
    card.append(actions);
    return card;
  }

  function filterGallery() {
    const search = $("[data-gallery-search]");
    const grid = $("[data-gallery-grid]");
    if (!search || !grid) return;
    const value = search.value.trim().toLowerCase();
    let visible = 0;
    $$("[data-filename]", grid).forEach((item) => {
      const show = item.dataset.filename.includes(value);
      item.hidden = !show;
      if (show) visible += 1;
    });
    const emptyResult = $("[data-empty-search]", grid);
    if (value && !visible) {
      if (!emptyResult) {
        const message = make("div", "empty-state", "No transcripts match that search.");
        message.dataset.emptySearch = "true";
        grid.append(message);
      }
    } else emptyResult?.remove();
  }

  async function startStudio() {
    const fileInput = $("#audio-file");
    const choose = $("[data-choose-file]");
    const uploadArea = $("[data-upload-area]");
    const selected = $("[data-selected-file]");
    const transcribe = $("[data-transcribe]");
    const status = $("[data-studio-status]");
    const resultPanel = $("[data-transcript-panel]");
    if (!fileInput || !transcribe) return;
    let selectedFile = null;
    let generationId = null;
    let currentSegments = [];
    let pendingSpeaker = null;
    let speakerProfiles = [];
    let selectedProfileId = null;
    let editingProfileId = null;
    let pendingProfileForRename = false;
    let editorImageData = null;
    const speakerDialog = $("[data-speaker-dialog]");
    const speakerForm = $("[data-speaker-form]");
    const speakerInput = $("[data-speaker-name-input]");
    const speakerError = $("[data-speaker-error]");
    const saveSpeaker = $("[data-save-speaker]");
    const speakerSelect = $("[data-speaker-profile-select]");
    const speakerList = $("[data-speaker-list]");
    const speakerSearch = $("[data-speaker-search]");
    const speakerCount = $("[data-speaker-count]");
    const editorDialog = $("[data-speaker-editor]");
    const editorForm = $("[data-speaker-editor-form]");
    const editorName = $("[data-speaker-editor-name]");
    const editorDescription = $("[data-speaker-editor-description]");
    const editorImageInput = $("[data-speaker-image-input]");
    const editorImagePreview = $("[data-speaker-image-preview]");
    const editorImageRemove = $("[data-remove-speaker-image]");
    const editorError = $("[data-speaker-editor-error]");
    const saveProfile = $("[data-save-speaker-profile]");

    const renderCurrentTranscript = () => renderTranscript(
      $("[data-transcript-results]"),
      currentSegments,
      openSpeakerRename,
      speakerProfiles,
    );
    function renderSpeakerSelect(profileId = "") {
      speakerSelect.replaceChildren(make("option", "", "Enter a name or choose a saved speaker"));
      speakerProfiles.forEach((profile) => {
        const option = make("option", "", profile.name);
        option.value = profile.id;
        speakerSelect.append(option);
      });
      speakerSelect.value = profileId;
    }
    function renderSpeakerDirectory() {
      if (!speakerList) return;
      const query = speakerSearch.value.trim().toLocaleLowerCase();
      const visible = speakerProfiles.filter((profile) => (
        `${profile.name} ${profile.description}`.toLocaleLowerCase().includes(query)
      ));
      speakerCount.textContent = `${visible.length} speaker${visible.length === 1 ? "" : "s"}`;
      speakerList.replaceChildren();
      if (!accessToken()) {
        speakerList.append(make("div", "speaker-library-empty", "Sign in to save speakers to your voice directory."));
        return;
      }
      if (!visible.length) {
        speakerList.append(make("div", "speaker-library-empty", query ? "No speakers match your search." : "Your speaker directory is empty. Add a speaker to get started."));
        return;
      }
      visible.forEach((profile) => {
        const card = make("article", "speaker-profile-card");
        const avatar = profile.image_data
          ? make("img", "speaker-profile-avatar")
          : make("span", "speaker-profile-avatar", profile.name.trim().charAt(0).toLocaleUpperCase() || "?");
        if (profile.image_data) {
          avatar.src = profile.image_data;
          avatar.alt = "";
        }
        const details = make("div", "speaker-profile-details");
        details.append(make("b", "", profile.name), make("p", "", profile.description || "No description yet."));
        const actions = make("div", "speaker-profile-actions");
        const edit = make("button", "icon-button", "✎");
        edit.type = "button";
        edit.title = `Edit ${profile.name}`;
        edit.setAttribute("aria-label", `Edit ${profile.name}`);
        edit.dataset.editSpeaker = profile.id;
        const remove = make("button", "icon-button danger", "×");
        remove.type = "button";
        remove.title = `Delete ${profile.name}`;
        remove.setAttribute("aria-label", `Delete ${profile.name}`);
        remove.dataset.removeSpeaker = profile.id;
        actions.append(edit, remove);
        card.append(avatar, details, actions);
        speakerList.append(card);
      });
    }
    async function loadSpeakers() {
      if (!accessToken()) {
        renderSpeakerDirectory();
        return;
      }
      try {
        speakerProfiles = await api("/speakers");
        renderSpeakerDirectory();
        renderSpeakerSelect(selectedProfileId || "");
        renderCurrentTranscript();
      } catch (error) {
        speakerList.replaceChildren(make("div", "speaker-library-empty is-error", error.message));
      }
    }
    function openSpeakerRename(speaker) {
      pendingSpeaker = speaker;
      selectedProfileId = null;
      speakerInput.value = speaker;
      speakerError.hidden = true;
      speakerError.textContent = "";
      renderSpeakerSelect();
      speakerDialog.showModal();
      speakerInput.focus();
      speakerInput.select();
    }
    function updateEditorImagePreview() {
      editorImagePreview.replaceChildren();
      if (editorImageData) {
        const image = make("img", "", undefined);
        image.src = editorImageData;
        image.alt = "";
        editorImagePreview.append(image);
        editorImageRemove.hidden = false;
      } else {
        editorImagePreview.textContent = editorName.value.trim().charAt(0).toLocaleUpperCase() || "?";
        editorImageRemove.hidden = true;
      }
    }
    function openSpeakerEditor(profile = null, fromRename = false) {
      if (!accessToken()) {
        toast("Sign in to create and save speakers.", true);
        return;
      }
      editingProfileId = profile?.id || null;
      pendingProfileForRename = fromRename;
      editorName.value = profile?.name || "";
      editorDescription.value = profile?.description || "";
      editorImageData = profile?.image_data || null;
      editorImageInput.value = "";
      editorError.hidden = true;
      editorError.textContent = "";
      $("[data-speaker-editor-title]").textContent = editingProfileId ? "Edit speaker" : "Add a speaker";
      saveProfile.innerHTML = editingProfileId ? 'Save changes <span>↗</span>' : 'Save speaker <span>↗</span>';
      updateEditorImagePreview();
      editorDialog.showModal();
      editorName.focus();
    }
    const previewSample = () => showSamplePreview((segments) => {
      generationId = null;
      currentSegments = segments;
      renderCurrentTranscript();
    });

    const showStatus = (message, isError = false) => {
      status.hidden = !message;
      status.textContent = message;
      status.classList.toggle("is-error", isError);
    };
    const setFile = (file) => {
      selectedFile = file;
      if (!file) {
        selected.hidden = true;
        uploadArea.hidden = false;
        transcribe.disabled = true;
        return;
      }
      selected.hidden = false;
      uploadArea.hidden = true;
      $("[data-file-name]").textContent = file.name;
      $("[data-file-size]").textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB`;
      transcribe.disabled = false;
      showStatus("");
      resultPanel.hidden = true;
      generationId = null;
      $$("[data-export]").forEach((button) => { button.disabled = true; });
    };
    choose?.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => setFile(fileInput.files?.[0] || null));
    $("[data-remove-file]")?.addEventListener("click", () => {
      fileInput.value = "";
      setFile(null);
    });
    ["dragenter", "dragover"].forEach((eventName) => uploadArea.addEventListener(eventName, (event) => {
      event.preventDefault();
      uploadArea.classList.add("is-dragging");
    }));
    ["dragleave", "drop"].forEach((eventName) => uploadArea.addEventListener(eventName, (event) => {
      event.preventDefault();
      uploadArea.classList.remove("is-dragging");
    }));
    uploadArea.addEventListener("drop", (event) => {
      const file = event.dataTransfer?.files?.[0];
      if (file) setFile(file);
    });

    $$("[data-studio-tab]").forEach((tab) => tab.addEventListener("click", () => {
      $$("[data-studio-tab]").forEach((item) => item.classList.toggle("is-selected", item === tab));
      if (tab.dataset.studioTab === "sample") previewSample();
    }));
    $("[data-use-sample]")?.addEventListener("click", previewSample);
    const closeSpeakerDialog = () => speakerDialog.close();
    $("[data-close-speaker-dialog]")?.addEventListener("click", closeSpeakerDialog);
    $("[data-cancel-speaker-dialog]")?.addEventListener("click", closeSpeakerDialog);
    $("[data-add-speaker]")?.addEventListener("click", () => openSpeakerEditor());
    $("[data-close-speaker-editor]")?.addEventListener("click", () => editorDialog.close());
    $("[data-cancel-speaker-editor]")?.addEventListener("click", () => editorDialog.close());
    $("[data-create-speaker-from-rename]")?.addEventListener("click", () => {
      if (!accessToken()) {
        toast("Sign in to create and save speakers.", true);
        return;
      }
      speakerDialog.close();
      openSpeakerEditor(null, true);
    });
    speakerSearch?.addEventListener("input", renderSpeakerDirectory);
    speakerSelect?.addEventListener("change", () => {
      const profile = speakerProfiles.find((item) => item.id === speakerSelect.value);
      selectedProfileId = profile?.id || null;
      if (profile) speakerInput.value = profile.name;
    });
    speakerInput?.addEventListener("input", () => {
      selectedProfileId = null;
      speakerSelect.value = "";
    });
    editorName?.addEventListener("input", updateEditorImagePreview);
    editorImageInput?.addEventListener("change", () => {
      const file = editorImageInput.files?.[0];
      if (!file) return;
      if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 2 * 1024 * 1024) {
        editorError.textContent = "Choose a JPG, PNG, or WebP image smaller than 2 MB.";
        editorError.hidden = false;
        editorImageInput.value = "";
        return;
      }
      const reader = new FileReader();
      reader.addEventListener("load", () => {
        editorImageData = typeof reader.result === "string" ? reader.result : null;
        updateEditorImagePreview();
      });
      reader.addEventListener("error", () => {
        editorError.textContent = "The selected image could not be read.";
        editorError.hidden = false;
      });
      reader.readAsDataURL(file);
    });
    editorImageRemove?.addEventListener("click", () => {
      editorImageData = null;
      editorImageInput.value = "";
      updateEditorImagePreview();
    });
    speakerList?.addEventListener("click", async (event) => {
      const editButton = event.target.closest("[data-edit-speaker]");
      if (editButton) {
        const profile = speakerProfiles.find((item) => item.id === editButton.dataset.editSpeaker);
        if (profile) openSpeakerEditor(profile);
        return;
      }
      const removeButton = event.target.closest("[data-remove-speaker]");
      if (!removeButton) return;
      const profile = speakerProfiles.find((item) => item.id === removeButton.dataset.removeSpeaker);
      if (!profile || !window.confirm(`Delete ${profile.name} from your saved speakers?`)) return;
      try {
        await api(`/speakers/${encodeURIComponent(profile.id)}`, { method: "DELETE" });
        await loadSpeakers();
        toast("Speaker deleted.");
      } catch (error) {
        toast(error.message, true);
      }
    });
    editorForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        name: editorName.value.trim(),
        description: editorDescription.value.trim(),
        image_data: editorImageData,
      };
      saveProfile.disabled = true;
      editorError.hidden = true;
      try {
        const savedProfile = await api(
          editingProfileId ? `/speakers/${encodeURIComponent(editingProfileId)}` : "/speakers",
          {
            method: editingProfileId ? "PATCH" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          },
        );
        speakerProfiles = [
          ...speakerProfiles.filter((profile) => profile.id !== savedProfile.id),
          savedProfile,
        ].sort((a, b) => a.name.localeCompare(b.name));
        renderSpeakerDirectory();
        renderSpeakerSelect();
        renderCurrentTranscript();
        editorDialog.close();
        if (pendingProfileForRename) {
          openSpeakerRename(pendingSpeaker);
          selectedProfileId = savedProfile.id;
          renderSpeakerSelect(selectedProfileId);
          speakerInput.value = savedProfile.name;
        } else {
          toast(editingProfileId ? "Speaker updated." : "Speaker saved.");
        }
      } catch (error) {
        editorError.textContent = error.message;
        editorError.hidden = false;
      } finally {
        saveProfile.disabled = false;
      }
    });
    speakerDialog?.addEventListener("click", (event) => {
      if (event.target === speakerDialog) closeSpeakerDialog();
    });
    editorDialog?.addEventListener("click", (event) => {
      if (event.target === editorDialog) editorDialog.close();
    });
    speakerForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const name = speakerInput.value.trim();
      if (!name || !pendingSpeaker) {
        speakerInput.reportValidity();
        return;
      }
      saveSpeaker.disabled = true;
      speakerError.hidden = true;
      try {
        if (generationId) {
          const result = await api(`/generations/${encodeURIComponent(generationId)}/speakers`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              speaker: pendingSpeaker,
              name,
              speaker_profile_id: selectedProfileId,
            }),
          });
          currentSegments = result.segments;
        } else {
          currentSegments = currentSegments.map((segment) => (
            segment.speaker === pendingSpeaker ? { ...segment, speaker: name } : segment
          ));
        }
        renderCurrentTranscript();
        speakerDialog.close();
      } catch (error) {
        speakerError.textContent = error.message;
        speakerError.hidden = false;
      } finally {
        saveSpeaker.disabled = false;
      }
    });
    loadSpeakers();

    async function runTranscription(file) {
      transcribe.disabled = true;
      transcribe.innerHTML = '<span class="spinner"></span> Listening…';
      showStatus("Uploading your recording and separating the speakers…");
      try {
        await ensureGuest();
        const body = new FormData();
        body.append("audio", file);
        const result = await api("/generations", { method: "POST", body });
        generationId = result.id;
        $("[data-result-title]").textContent = result.filename;
        currentSegments = result.segments;
        renderCurrentTranscript();
        $("[data-demo-banner]").hidden = !result.demo_mode;
        $$("[data-export]").forEach((button) => { button.disabled = !accessToken(); });
        resultPanel.hidden = false;
        showStatus(result.demo_mode
          ? "This is a demo transcript. Configure a transcription provider to analyze real audio."
          : "Your transcript is ready.");
        resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        if (accessToken()) await loadDashboard();
      } catch (error) {
        showStatus(error.message, true);
        if (error.message.toLowerCase().includes("sign up")) {
          const link = make("a", "text-link", "Create an account →");
          link.href = "/register";
          status.append(document.createTextNode(" "), link);
        }
      } finally {
        transcribe.disabled = !selectedFile;
        transcribe.innerHTML = 'Transcribe audio <span>↗</span>';
      }
    }

    transcribe.addEventListener("click", () => {
      if (selectedFile) runTranscription(selectedFile);
    });
    $$("[data-export]").forEach((button) => button.addEventListener("click", async () => {
      if (!generationId) return;
      try {
        await exportGeneration(generationId, button.dataset.export, "echoid-transcript");
      } catch (error) {
        toast(error.message, true);
      }
    }));
    const queryId = new URLSearchParams(location.search).get("generation");
    if (queryId && (accessToken() || sessionStorage.getItem(guestKey))) {
      try {
        const generation = await api(`/generations/${encodeURIComponent(queryId)}`);
        generationId = generation.id;
        $("[data-result-title]").textContent = generation.filename;
        currentSegments = generation.segments;
        renderCurrentTranscript();
        $("[data-demo-banner]").hidden = !generation.demo_mode;
          $$("[data-export]").forEach((button) => { button.disabled = !accessToken(); });
        resultPanel.hidden = false;
      } catch (error) {
        toast(error.message, true);
      }
    }
  }

  function showSamplePreview(onSegments) {
    const panel = $("[data-transcript-panel]");
    const title = $("[data-result-title]");
    const banner = $("[data-demo-banner]");
    if (!panel) return;
    title.textContent = "A quick preview";
    banner.hidden = false;
    banner.textContent = "EXAMPLE PREVIEW — These sample lines are illustrative, not generated from an audio recording.";
    onSegments([
      { speaker: "ALEX", text: "Did the Q3 numbers land yet?", start_seconds: 4, end_seconds: 7 },
      { speaker: "PRIYA", text: "Uploading the deck now.", start_seconds: 8, end_seconds: 10 },
      { speaker: "ALEX", text: "Perfect. Let's review it together.", start_seconds: 11, end_seconds: 14 },
    ]);
    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    $$("[data-export]", panel).forEach((button) => { button.disabled = true; });
  }

  async function loadBilling() {
    if (!$("[data-package-grid]")) return;
    try {
      const [user, packages] = await Promise.all([api("/auth/me"), api("/billing/packages")]);
      const balance = $("[data-credit-balance]");
      balance.replaceChildren(document.createTextNode(user.credits.toLocaleString()), make("small", "", " credits"));
      $("[data-billing-email]").textContent = user.email;
      renderPackages(packages);
      loadPayments();
    } catch (error) {
      $("[data-package-grid]").replaceChildren(make("div", "empty-state", error.message));
      if (error.message.includes("token") || error.message.includes("Sign in")) redirectToLogin();
    }
  }

  function renderPackages(packages) {
    const grid = $("[data-package-grid]");
    grid.replaceChildren();
    const popular = "creator";
    packages.forEach((pack) => {
      const card = make("article", `package-card${pack.id === popular ? " is-popular" : ""}`);
      if (pack.id === popular) card.append(make("span", "popular-ribbon", "MOST POPULAR"));
      card.append(
        make("span", "package-label", pack.id),
        make("div", "package-price", `KES ${pack.amount_kes.toLocaleString()}`),
        make("div", "package-credits", `${pack.credits} credits`),
        make("p", "package-note", `KES ${(pack.amount_kes / pack.credits).toFixed(2)} per credit · one-time payment`),
      );
      const actions = make("div", "package-actions");
      const stk = make("button", "button button-primary", "M-Pesa STK");
      stk.type = "button";
      stk.addEventListener("click", () => openStkDialog(pack));
      const qr = make("button", "button button-secondary", "Scan QR");
      qr.type = "button";
      qr.addEventListener("click", () => createPayment("/billing/mpesa/qr", pack.id, "POST"));
      const manual = make("button", "button button-secondary", "Till / Paybill");
      manual.type = "button";
      manual.addEventListener("click", () => createPayment("/billing/mpesa/manual", pack.id, "POST"));
      const cardPay = make("button", "button button-secondary", "Card");
      cardPay.type = "button";
      cardPay.addEventListener("click", () => createPayment("/billing/card", pack.id, "POST", true));
      actions.append(stk, qr, manual, cardPay);
      card.append(actions);
      grid.append(card);
    });
  }

  function dialogContent(title, message) {
    const root = $("[data-payment-dialog-content]");
    root.replaceChildren(make("span", "eyebrow", "ECHOID CHECKOUT"), make("h2", "", title), make("p", "", message));
    return root;
  }

  function openDialog() {
    const dialog = $("[data-payment-dialog]");
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function openStkDialog(pack) {
    const root = dialogContent("A little prompt is on its way.", `You’re adding ${pack.credits} credits for KES ${pack.amount_kes}. Enter the M-Pesa number to receive the STK prompt.`);
    const label = make("label", "", "M-Pesa phone number");
    label.htmlFor = "mpesa-phone";
    const phone = document.createElement("input");
    phone.id = "mpesa-phone";
    phone.type = "tel";
    phone.placeholder = "07XX XXX XXX";
    phone.autocomplete = "tel";
    phone.required = true;
    phone.pattern = "^(?:\\+?254|0)?[17]\\d{8}$";
    const submit = make("button", "button button-primary", "Send payment prompt ↗");
    submit.type = "button";
    submit.addEventListener("click", async () => {
      if (!phone.reportValidity()) return;
      submit.disabled = true;
      try {
        await completePaymentAction(root, `/billing/mpesa/stk`, "POST", { package_id: pack.id, phone_number: phone.value });
      } catch (error) {
        showPaymentError(root, error);
        submit.disabled = false;
      }
    });
    root.append(label, phone, submit);
    openDialog();
  }

  async function createPayment(path, packageId, method, redirect = false) {
    const root = dialogContent("Preparing your payment…", "Connecting securely to your payment provider.");
    openDialog();
    try {
      await completePaymentAction(root, `${path}?package_id=${encodeURIComponent(packageId)}`, method, {}, redirect);
    } catch (error) {
      showPaymentError(root, error);
    }
  }

  async function completePaymentAction(root, path, method, body, redirect = false) {
    const result = await api(path, {
      method,
      headers: body && Object.keys(body).length ? { "Content-Type": "application/json" } : {},
      body: body && Object.keys(body).length ? JSON.stringify(body) : undefined,
    });
    if (redirect && result.checkout_url) {
      location.assign(result.checkout_url);
      return;
    }
    root.replaceChildren(make("span", "eyebrow", "PAYMENT STARTED"), make("h2", "", "You’re all set for the next step."));
    root.append(make("p", "", result.message));
    if (result.qr_code && /^[A-Za-z0-9+/=]+$/.test(result.qr_code)) {
      const image = document.createElement("img");
      image.className = "qr-image";
      image.alt = "M-Pesa payment QR code";
      image.src = `data:image/png;base64,${result.qr_code}`;
      root.append(image);
    }
    if (result.checkout_request_id) {
      root.append(make("p", "payment-instructions", "Approve the prompt on your phone. Your credits appear here once M-Pesa confirms the payment."));
    }
    const close = make("button", "button button-primary", "Done");
    close.type = "button";
    close.addEventListener("click", () => $("[data-payment-dialog]").close());
    root.append(close);
    loadPayments();
  }

  function showPaymentError(root, error) {
    root.replaceChildren(make("span", "eyebrow", "PAYMENT NOT STARTED"), make("h2", "", "Let’s try another way."), make("p", "payment-instructions", error.message));
  }

  async function loadPayments() {
    const list = $("[data-payment-history]");
    if (!list) return;
    try {
      const payments = await api("/billing/payments");
      list.replaceChildren();
      if (!payments.length) {
        list.append(make("div", "empty-state", "No payments yet. Your top-ups will appear here."));
        return;
      }
      payments.forEach((payment) => {
        const row = make("div", "payment-row");
        const main = make("div", "payment-row-main");
        main.append(make("b", "", `${payment.provider.replaceAll("_", " ")} · ${payment.credits} credits`), make("small", "", `${formatDate(payment.created_at)} · ${payment.status}`));
        row.append(main, make("span", "payment-row-amount", `KES ${payment.amount_kes.toLocaleString()}`));
        list.append(row);
      });
    } catch (error) {
      list.replaceChildren(make("div", "empty-state", error.message));
    }
  }

  function setupNavigation() {
    const toggle = $(".menu-toggle");
    const nav = $(".main-nav");
    toggle?.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
    });
    $$("[data-logout]").forEach((button) => button.addEventListener("click", (event) => {
      event.preventDefault();
      sessionStorage.removeItem(accessKey);
      sessionStorage.removeItem(guestKey);
      location.href = "/";
    }));
    const token = accessToken();
    if (!token) return;
    api("/auth/me").then((user) => {
      const login = $(".nav-login");
      const cta = $(".nav-cta");
      if (login) { login.textContent = `Hi, ${user.display_name.split(" ")[0]}`; login.href = "/dashboard"; }
      if (cta) { cta.textContent = "Log out"; cta.href = "/"; cta.dataset.logout = ""; }
    }).catch(() => {
      sessionStorage.removeItem(accessKey);
    });
  }

  document.addEventListener("click", async (event) => {
    const target = event.target.closest("[data-delete-generation]");
    if (!target) return;
    try {
      await confirmDelete(target.dataset.deleteGeneration);
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("[data-gallery-search]")?.addEventListener("input", filterGallery);
  setupNavigation();
  if (accessToken() && ($("[data-generation-list]") || $("[data-gallery-grid]") || $("[data-credit-balance]"))) {
    loadDashboard();
  }
  startStudio();
  loadGallery();
  loadBilling();

  window.EchoID = { api, accessKey, guestKey, toast };
})();
