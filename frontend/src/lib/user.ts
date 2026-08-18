/**
 * Lightweight, no-login user identification.
 * Generates a random UUID on first visit, stores it in a cookie and localStorage,
 * and returns it for use with all API requests — replacing hardcoded "default".
 */

const USER_ID_KEY = "memoryverse_user_id";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    const val = parts.pop()?.split(";").shift();
    return val ? decodeURIComponent(val) : null;
  }
  return null;
}

function setCookie(name: string, value: string, days = 365) {
  if (typeof document === "undefined") return;
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

export function getOrCreateUserId(): string {
  if (typeof window === "undefined") return "default";

  // 0. An explicit ?user=<id> in the URL pins that identity and persists it.
  //    This is how the demo is loaded without console surgery: bookmark
  //    /dashboard?user=<uuid> and one click seeds the cookie + localStorage,
  //    overriding any previously stored id. Ignored only for the literal
  //    "default", which the backend treats as the unseeded fallback bucket.
  try {
    const fromUrl = new URLSearchParams(window.location.search).get("user");
    if (fromUrl && fromUrl !== "default") {
      setCookie(USER_ID_KEY, fromUrl);
      try {
        localStorage.setItem(USER_ID_KEY, fromUrl);
      } catch {}
      return fromUrl;
    }
  } catch {}

  // 1. Try cookie first
  let userId = getCookie(USER_ID_KEY);

  // 2. Fallback to localStorage
  if (!userId || userId === "default") {
    try {
      userId = localStorage.getItem(USER_ID_KEY);
    } catch {}
  }

  // 3. Generate new UUID if missing or default
  if (!userId || userId === "default") {
    userId =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : "usr_" +
          Math.random().toString(36).substring(2, 11) +
          Date.now().toString(36);
  }

  // Persist in both cookie and localStorage
  setCookie(USER_ID_KEY, userId);
  try {
    localStorage.setItem(USER_ID_KEY, userId);
  } catch {}

  return userId;
}
