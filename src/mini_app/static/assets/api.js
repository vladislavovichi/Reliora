export class MiniAppRequestError extends Error {
  constructor(message, { status, code } = {}) {
    super(message);
    this.name = "MiniAppRequestError";
    this.status = typeof status === "number" ? status : 0;
    this.code = typeof code === "string" ? code : "";
  }
}

export function createMiniAppApi(launchContext) {
  const initData = typeof launchContext?.initData === "string" ? launchContext.initData : "";
  const launchSource = typeof launchContext?.source === "string" ? launchContext.source : "missing";
  const clientDiagnostics = Array.isArray(launchContext?.diagnostics)
    ? launchContext.diagnostics.filter(Boolean)
    : [];
  const attemptedSources = Array.isArray(launchContext?.attemptedSources)
    ? launchContext.attemptedSources.filter(Boolean)
    : [];

  async function request(path, { method = "GET", body, responseType = "json" } = {}) {
    const headers = {
      Authorization: `TMA ${initData}`,
      "X-Telegram-Init-Data": initData,
      "X-Mini-App-Launch-Source": launchSource,
      "X-Mini-App-Telegram-WebApp": launchContext?.isTelegramWebApp ? "present" : "missing",
      "X-Mini-App-Telegram-User": launchContext?.hasTelegramUser ? "present" : "missing",
    };
    appendOptionalHeader(headers, "X-Mini-App-Client-Diagnostics", clientDiagnostics.join(","));
    appendOptionalHeader(headers, "X-Mini-App-Attempted-Sources", attemptedSources.join(","));
    appendOptionalHeader(headers, "X-Mini-App-Telegram-Platform", launchContext?.telegramPlatform);
    appendOptionalHeader(headers, "X-Mini-App-Telegram-Version", launchContext?.telegramVersion);

    const options = {
      method,
      headers,
    };

    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    const response = await fetch(path, options);
    if (!response.ok) {
      let errorMessage = "Сервис недоступен.";
      let errorCode = "";

      try {
        const payload = await response.json();
        if (payload && typeof payload.error === "string") {
          errorMessage = payload.error;
        }
        if (payload && typeof payload.code === "string") {
          errorCode = payload.code;
        }
      } catch (_error) {
        errorMessage = `Ошибка ${response.status}.`;
      }

      throw new MiniAppRequestError(errorMessage, {
        status: response.status,
        code: errorCode,
      });
    }

    if (responseType === "blob") {
      return response.blob();
    }
    return response.json();
  }

  async function download(path, filenameHint) {
    const blob = await request(path, { responseType: "blob" });
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = filenameHint;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
  }

  return {
    hasInitData() {
      return Boolean(initData);
    },
    getSession() {
      return request("/api/session");
    },
    getDashboard() {
      return request("/api/dashboard");
    },
    getQueue() {
      return request("/api/queue");
    },
    takeNext() {
      return request("/api/queue/take-next", { method: "POST" });
    },
    getMyTickets() {
      return request("/api/my-tickets");
    },
    getArchive() {
      return request("/api/archive");
    },
    getAnalytics(windowKey) {
      return request(`/api/analytics?window=${encodeURIComponent(windowKey)}`);
    },
    downloadAnalytics(windowKey, section, format) {
      return download(
        `/api/analytics/export?window=${encodeURIComponent(windowKey)}&section=${encodeURIComponent(section)}&format=${encodeURIComponent(format)}`,
        `analytics-${windowKey}.${format === "csv" ? "csv" : "html"}`,
      );
    },
    getOperators() {
      return request("/api/admin/operators");
    },
    createInvite() {
      return request("/api/admin/invites", { method: "POST" });
    },
    getTicket(publicId) {
      return request(`/api/tickets/${publicId}`);
    },
    refreshTicketAi(publicId) {
      return request(`/api/tickets/${publicId}/ai-summary`, { method: "POST" });
    },
    generateTicketReplyDraft(publicId) {
      return request(`/api/tickets/${publicId}/ai-reply-draft`, { method: "POST" });
    },
    takeTicket(publicId) {
      return request(`/api/tickets/${publicId}/take`, { method: "POST" });
    },
    closeTicket(publicId) {
      return request(`/api/tickets/${publicId}/close`, { method: "POST" });
    },
    escalateTicket(publicId) {
      return request(`/api/tickets/${publicId}/escalate`, { method: "POST" });
    },
    assignTicket(publicId, payload) {
      return request(`/api/tickets/${publicId}/assign`, { method: "POST", body: payload });
    },
    addTicketNote(publicId, text) {
      return request(`/api/tickets/${publicId}/notes`, {
        method: "POST",
        body: { text },
      });
    },
    applyMacro(publicId, macroId) {
      return request(`/api/tickets/${publicId}/macros/${macroId}`, { method: "POST" });
    },
    downloadTicket(publicId, format) {
      return download(
        `/api/tickets/${publicId}/export?format=${encodeURIComponent(format)}`,
        `ticket-${publicId}.${format === "csv" ? "csv" : "html"}`,
      );
    },
  };
}

function appendOptionalHeader(headers, key, value) {
  if (typeof value === "string" && value.trim()) {
    headers[key] = value;
  }
}
