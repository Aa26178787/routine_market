(() => {
  const form = document.querySelector("#signup-form");
  if (!form) return;

  const emailInput = form.querySelector("#id_email");
  const nicknameInput = form.querySelector("#id_nickname");
  const sendButton = form.querySelector("[data-send-code]");
  const verificationSection = form.querySelector("[data-email-verification]");
  const confirmButton = form.querySelector("[data-confirm-code]");
  const codeRow = form.querySelector("[data-code-row]");
  const codeInput = form.querySelector("[data-code-input]");
  const timerElement = form.querySelector("[data-verification-timer]");
  const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
  let expiryTimer;
  let resendTimer;

  const showStatus = (name, message, ok = false) => {
    const target = form.querySelector(`[data-status="${name}"]`);
    target.textContent = message;
    target.classList.toggle("success", ok);
    target.classList.toggle("error", !ok && Boolean(message));
  };

  const post = async (url, values) => {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "X-CSRFToken": csrfToken,
      },
      body: new URLSearchParams(values),
    });
    return { response, data: await response.json() };
  };

  const clearTimers = () => {
    window.clearInterval(expiryTimer);
    window.clearInterval(resendTimer);
  };

  const startExpiryTimer = (seconds) => {
    window.clearInterval(expiryTimer);
    const expiresAt = Date.now() + seconds * 1000;
    const update = () => {
      const remaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
      const minutes = String(Math.floor(remaining / 60)).padStart(2, "0");
      const remainder = String(remaining % 60).padStart(2, "0");
      timerElement.textContent = `${minutes}:${remainder}`;
      timerElement.classList.toggle("expiring", remaining > 0 && remaining <= 60);
      if (remaining === 0) {
        window.clearInterval(expiryTimer);
        confirmButton.disabled = true;
        showStatus("verification", "인증시간이 만료되었습니다. 인증번호를 다시 받아 주세요.");
      }
    };
    update();
    expiryTimer = window.setInterval(update, 1000);
  };

  const startResendTimer = (seconds) => {
    window.clearInterval(resendTimer);
    const availableAt = Date.now() + seconds * 1000;
    const update = () => {
      const remaining = Math.max(0, Math.ceil((availableAt - Date.now()) / 1000));
      if (remaining === 0) {
        window.clearInterval(resendTimer);
        sendButton.disabled = false;
        sendButton.textContent = "인증번호 다시 받기";
      } else {
        sendButton.disabled = true;
        sendButton.textContent = `재발송 ${remaining}초`;
      }
    };
    update();
    resendTimer = window.setInterval(update, 1000);
  };

  form.querySelectorAll("[data-check]").forEach((button) => {
    button.addEventListener("click", async () => {
      const field = button.dataset.check;
      const input = field === "email" ? emailInput : nicknameInput;
      const value = input.value.trim();
      if (!value) {
        showStatus(field, `${field === "email" ? "이메일" : "닉네임"}을 먼저 입력해 주세요.`);
        input.focus();
        return;
      }
      button.disabled = true;
      try {
        const url = new URL(form.dataset.availabilityUrl, window.location.origin);
        url.searchParams.set("field", field);
        url.searchParams.set("value", value);
        const data = await (await fetch(url)).json();
        showStatus(field, data.message, data.available);
      } catch (_) {
        showStatus(field, "중복확인 중 문제가 발생했습니다. 다시 시도해 주세요.");
      } finally {
        button.disabled = false;
      }
    });
  });

  emailInput.addEventListener("input", () => {
    if (emailInput.value.trim().toLowerCase() !== form.dataset.verifiedEmail) {
      clearTimers();
      form.dataset.verifiedEmail = "";
      sendButton.disabled = false;
      sendButton.textContent = "인증번호 받기";
      confirmButton.disabled = false;
      timerElement.textContent = "05:00";
      timerElement.classList.remove("expiring");
      codeRow.hidden = true;
      verificationSection.classList.remove("active");
      showStatus("email", "");
      showStatus("verification", "");
    }
  });
  nicknameInput.addEventListener("input", () => showStatus("nickname", ""));

  sendButton.addEventListener("click", async () => {
    const email = emailInput.value.trim();
    if (!email) {
      showStatus("verification", "이메일을 먼저 입력해 주세요.");
      emailInput.focus();
      return;
    }
    sendButton.disabled = true;
    sendButton.textContent = "발송 중…";
    let sent = false;
    try {
      const { data } = await post(form.dataset.emailSendUrl, { email });
      showStatus("verification", data.message, data.ok);
      if (data.ok) {
        sent = true;
        codeRow.hidden = false;
        verificationSection.classList.add("active");
        confirmButton.disabled = false;
        codeInput.value = "";
        codeInput.focus();
        startExpiryTimer(data.expires_in || 300);
        startResendTimer(data.resend_after || 60);
      }
    } catch (_) {
      showStatus("verification", "인증 메일 발송 중 문제가 발생했습니다.");
    } finally {
      if (!sent) {
        sendButton.disabled = false;
        sendButton.textContent = "인증번호 받기";
      }
    }
  });

  confirmButton.addEventListener("click", async () => {
    const code = codeInput.value.trim();
    if (!/^\d{6}$/.test(code)) {
      showStatus("verification", "6자리 인증번호를 입력해 주세요.");
      codeInput.focus();
      return;
    }
    confirmButton.disabled = true;
    try {
      const { data } = await post(form.dataset.emailConfirmUrl, {
        email: emailInput.value.trim(),
        code,
      });
      showStatus("verification", data.message, data.ok);
      if (data.ok) {
        clearTimers();
        form.dataset.verifiedEmail = emailInput.value.trim().toLowerCase();
        showStatus("email", "인증된 이메일입니다.", true);
        codeRow.hidden = true;
        verificationSection.classList.remove("active");
        sendButton.disabled = true;
        sendButton.textContent = "인증 완료";
      }
    } catch (_) {
      showStatus("verification", "인증 확인 중 문제가 발생했습니다.");
    } finally {
      confirmButton.disabled = false;
    }
  });

  if (form.dataset.verifiedEmail) {
    sendButton.disabled = true;
    sendButton.textContent = "인증 완료";
  }
})();
