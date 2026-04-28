from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ApplicationError(Exception):
    public_message: str
    code: str

    def __str__(self) -> str:
        return self.public_message


class NotFoundError(ApplicationError):
    def __init__(self, message: str = "Ресурс не найден.") -> None:
        super().__init__(message, "not_found")


class ForbiddenError(ApplicationError):
    def __init__(self, message: str = "Доступ запрещён.") -> None:
        super().__init__(message, "forbidden")


class ValidationAppError(ApplicationError):
    def __init__(self, message: str = "Некорректный запрос.") -> None:
        super().__init__(message, "validation_error")


class RateLimitError(ApplicationError):
    def __init__(self, message: str = "Слишком много запросов.") -> None:
        super().__init__(message, "rate_limited")


class BackendUnavailableError(ApplicationError):
    def __init__(self, message: str = "Backend сервис временно недоступен.") -> None:
        super().__init__(message, "backend_unavailable")


class AIUnavailableError(ApplicationError):
    def __init__(self, message: str = "AI-service временно недоступен.") -> None:
        super().__init__(message, "ai_unavailable")


class ConcurrencyConflictError(ApplicationError):
    def __init__(self, message: str = "Операция конфликтует с другим изменением.") -> None:
        super().__init__(message, "concurrency_conflict")
