(() => {
  const profileForm = document.getElementById("profile-form");
  const nameInput = document.getElementById("profile-name");
  const photoInput = document.getElementById("profile-photo");
  const previewName = document.getElementById("profile-preview-name");
  const avatar = document.getElementById("profile-avatar");
  const status = document.getElementById("profile-status");
  let profilePhoto = "";

  function guestName() {
    const number = window.crypto.getRandomValues(new Uint16Array(1))[0] % 10000;
    return `Student-${String(number).padStart(4, "0")}`;
  }

  function updatePreview(name) {
    const cleanName = name.trim();
    previewName.textContent = cleanName || "Your name";
    avatar.replaceChildren();
    if (profilePhoto) {
      const image = document.createElement("img");
      image.src = profilePhoto;
      image.alt = "";
      avatar.append(image);
    } else {
      avatar.textContent = cleanName ? cleanName.slice(0, 1).toUpperCase() : "?";
    }
  }

  function resizePhoto(file) {
    if (!file.type.startsWith("image/")) {
      return Promise.reject(new Error("Choose an image file."));
    }
    if (file.size > 5 * 1024 * 1024) {
      return Promise.reject(new Error("Profile photos must be 5 MB or smaller."));
    }
    return new Promise((resolve, reject) => {
      const image = new Image();
      const objectUrl = URL.createObjectURL(file);
      image.onload = () => {
        URL.revokeObjectURL(objectUrl);
        const canvas = document.createElement("canvas");
        canvas.width = 256;
        canvas.height = 256;
        const context = canvas.getContext("2d");
        if (!context) {
          reject(new Error("Could not process this image."));
          return;
        }
        const scale = Math.max(256 / image.naturalWidth, 256 / image.naturalHeight);
        const width = 256 / scale;
        const height = 256 / scale;
        const left = (image.naturalWidth - width) / 2;
        const top = (image.naturalHeight - height) / 2;
        context.drawImage(image, left, top, width, height, 0, 0, 256, 256);
        resolve(canvas.toDataURL("image/jpeg", 0.82));
      };
      image.onerror = () => {
        URL.revokeObjectURL(objectUrl);
        reject(new Error("Could not load this image."));
      };
      image.src = objectUrl;
    });
  }

  nameInput.value = "";
  updatePreview("");
  nameInput.addEventListener("input", () => updatePreview(nameInput.value));
  document.getElementById("remove-profile-photo").addEventListener("click", () => {
    profilePhoto = "";
    updatePreview(nameInput.value);
    status.textContent = "Photo removed. Save profile to apply the change.";
  });
  photoInput.addEventListener("change", async () => {
    const file = photoInput.files[0];
    if (!file) return;
    try {
      profilePhoto = await resizePhoto(file);
      updatePreview(nameInput.value);
      status.textContent = "Photo ready. Save profile to apply the change.";
    } catch (error) {
      status.textContent = error.message;
    } finally {
      photoInput.value = "";
    }
  });

  profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = nameInput.value.trim().slice(0, 32);
    if (!name) {
      status.textContent = "Enter a display name.";
      return;
    }
    try {
      await window.ChatSession.requestJson("/api/me", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: name, photo: profilePhoto }),
      });
    } catch (error) {
      status.textContent = error.message;
      return;
    }
    window.location.assign("/");
  });

  document.getElementById("new-guest-name").addEventListener("click", () => {
    nameInput.value = guestName();
    updatePreview(nameInput.value);
    status.textContent = "New guest name ready. Save profile to use it.";
  });

  document.getElementById("delete-profile").addEventListener("click", async () => {
    if (!window.confirm("Delete this browser profile and its photo?")) return;
    try {
      await window.ChatSession.requestJson("/api/me", { method: "DELETE" });
      window.location.assign("/");
    } catch (error) {
      status.textContent = error.message;
    }
  });

  window.ChatSession.load().then((user) => {
    nameInput.value = user.username;
    profilePhoto = user.photo || "";
    updatePreview(user.username);
  }).catch((error) => {
    status.textContent = error.message;
  });
})();