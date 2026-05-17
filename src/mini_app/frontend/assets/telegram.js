const telegram = window.Telegram?.WebApp ?? null;

const INIT_DATA_STORAGE_KEY = "reliora:mini-app:init-data";
const INIT_DATA_SOURCE_STORAGE_KEY = "reliora:mini-app:init-data-source";
const INIT_DATA_STORED_AT_KEY = "reliora:mini-app:init-data-stored-at";
const SENSITIVE_LAUNCH_KEYS = ["tgWebAppData", "init_data"];
const POLL_INTERVAL_MS = 120;
const DEFAULT_WAIT_BUDGET_MS = 1800;
const TELEGRAM_WAIT_BUDGET_MS = 4500;
const TELEGRAM_USER_WAIT_BUDGET_MS = 6500;
const RETRY_EXTENSION_MS = 2400;
const MAX_PERSISTED_INIT_DATA_AGE_MS = 30 * 60 * 1000;

function delay(timeoutMs) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, timeoutMs);
  });
}

function normalizeValue(value) {
  if (typeof value !== "string") {
    return "";
  }

  let normalized = value.trim();
  for (let index = 0; index < 2; index += 1) {
    const decoded = decodeURIComponentSafe(normalized).trim();
    if (decoded === normalized) {
      break;
    }
    normalized = decoded;
  }

  return normalized;
}

function decodeURIComponentSafe(value) {
  try {
    return decodeURIComponent(value);
  } catch (_error) {
    return value;
  }
}

function readLaunchParams() {
  const url = new URL(window.location.href);
  const scopes = [
    ["search", url.searchParams],
    [
      "hash",
      new URLSearchParams(url.hash.includes("?") ? url.hash.split("?")[1] ?? "" : ""),
    ],
  ];

  for (const [scope, params] of scopes) {
    for (const key of SENSITIVE_LAUNCH_KEYS) {
      const value = normalizeValue(params.get(key));
      if (value) {
        return { value, source: `query:${key}`, scope };
      }
    }
  }

  return { value: "", source: "missing", scope: null };
}

function stripSensitiveLaunchParams() {
  const url = new URL(window.location.href);
  let changed = false;

  for (const key of SENSITIVE_LAUNCH_KEYS) {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  }

  if (url.hash.includes("?")) {
    const [hashPath, hashQuery] = url.hash.split("?");
    const hashParams = new URLSearchParams(hashQuery ?? "");
    for (const key of SENSITIVE_LAUNCH_KEYS) {
      if (hashParams.has(key)) {
        hashParams.delete(key);
        changed = true;
      }
    }
    const nextHashQuery = hashParams.toString();
    url.hash = nextHashQuery ? `${hashPath}?${nextHashQuery}` : hashPath;
  }

  if (changed) {
    window.history.replaceState(null, "", url.toString());
  }
}

function persistInitData(initData, source) {
  try {
    window.sessionStorage.setItem(INIT_DATA_STORAGE_KEY, initData);
    window.sessionStorage.setItem(INIT_DATA_SOURCE_STORAGE_KEY, source);
    window.sessionStorage.setItem(INIT_DATA_STORED_AT_KEY, String(Date.now()));
  } catch (_error) {
    // Storage can be unavailable inside constrained webviews.
  }
}

export function clearPersistedLaunchContext() {
  try {
    window.sessionStorage.removeItem(INIT_DATA_STORAGE_KEY);
    window.sessionStorage.removeItem(INIT_DATA_SOURCE_STORAGE_KEY);
    window.sessionStorage.removeItem(INIT_DATA_STORED_AT_KEY);
  } catch (_error) {
    // Storage can be unavailable inside constrained webviews.
  }
}

function restorePersistedInitData() {
  try {
    const storedAtRaw = window.sessionStorage.getItem(INIT_DATA_STORED_AT_KEY);
    const storedAt = Number(storedAtRaw);
    if (!Number.isFinite(storedAt) || Date.now() - storedAt > MAX_PERSISTED_INIT_DATA_AGE_MS) {
      clearPersistedLaunchContext();
      return { value: "", source: "session-storage", ageMs: null };
    }

    return {
      value: normalizeValue(window.sessionStorage.getItem(INIT_DATA_STORAGE_KEY)),
      source:
        normalizeValue(window.sessionStorage.getItem(INIT_DATA_SOURCE_STORAGE_KEY)) ||
        "session-storage",
      ageMs: Math.max(Date.now() - storedAt, 0),
    };
  } catch (_error) {
    return { value: "", source: "session-storage", ageMs: null };
  }
}

function readTelegramLiveSources() {
  const initData = normalizeValue(telegram?.initData);
  if (initData) {
    return { value: initData, source: "telegram-web-app" };
  }

  const webViewInitData = normalizeValue(window.Telegram?.WebView?.initParams?.tgWebAppData);
  if (webViewInitData) {
    return { value: webViewInitData, source: "telegram-webview-init-params" };
  }

  return { value: "", source: "missing" };
}

function resolveWaitBudget({ extraWait = false } = {}) {
  const hasTelegramUser = Boolean(telegram?.initDataUnsafe?.user);
  const isTelegramWebApp = Boolean(telegram);

  let budgetMs = DEFAULT_WAIT_BUDGET_MS;
  if (isTelegramWebApp) {
    budgetMs = TELEGRAM_WAIT_BUDGET_MS;
  }
  if (hasTelegramUser) {
    budgetMs = TELEGRAM_USER_WAIT_BUDGET_MS;
  }
  if (extraWait) {
    budgetMs += RETRY_EXTENSION_MS;
  }
  return budgetMs;
}

async function waitForLiveInitData({ budgetMs }) {
  const startedAt = Date.now();
  let attempts = 0;

  while (Date.now() - startedAt <= budgetMs) {
    attempts += 1;
    const resolved = readTelegramLiveSources();
    if (resolved.value) {
      return {
        ...resolved,
        waitedMs: Date.now() - startedAt,
        attempts,
      };
    }
    await delay(POLL_INTERVAL_MS);
  }

  return {
    value: "",
    source: "missing",
    waitedMs: Date.now() - startedAt,
    attempts,
  };
}

function syncViewport() {
  const height = telegram?.viewportStableHeight || telegram?.viewportHeight || window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${Math.round(height)}px`);
}

function configureTelegramChrome() {
  syncViewport();
  if (!telegram) {
    return;
  }

  try {
    telegram.ready();
    telegram.expand();
    telegram.disableVerticalSwipes?.();
    telegram.setHeaderColor?.("#ede7dc");
    telegram.setBackgroundColor?.("#ece5db");
  } catch (_error) {
    // Telegram clients can expose a partial WebApp API surface.
  }

  telegram.onEvent?.("viewportChanged", syncViewport);
}

function buildAttemptedSources(context) {
  const attemptedSources = [
    "telegram-web-app",
    "telegram-webview-init-params",
    "query:tgWebAppData",
    "query:init_data",
    "session-storage",
  ];
  if (!context.isTelegramWebApp) {
    attemptedSources.unshift("telegram-web-app:missing");
  }
  return attemptedSources;
}

function logLaunchContext(context) {
  const logger = context.initData ? console.info : console.warn;
  logger("[mini-app] launch", {
    source: context.source,
    isTelegramWebApp: context.isTelegramWebApp,
    hasTelegramUser: context.hasTelegramUser,
    waitedMs: context.waitedMs,
    attemptedSources: context.attemptedSources,
    diagnostics: context.diagnostics,
    telegramPlatform: context.telegramPlatform,
    telegramVersion: context.telegramVersion,
  });
}

function buildBaseContext() {
  return {
    initData: "",
    source: "missing",
    isTelegramWebApp: Boolean(telegram),
    hasTelegramUser: Boolean(telegram?.initDataUnsafe?.user),
    attemptedSources: [],
    diagnostics: [],
    telegramPlatform: normalizeValue(telegram?.platform) || "",
    telegramVersion: normalizeValue(telegram?.version) || "",
    waitedMs: 0,
  };
}

export async function createTelegramLaunchContext({ extraWait = false } = {}) {
  configureTelegramChrome();

  const context = buildBaseContext();
  context.attemptedSources = buildAttemptedSources(context);
  context.diagnostics.push(context.isTelegramWebApp ? "telegram-web-app:present" : "telegram-web-app:missing");
  context.diagnostics.push(context.hasTelegramUser ? "telegram-user:present" : "telegram-user:missing");

  const immediateLaunch = readTelegramLiveSources();
  if (immediateLaunch.value) {
    persistInitData(immediateLaunch.value, immediateLaunch.source);
    context.initData = immediateLaunch.value;
    context.source = immediateLaunch.source;
    context.diagnostics.push(`launch:${immediateLaunch.source}`);
    logLaunchContext(context);
    return context;
  }

  const queryLaunch = readLaunchParams();
  if (queryLaunch.value) {
    stripSensitiveLaunchParams();
    persistInitData(queryLaunch.value, queryLaunch.source);
    context.initData = queryLaunch.value;
    context.source = queryLaunch.source;
    context.diagnostics.push(`launch:${queryLaunch.source}`);
    context.diagnostics.push(`launch-scope:${queryLaunch.scope ?? "unknown"}`);
    logLaunchContext(context);
    return context;
  }

  const budgetMs = resolveWaitBudget({ extraWait });
  context.diagnostics.push(`wait-budget-ms:${budgetMs}`);
  const liveLaunch = await waitForLiveInitData({ budgetMs });
  context.waitedMs = liveLaunch.waitedMs;
  context.diagnostics.push(`waited-ms:${liveLaunch.waitedMs}`);
  context.diagnostics.push(`poll-attempts:${liveLaunch.attempts}`);
  if (liveLaunch.value) {
    persistInitData(liveLaunch.value, liveLaunch.source);
    context.initData = liveLaunch.value;
    context.source = liveLaunch.source;
    context.diagnostics.push(`launch:${liveLaunch.source}`);
    logLaunchContext(context);
    return context;
  }

  const persistedLaunch = restorePersistedInitData();
  if (persistedLaunch.value) {
    context.initData = persistedLaunch.value;
    context.source = persistedLaunch.source || "session-storage";
    context.diagnostics.push(`launch:${context.source}`);
    if (persistedLaunch.ageMs !== null) {
      context.diagnostics.push(`session-storage-age-ms:${persistedLaunch.ageMs}`);
    }
    logLaunchContext(context);
    return context;
  }

  context.diagnostics.push("launch:missing");
  logLaunchContext(context);
  return context;
}

export function buildLaunchFailureCopy(context, requestError = null) {
  if (requestError?.code === "expired_init_data") {
    return {
      title: "Откройте рабочее место заново",
      message: "Сеанс рабочего места устарел. Вернитесь в бот и снова откройте его через кнопку меню.",
      detail: "Telegram передаёт временные данные запуска. После паузы их нужно обновить.",
    };
  }

  if (requestError?.code === "invalid_signature" || requestError?.code === "malformed_init_data") {
    return {
      title: "Не удалось подтвердить запуск",
      message: "Рабочее место открылось без корректных данных Telegram. Откройте его снова через кнопку меню в боте.",
      detail: "Если ссылка была открыта вручную в браузере, безопасный вход не сработает.",
    };
  }

  if (context.isTelegramWebApp) {
    return {
      title: "Telegram не передал запуск",
      message: "Рабочее место открылось внутри Telegram, но безопасные данные запуска ещё не пришли.",
      detail: "Закройте окно и снова откройте «Рабочее место» кнопкой меню в чате с ботом.",
    };
  }

  return {
    title: "Откройте рабочее место из Telegram",
    message: "Для безопасного входа рабочее место нужно запускать из кнопки меню в чате с ботом.",
    detail: "Если кнопка меню не видна, проверьте настройку публичного HTTPS URL рабочего места.",
  };
}
