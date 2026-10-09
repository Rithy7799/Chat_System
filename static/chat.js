(() => {
  const currentName = document.getElementById("current-name");
  const messageForm = document.getElementById("message-form");
  const messageInput = document.getElementById("message-input");
  const fileInput = document.getElementById("file-input");
  const attachButton = document.getElementById("attach-button");
  const chatPanel = document.querySelector(".chat-panel");
  const dropOverlay = document.getElementById("drop-overlay");
  const messageArea = document.getElementById("message-area");
  const scrollControls = document.getElementById("scroll-controls");
  const scrollToTopButton = document.getElementById("scroll-to-top");
  const scrollToBottomButton = document.getElementById("scroll-to-bottom");
  const messageList = document.getElementById("message-list");
  const welcomeBlock = document.getElementById("welcome-block");
  const connectionIndicator = document.getElementById("connection-indicator");
  const connectionLabel = document.getElementById("connection-label");
  const onlineCount = document.getElementById("online-count");
  const statusMessage = document.getElementById("status-message");
  const groupList = document.getElementById("group-list");
  const activeRoomName = document.getElementById("active-room-name");
  const mobileGroupCurrent = document.getElementById("mobile-group-current");
  const mobileGroupToggle = document.getElementById("mobile-group-toggle");
  const sidePanel = document.querySelector(".side-panel");
  const groupOverlay = document.getElementById("group-overlay");
  const groupForm = document.getElementById("group-form");
  const groupNameInput = document.getElementById("group-name-input");
  const previewOverlay = document.getElementById("preview-overlay");
  const previewTitle = document.getElementById("preview-title");
  const previewContent = document.getElementById("preview-content");
  let username = "";
  let activeGroupId = 1;
  let groups = [];
  let connected = false;
  let refreshInProgress = false;

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.description || "The request could not be completed.");
    }
    return result;
  }

  function showStatus(text) {
    statusMessage.textContent = text;
    if (text) window.setTimeout(() => { statusMessage.textContent = ""; }, 3500);
  }

  function renderGroups() {
    groupList.replaceChildren();
    groups.forEach((group) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "group-choice" + (group.id === activeGroupId ? " is-active" : "");
      button.setAttribute("aria-current", group.id === activeGroupId ? "page" : "false");
      const hash = document.createElement("span");
      hash.className = "room-hash";
      hash.textContent = "#";
      const label = document.createElement("span");
      label.className = "group-choice-name";
      label.textContent = group.name;
      button.append(hash, label);
      button.addEventListener("click", () => {
        setGroupsOpen(false);
        if (group.id !== activeGroupId) selectGroup(group.id);
      });
      groupList.append(button);
    });
    const active = groups.find((group) => group.id === activeGroupId);
    if (active) {
      activeRoomName.textContent = active.name;
      mobileGroupCurrent.textContent = active.name;
    }
  }

  function setGroupsOpen(open) {
    sidePanel.classList.toggle("groups-open", open);
    mobileGroupToggle.setAttribute("aria-expanded", String(open));
  }

  function updateScrollControls() {
    const canScrollUp = messageArea.scrollTop > 4;
    const canScrollDown = messageArea.scrollTop + messageArea.clientHeight < messageArea.scrollHeight - 4;
    scrollToTopButton.hidden = !canScrollUp;
    scrollToBottomButton.hidden = !canScrollDown;
    scrollControls.hidden = !canScrollUp && !canScrollDown;
  }

  function renderAvatar(avatar, message) {
    avatar.replaceChildren();
    if (message.profile_photo) {
      const image = document.createElement("img");
      image.src = message.profile_photo;
      image.alt = "";
      avatar.append(image);
    } else {
      avatar.textContent = message.username.slice(0, 1).toUpperCase();
    }
  }

  function appendMessage(message) {
    const shouldFollowLatest = messageArea.scrollHeight - messageArea.scrollTop - messageArea.clientHeight < 80;
    welcomeBlock.hidden = true;
    const item = document.createElement("li");
    item.className = "message-item";
    item.dataset.messageId = String(message.id);
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    renderAvatar(avatar, message);
    const body = document.createElement("div");
    body.className = "message-body";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const author = document.createElement("span");
    author.className = "message-author";
    author.textContent = message.username;
    const time = document.createElement("time");
    time.className = "message-time";
    const sentAt = new Date(message.sent_at);
    const sentDate = sentAt.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
    const sentTime = sentAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    time.textContent = `${sentDate} · ${sentTime}`;
    time.dateTime = message.sent_at;
    meta.append(author, time);
    if (message.username === username && message.id !== undefined) {
      const deleteButton = document.createElement("button");
      deleteButton.className = "message-delete";
      deleteButton.type = "button";
      deleteButton.textContent = "Delete";
      deleteButton.setAttribute("aria-label", "Delete your message");
      deleteButton.addEventListener("click", () => {
        if (window.confirm("Delete this message for everyone in the room?")) {
          deleteMessage(message.id);
        }
      });
      meta.append(deleteButton);
    }
    body.append(meta);
    if (message.type === "file") {
      if (message.mime_type.startsWith("image/")) {
        const imageCard = document.createElement("div");
        imageCard.className = "image-file-card";
        const imageButton = document.createElement("button");
        imageButton.className = "image-message-preview";
        imageButton.type = "button";
        imageButton.setAttribute("aria-label", `Preview ${message.file_name}`);
        imageButton.addEventListener("click", () => viewFile(message));
        const image = document.createElement("img");
        image.src = `/files/${encodeURIComponent(message.file_id)}/view`;
        image.alt = message.file_name;
        image.loading = "lazy";
        imageButton.append(image);
        const imageDetails = document.createElement("div");
        imageDetails.className = "image-file-details";
        const imageName = document.createElement("span");
        imageName.className = "image-file-name";
        imageName.textContent = message.file_name;
        const imageSize = document.createElement("small");
        imageSize.textContent = formatFileSize(message.file_size);
        const downloadLink = document.createElement("a");
        downloadLink.className = "image-file-download";
        downloadLink.href = `/files/${encodeURIComponent(message.file_id)}/download`;
        downloadLink.textContent = "Download";
        downloadLink.setAttribute("download", "");
        imageDetails.append(imageName, imageSize, downloadLink);
        imageCard.append(imageButton, imageDetails);
        body.append(imageCard);
      } else {
        const fileCard = document.createElement("div");
        fileCard.className = "file-card";
        const fileBadge = document.createElement("span");
        fileBadge.className = "file-badge";
        fileBadge.textContent = message.file_name.split(".").pop().toUpperCase();
        const fileInfo = document.createElement("span");
        fileInfo.className = "file-info";
        const fileName = document.createElement("strong");
        fileName.textContent = message.file_name;
        const fileSize = document.createElement("small");
        fileSize.textContent = formatFileSize(message.file_size);
        fileInfo.append(fileName, fileSize);
        const actions = document.createElement("span");
        actions.className = "file-actions";
        const viewButton = document.createElement("button");
        viewButton.className = "file-view";
        viewButton.type = "button";
        viewButton.textContent = "View";
        viewButton.addEventListener("click", () => viewFile(message));
        const downloadLink = document.createElement("a");
        downloadLink.href = `/files/${encodeURIComponent(message.file_id)}/download`;
        downloadLink.textContent = "Download";
        downloadLink.setAttribute("download", "");
        actions.append(viewButton, downloadLink);
        fileCard.append(fileBadge, fileInfo, actions);
        body.append(fileCard);
      }
    } else {
      const text = document.createElement("p");
      text.className = "message-text";
      text.textContent = message.text;
      body.append(text);
    }
    
    item.append(avatar, body);
    messageList.append(item);
    if (shouldFollowLatest) messageArea.scrollTop = messageArea.scrollHeight;
    updateScrollControls();
  }

  function formatFileSize(size) {
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  async function viewFile(message) {
    const url = `/files/${encodeURIComponent(message.file_id)}/view`;
    if (message.mime_type === "application/pdf") {
      window.open(url, "_blank", "noopener");
      return;
    }
    previewTitle.textContent = message.file_name;
    previewContent.replaceChildren();
    previewOverlay.hidden = false;
    if (message.mime_type.startsWith("image/")) {
      const image = document.createElement("img");
      image.src = url;
      image.alt = message.file_name;
      previewContent.append(image);
      return;
    }
    const pre = document.createElement("pre");
    pre.textContent = "Loading preview...";
    previewContent.append(pre);
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error("Preview could not be loaded.");
      pre.textContent = await response.text();
    } catch (error) {
      pre.textContent = error.message;
    }
  }

  async function deleteMessage(messageId) {
    try {
      await requestJson(`/api/messages/${messageId}`, {
        method: "DELETE",
      });
      await refreshChat();
    } catch (error) {
      showStatus(error.message);
    }
  }

  function updateMessages(messages) {
    const messageIds = new Set(messages.map((message) => String(message.id)));
    Array.from(messageList.children).forEach((item) => {
      if (!messageIds.has(item.dataset.messageId)) item.remove();
    });
    const existingItems = new Map(
      Array.from(messageList.children).map((item) => [item.dataset.messageId, item])
    );
    messages.forEach((message) => {
      const existingItem = existingItems.get(String(message.id));
      if (existingItem) {
        renderAvatar(existingItem.querySelector(".avatar"), message);
      } else {
        appendMessage(message);
      }
    });
    welcomeBlock.hidden = messages.length > 0;
    updateScrollControls();
  }

  async function refreshChat() {
    if (refreshInProgress) return;
    refreshInProgress = true;
    try {
      const state = await requestJson("/api/chat");
      connected = true;
      connectionIndicator.classList.add("is-connected");
      connectionLabel.textContent = "Connected";
      onlineCount.textContent = `${state.online_count} online`;
      username = state.user.username;
      currentName.textContent = username;
      activeGroupId = state.group.id;
      groups = state.groups;
      renderGroups();
      updateMessages(state.messages);
    } catch (error) {
      connected = false;
      connectionIndicator.classList.remove("is-connected");
      connectionLabel.textContent = "Reconnecting";
    } finally {
      refreshInProgress = false;
    }
  }

  async function selectGroup(groupId) {
    setGroupsOpen(false);
    try {
      await requestJson("/api/me", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_id: groupId }),
      });
    } catch (error) {
      showStatus(error.message);
      return;
    }
    activeGroupId = groupId;
    messageList.replaceChildren();
    welcomeBlock.hidden = false;
    renderGroups();
    refreshChat();
  }

  messageArea.addEventListener("scroll", updateScrollControls, { passive: true });
  scrollToTopButton.addEventListener("click", () => {
    messageArea.scrollTo({ top: 0, behavior: "smooth" });
  });
  scrollToBottomButton.addEventListener("click", () => {
    messageArea.scrollTo({ top: messageArea.scrollHeight, behavior: "smooth" });
  });
  window.addEventListener("resize", updateScrollControls);

  mobileGroupToggle.addEventListener("click", () => {
    setGroupsOpen(mobileGroupToggle.getAttribute("aria-expanded") !== "true");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setGroupsOpen(false);
  });
  document.addEventListener("click", (event) => {
    if (!sidePanel.contains(event.target)) setGroupsOpen(false);
  });

  async function initializeChat() {
    try {
      const user = await window.ChatSession.load();
      username = user.username;
      activeGroupId = user.selected_group_id;
      currentName.textContent = username;
      await refreshChat();
    } catch (error) {
      connectionLabel.textContent = "Unavailable";
      showStatus(error.message);
    }
  }

  initializeChat();
  window.setInterval(() => {
    if (username) refreshChat();
  }, 2500);

  messageForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = messageInput.value.trim();
    if (!text || !username || !connected) return;
    requestJson("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then(() => {
      messageInput.value = "";
      messageInput.style.height = "auto";
      messageInput.focus();
      refreshChat();
    }).catch((error) => showStatus(error.message));
  });
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      messageForm.requestSubmit();
    }
  });
  messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 140)}px`;
  });

  async function uploadFiles(files) {
    if (!files.length) return;
    if (!username || !connected) {
      showStatus("Connect to the room before sharing a file.");
      return;
    }
    attachButton.disabled = true;
    try {
      for (const [index, file] of files.entries()) {
        const formData = new FormData();
        formData.append("file", file);
        showStatus(`Uploading ${file.name} (${index + 1}/${files.length})...`);
        const response = await fetch("/upload", { method: "POST", body: formData });
        if (!response.ok) {
          const result = await response.json().catch(() => ({}));
          throw new Error(result.description || `Could not upload ${file.name}.`);
        }
      }
      showStatus(files.length === 1 ? "File shared." : "Files shared.");
      refreshChat();
    } catch (error) {
      showStatus(error.message);
    } finally {
      attachButton.disabled = false;
      fileInput.value = "";
    }
  }

  attachButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => uploadFiles(Array.from(fileInput.files)));

  function isFileDrag(event) {
    return Array.from(event.dataTransfer.types).includes("Files");
  }

  let dragDepth = 0;
  chatPanel.addEventListener("dragenter", (event) => {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    dragDepth += 1;
    dropOverlay.hidden = false;
  });
  chatPanel.addEventListener("dragover", (event) => {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  chatPanel.addEventListener("dragleave", (event) => {
    if (!isFileDrag(event)) return;
    dragDepth -= 1;
    if (dragDepth <= 0) {
      dragDepth = 0;
      dropOverlay.hidden = true;
    }
  });
  chatPanel.addEventListener("drop", (event) => {
    if (!event.dataTransfer.files.length) return;
    event.preventDefault();
    dragDepth = 0;
    dropOverlay.hidden = true;
    uploadFiles(Array.from(event.dataTransfer.files));
  });

  document.getElementById("close-preview").addEventListener("click", () => {
    previewOverlay.hidden = true;
    previewContent.replaceChildren();
  });
  previewOverlay.addEventListener("click", (event) => {
    if (event.target === previewOverlay) {
      previewOverlay.hidden = true;
      previewContent.replaceChildren();
    }
  });

  document.getElementById("open-create-group").addEventListener("click", () => {
    setGroupsOpen(false);
    groupOverlay.hidden = false;
    groupNameInput.focus();
  });
  document.getElementById("cancel-create-group").addEventListener("click", () => {
    groupOverlay.hidden = true;
  });
  groupOverlay.addEventListener("click", (event) => {
    if (event.target === groupOverlay) groupOverlay.hidden = true;
  });
  groupForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = groupNameInput.value.trim();
    if (!name) return;
    requestJson("/api/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then(({ group }) => {
      groupOverlay.hidden = true;
      groupNameInput.value = "";
      selectGroup(group.id);
    }).catch((error) => showStatus(error.message));
  });

})();