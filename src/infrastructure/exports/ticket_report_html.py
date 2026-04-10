from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from application.use_cases.tickets.exports import (
    TicketReport,
    TicketReportAttachment,
    TicketReportEvent,
    TicketReportInternalNote,
    TicketReportMessage,
)
from domain.enums.tickets import (
    TicketAttachmentKind,
    TicketEventType,
    TicketMessageSenderType,
    TicketStatus,
)


def render_ticket_report_html(report: TicketReport) -> bytes:
    generated_at = _format_timestamp(datetime.now(UTC))
    status_pill = (
        f'<span class="pill {_status_css(report.status)}">'
        f"{escape(_status_label(report.status))}"
        "</span>"
    )
    feedback_rating = str(report.feedback.rating) if report.feedback is not None else "Нет"
    feedback_comment = (
        report.feedback.comment or "Нет" if report.feedback is not None else "Нет"
    )
    feedback_received = (
        _format_timestamp(report.feedback.submitted_at) if report.feedback is not None else "Нет"
    )
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Отчёт по заявке {escape(report.public_number)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4efe6;
      --panel: #fffdf9;
      --panel-strong: #ffffff;
      --border: #ded5c8;
      --text: #1f2430;
      --muted: #67707d;
      --accent: #264653;
      --accent-soft: #e7eef0;
      --good: #2d6a4f;
      --warn: #9c6644;
      --shadow: 0 18px 40px rgba(31, 36, 48, 0.08);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(38, 70, 83, 0.09), transparent 36%),
        linear-gradient(180deg, #f7f2ea 0%, var(--bg) 100%);
      color: var(--text);
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      line-height: 1.55;
      padding: 32px 18px 48px;
    }}
    .page {{
      max-width: 980px;
      margin: 0 auto;
    }}
    .hero {{
      background: linear-gradient(135deg, var(--panel-strong), #f7f4ee);
      border: 1px solid var(--border);
      border-radius: 28px;
      box-shadow: var(--shadow);
      padding: 28px;
      margin-bottom: 20px;
    }}
    .eyebrow {{
      color: var(--muted);
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 32px;
      line-height: 1.15;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 7px 12px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 14px;
      font-weight: 600;
    }}
    .pill.status-closed {{ background: #e4efe9; color: var(--good); }}
    .pill.status-escalated {{ background: #f7ebe2; color: var(--warn); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }}
    .card {{
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 18px 20px;
      box-shadow: 0 8px 24px rgba(31, 36, 48, 0.04);
    }}
    .card h2 {{
      margin: 0 0 14px;
      font-size: 18px;
    }}
    .meta-list {{
      display: grid;
      gap: 12px;
    }}
    .meta-item {{
      border-top: 1px solid rgba(222, 213, 200, 0.65);
      padding-top: 12px;
    }}
    .meta-item:first-child {{
      border-top: 0;
      padding-top: 0;
    }}
    .label {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 4px;
    }}
    .value {{
      font-size: 15px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .timeline {{
      display: grid;
      gap: 12px;
    }}
    .timeline-item {{
      border-left: 3px solid var(--accent-soft);
      padding-left: 14px;
    }}
    .timeline-title {{
      font-weight: 600;
    }}
    .timeline-time {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 2px;
    }}
    .timeline-detail {{
      margin-top: 5px;
    }}
    .transcript {{
      display: grid;
      gap: 14px;
    }}
    .message {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px 18px;
    }}
    .message-head {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 10px;
    }}
    .message-role {{
      font-weight: 600;
    }}
    .message-time {{
      color: var(--muted);
      font-size: 13px;
    }}
    .message-body {{
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .muted {{
      color: var(--muted);
    }}
    @media (max-width: 640px) {{
      body {{ padding: 18px 12px 32px; }}
      .hero {{ padding: 22px 18px; border-radius: 22px; }}
      h1 {{ font-size: 26px; }}
      .card {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="eyebrow">Отчёт по заявке</div>
      <h1>{escape(report.public_number)}</h1>
      <div>{escape(report.subject)}</div>
      <div class="hero-meta">
        {status_pill}
        <span class="pill">Приоритет: {escape(_priority_label(report.priority))}</span>
        <span class="pill">Подготовлен: {escape(generated_at)}</span>
      </div>
    </section>
    <section class="grid">
      <article class="card">
        <h2>Карточка</h2>
        <div class="meta-list">
          {_meta_item("Публичный ID", str(report.public_id))}
          {_meta_item("Клиент", f"Telegram chat ID {report.client_chat_id}")}
          {_meta_item("Категория", report.category_title or "Не указана")}
          {_meta_item("Код категории", report.category_code or "Не указан")}
          {_meta_item("Оператор", _assigned_operator(report))}
          {_meta_item("Теги", ", ".join(report.tags) if report.tags else "Нет")}
        </div>
      </article>
      <article class="card">
        <h2>Таймстемпы</h2>
        <div class="meta-list">
          {_meta_item("Создана", _format_timestamp(report.created_at))}
          {_meta_item("Обновлена", _format_timestamp(report.updated_at))}
          {_meta_item("Первый ответ", _format_timestamp(report.first_response_at))}
          {_meta_item("Время до первого ответа", _format_duration(report.first_response_seconds))}
          {_meta_item("Закрыта", _format_timestamp(report.closed_at))}
        </div>
      </article>
      <article class="card">
        <h2>Обратная связь</h2>
        <div class="meta-list">
          {_meta_item("Оценка", feedback_rating)}
          {_meta_item("Комментарий", feedback_comment)}
          {_meta_item("Получена", feedback_received)}
        </div>
      </article>
    </section>
    <section class="card">
      <h2>Ход заявки</h2>
      {_render_timeline(report.events)}
    </section>
    <section class="card">
      <h2>Переписка</h2>
      {_render_transcript(report.messages)}
    </section>
    <section class="card">
      <h2>Внутренние заметки</h2>
      {_render_internal_notes(report.internal_notes)}
    </section>
  </div>
</body>
</html>
"""
    return html.encode("utf-8")


def _meta_item(label: str, value: str) -> str:
    return (
        '<div class="meta-item">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(value)}</div>'
        "</div>"
    )


def _render_timeline(events: tuple[TicketReportEvent, ...]) -> str:
    if not events:
        return '<div class="muted">Значимых событий не найдено.</div>'

    items = []
    for event in events:
        detail = _event_detail(event)
        detail_html = (
            f'<div class="timeline-detail">{escape(detail)}</div>' if detail is not None else ""
        )
        items.append(
            '<div class="timeline-item">'
            f'<div class="timeline-title">{escape(_event_title(event.event_type))}</div>'
            f'<div class="timeline-time">{escape(_format_timestamp(event.created_at))}</div>'
            f"{detail_html}"
            "</div>"
        )
    return f'<div class="timeline">{"".join(items)}</div>'


def _render_transcript(messages: tuple[TicketReportMessage, ...]) -> str:
    if not messages:
        return '<div class="muted">Сообщений пока нет.</div>'

    items = []
    for message in messages:
        items.append(
            '<article class="message">'
            '<div class="message-head">'
            f'<div class="message-role">{escape(_message_sender_label(message))}</div>'
            f'<div class="message-time">{escape(_format_timestamp(message.created_at))}</div>'
            "</div>"
            f'<div class="message-body">{escape(_message_body(message))}</div>'
            "</article>"
        )
    return f'<div class="transcript">{"".join(items)}</div>'


def _render_internal_notes(notes: tuple[TicketReportInternalNote, ...]) -> str:
    if not notes:
        return '<div class="muted">Заметок пока нет.</div>'

    items = []
    for note in notes:
        items.append(
            '<article class="message">'
            '<div class="message-head">'
            f'<div class="message-role">{escape(_internal_note_author(note))}</div>'
            f'<div class="message-time">{escape(_format_timestamp(note.created_at))}</div>'
            "</div>"
            f'<div class="message-body">{escape(note.text)}</div>'
            "</article>"
        )
    return f'<div class="transcript">{"".join(items)}</div>'


def _assigned_operator(report: TicketReport) -> str:
    if report.assigned_operator_id is None:
        return "Не назначен"
    if report.assigned_operator_name:
        return report.assigned_operator_name
    return f"Оператор #{report.assigned_operator_id}"


def _message_sender_label(message: TicketReportMessage) -> str:
    if message.sender_type == TicketMessageSenderType.CLIENT:
        return "Клиент"
    if message.sender_operator_name:
        return f"Оператор {message.sender_operator_name}"
    if message.sender_type == TicketMessageSenderType.SYSTEM:
        return "Система"
    return "Оператор"


def _message_body(message: TicketReportMessage) -> str:
    if message.attachment is None:
        return message.text or ""

    parts = [_attachment_label(message.attachment)]
    if message.text:
        parts.extend(("", message.text))
    return "\n".join(parts)


def _attachment_label(attachment: TicketReportAttachment) -> str:
    if attachment.kind == TicketAttachmentKind.PHOTO:
        return "Фото"
    if attachment.kind == TicketAttachmentKind.VOICE:
        return "Голосовое сообщение"
    if attachment.kind == TicketAttachmentKind.VIDEO:
        return "Видео"
    if attachment.filename:
        return f"Файл · {attachment.filename}"
    return "Файл"


def _internal_note_author(note: TicketReportInternalNote) -> str:
    if note.author_operator_name:
        return f"Заметка · {note.author_operator_name}"
    return f"Заметка · оператор #{note.author_operator_id}"


def _event_title(event_type: TicketEventType) -> str:
    mapping = {
        TicketEventType.CREATED: "Заявка создана",
        TicketEventType.QUEUED: "Поставлена в очередь",
        TicketEventType.ASSIGNED: "Назначена оператору",
        TicketEventType.REASSIGNED: "Передана другому оператору",
        TicketEventType.AUTO_REASSIGNED: "Автоматически передана",
        TicketEventType.ESCALATED: "Переведена на эскалацию",
        TicketEventType.AUTO_ESCALATED: "Автоматически эскалирована",
        TicketEventType.SLA_BREACHED_FIRST_RESPONSE: "Нарушен SLA первого ответа",
        TicketEventType.SLA_BREACHED_RESOLUTION: "Нарушен SLA решения",
        TicketEventType.TAG_ADDED: "Добавлена метка",
        TicketEventType.TAG_REMOVED: "Снята метка",
        TicketEventType.CLOSED: "Заявка закрыта",
    }
    return mapping.get(event_type, event_type.value)


def _event_detail(event: TicketReportEvent) -> str | None:
    payload = event.payload_json or {}
    if event.event_type in {TicketEventType.TAG_ADDED, TicketEventType.TAG_REMOVED}:
        tag = payload.get("tag")
        if isinstance(tag, str) and tag:
            return tag
        return None
    if event.event_type in {
        TicketEventType.ASSIGNED,
        TicketEventType.REASSIGNED,
        TicketEventType.AUTO_REASSIGNED,
    }:
        assigned_operator_id = payload.get("assigned_operator_id")
        if isinstance(assigned_operator_id, int):
            return f"Оператор #{assigned_operator_id}"
        return None
    from_status = payload.get("from_status")
    to_status = payload.get("to_status")
    if isinstance(from_status, str) and isinstance(to_status, str):
        return f"{from_status} -> {to_status}"
    return None


def _status_label(status: TicketStatus) -> str:
    return {
        TicketStatus.NEW: "Новая",
        TicketStatus.QUEUED: "В очереди",
        TicketStatus.ASSIGNED: "В работе",
        TicketStatus.ESCALATED: "Эскалация",
        TicketStatus.CLOSED: "Закрыта",
    }[status]


def _status_css(status: TicketStatus) -> str:
    return f"status-{status.value}"


def _priority_label(priority: str) -> str:
    return {
        "low": "низкий",
        "normal": "обычный",
        "high": "высокий",
        "urgent": "срочный",
    }.get(priority, priority)


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "Нет"
    return value.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")


def _format_duration(value: int | None) -> str:
    if value is None:
        return "Нет"
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} ч {minutes} мин"
    if minutes:
        return f"{minutes} мин {seconds} сек"
    return f"{seconds} сек"
