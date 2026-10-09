(() => {
  const keys = ["commonroom-name", "commonroom-photo", "commonroom-group", "commonroom-client-id"];

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.description || "The request could not be completed.");
    }
    return result;
  }

  async function load() {
    const legacy = {};
    try {
      legacy.username = window.localStorage.getItem("commonroom-name");
      legacy.photo = window.localStorage.getItem("commonroom-photo");
      const group = Number(window.localStorage.getItem("commonroom-group"));
      if (Number.isInteger(group) && group > 0) legacy.group_id = group;
    } catch (error) {
      // Continue with the database profile when browser storage is unavailable.
    }

    let user = await requestJson("/api/me");
    const migration = {};
    if (legacy.username) migration.username = legacy.username;
    if (legacy.photo) migration.photo = legacy.photo;
    if (legacy.group_id) migration.group_id = legacy.group_id;

    if (Object.keys(migration).length) {
      try {
        user = await requestJson("/api/me", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(migration),
        });
      } catch (error) {
        if (!migration.group_id) throw error;
        delete migration.group_id;
        user = await requestJson("/api/me", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(migration),
        });
      }
    }

    try {
      keys.forEach((key) => window.localStorage.removeItem(key));
    } catch (error) {
      // The server remains the source of truth if browser storage is unavailable.
    }
    return user;
  }

  window.ChatSession = { load, requestJson };
})();
