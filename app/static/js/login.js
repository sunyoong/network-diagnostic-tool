"use strict";
document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  const error = document.getElementById("login-error");
  button.disabled = true; error.textContent = "";
  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: document.getElementById("username").value, password: document.getElementById("password").value })
    });
    const body = await response.json();
    if (!response.ok || !body.success) throw new Error(body.error?.message || "로그인하지 못했습니다.");
    location.replace("/");
  } catch (reason) { error.textContent = reason.message || "서버에 연결하지 못했습니다."; }
  finally { button.disabled = false; }
});
