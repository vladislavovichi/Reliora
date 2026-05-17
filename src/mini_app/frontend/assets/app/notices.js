export function createNoticeController({ appNotice, telegram }) {
  let noticeTimeoutId = 0;

  function showNotice(message, tone = "neutral") {
    if (!appNotice) {
      return;
    }

    window.clearTimeout(noticeTimeoutId);
    appNotice.hidden = false;
    appNotice.textContent = message;
    appNotice.dataset.tone = tone;
    noticeTimeoutId = window.setTimeout(() => {
      appNotice.hidden = true;
      appNotice.textContent = "";
      delete appNotice.dataset.tone;
    }, 2600);
  }

  async function handleCopy(value, successMessage = "Скопировано.") {
    try {
      await navigator.clipboard.writeText(value);
      showNotice(successMessage || "Скопировано.", "success");
      if (telegram?.HapticFeedback) {
        telegram.HapticFeedback.notificationOccurred("success");
      }
    } catch (_error) {
      showNotice("Не удалось скопировать. Скопируйте вручную.", "danger");
    }
  }

  return { handleCopy, showNotice };
}
