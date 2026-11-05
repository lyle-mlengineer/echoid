const form = document.querySelector("[data-auth-form]");
const message = document.querySelector(".auth-message");
const googleButton = document.querySelector("[data-google-signin]");
const accessKey = "echoid.access";
const guestKey = "echoid.guest";

function showMessage(text, success = false) {
  if (!message) return;
  message.hidden = false;
  message.textContent = text;
  message.classList.toggle("is-success", success);
}

function continueToApp() {
  const next = new URLSearchParams(location.search).get("next");
  const destination = next ? new URL(next, location.origin) : null;
  location.assign(destination?.origin === location.origin ? destination.href : "/dashboard");
}

function saveSession(payload) {
  sessionStorage.setItem(accessKey, payload.access_token);
  sessionStorage.removeItem(guestKey);
  continueToApp();
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = form.querySelector('[type="submit"]');
  submit.disabled = true;
  const formData = new FormData(form);
  const isRegister = form.dataset.mode === "register";
  const body = Object.fromEntries(formData.entries());
  const guestToken = sessionStorage.getItem(guestKey);
  try {
    const response = await fetch(`/api/v1/auth/${isRegister ? "register" : "login"}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(isRegister && guestToken ? { "X-Guest-Token": guestToken } : {}),
      },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = payload.detail;
      throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join(", ") : detail || "We couldn't sign you in.");
    }
    saveSession(payload);
  } catch (error) {
    showMessage(error.message || "Something went wrong. Please try again.");
    submit.disabled = false;
  }
});

document.querySelector(".password-toggle")?.addEventListener("click", (event) => {
  const input = document.querySelector("#password");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  event.currentTarget.textContent = show ? "Hide" : "Show";
  event.currentTarget.setAttribute("aria-label", show ? "Hide password" : "Show password");
});

document.querySelector("[data-forgot-password]")?.addEventListener("click", async (event) => {
  event.preventDefault();
  const email = document.querySelector("#email").value.trim();
  if (!email) {
    showMessage("Enter your email address first, then choose forgot password.");
    document.querySelector("#email").focus();
    return;
  }
  if (!window.ECHOID_FIREBASE) {
    showMessage("Password reset is available when Firebase is configured for this app.");
    return;
  }
  try {
    const [{ initializeApp }, { getAuth, sendPasswordResetEmail }] = await Promise.all([
      import("https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js"),
      import("https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js"),
    ]);
    const auth = getAuth(initializeApp(window.ECHOID_FIREBASE));
    await sendPasswordResetEmail(auth, email);
    showMessage("If an account exists for that email, a reset link is on its way.", true);
  } catch {
    showMessage("We couldn't send a reset email. Check the address and try again.");
  }
});

googleButton?.addEventListener("click", async () => {
  if (!window.ECHOID_FIREBASE) {
    showMessage("Google sign-in isn't configured yet. Ask your administrator to add the Firebase web settings.");
    return;
  }
  googleButton.disabled = true;
  try {
    const [{ initializeApp }, { getAuth, GoogleAuthProvider, signInWithPopup }] = await Promise.all([
      import("https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js"),
      import("https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js"),
    ]);
    const auth = getAuth(initializeApp(window.ECHOID_FIREBASE));
    const result = await signInWithPopup(auth, new GoogleAuthProvider());
    const idToken = await result.user.getIdToken();
    const response = await fetch("/api/v1/auth/firebase", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Google sign-in could not be completed.");
    saveSession(payload);
  } catch (error) {
    showMessage(error.message || "Google sign-in could not be completed.");
    googleButton.disabled = false;
  }
});
