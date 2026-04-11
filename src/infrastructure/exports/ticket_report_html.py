from __future__ import annotations

import base64
import mimetypes
from collections.abc import Iterable
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

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
from infrastructure.assets.storage import LocalTicketAssetStorage
from infrastructure.config.settings import get_settings

EMBEDDED_PHOTO_MAX_BYTES = 8 * 1024 * 1024
SAFE_EMBEDDED_IMAGE_MIME_TYPES = frozenset({"image/gif", "image/jpeg", "image/png", "image/webp"})


def render_ticket_report_html(report: TicketReport) -> bytes:
    generated_at = _format_timestamp(datetime.now(UTC))
    attachment_count = sum(1 for message in report.messages if message.attachment is not None)
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Дело {escape(report.public_number)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4efe8;
      --paper: rgba(255, 252, 247, 0.94);
      --paper-strong: #fffdf9;
      --line: rgba(78, 65, 53, 0.12);
      --line-strong: rgba(78, 65, 53, 0.20);
      --text: #1f2328;
      --muted: #6a6f78;
      --accent: #2d5a63;
      --accent-soft: rgba(45, 90, 99, 0.10);
      --client-soft: rgba(138, 101, 73, 0.10);
      --note-soft: rgba(85, 100, 75, 0.10);
      --success: #4f6b57;
      --warning: #8c6647;
      --shadow: 0 22px 60px rgba(31, 35, 40, 0.08);
      --radius-xl: 32px;
      --radius-lg: 24px;
      --radius-md: 18px;
      --radius-sm: 14px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(45, 90, 99, 0.09), transparent 30%),
        linear-gradient(180deg, #faf7f2 0%, var(--bg) 100%);
      color: var(--text);
      font-family: "SF Pro Text", "Segoe UI", sans-serif;
      line-height: 1.6;
      padding: 32px 16px 56px;
    }}
    .page {{ max-width: 1160px; margin: 0 auto; }}
    .hero {{
      background: linear-gradient(160deg, rgba(255, 255, 255, 0.96), rgba(248, 242, 234, 0.98));
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
      padding: 34px 34px 28px;
      margin-bottom: 18px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(280px, 1fr);
      gap: 22px;
      align-items: start;
    }}
    .eyebrow {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 12px;
      margin-bottom: 12px;
    }}
    h1, h2, h3 {{
      font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
      font-weight: 600;
      letter-spacing: -0.02em;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 40px;
      line-height: 1.04;
    }}
    .hero-subtitle {{
      max-width: 760px;
      font-size: 18px;
      color: rgba(31, 35, 40, 0.88);
    }}
    .pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 20px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      padding: 9px 14px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 14px;
      font-weight: 600;
    }}
    .pill.status-closed {{ background: rgba(79, 107, 87, 0.12); color: var(--success); }}
    .pill.status-escalated {{ background: rgba(140, 102, 71, 0.12); color: var(--warning); }}
    .hero-aside {{
      background: rgba(255, 255, 255, 0.62);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      padding: 18px 18px 14px;
    }}
    .hero-aside-title {{
      margin: 0 0 12px;
      font-size: 18px;
    }}
    .hero-aside-list {{
      display: grid;
      gap: 12px;
    }}
    .meta-label {{
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .meta-value {{
      font-size: 15px;
      word-break: break-word;
    }}
    .meta-value a {{
      color: var(--accent);
      text-decoration: none;
    }}
    .section {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      box-shadow: 0 10px 26px rgba(31, 35, 40, 0.05);
      padding: 26px;
      margin-bottom: 16px;
    }}
    .section h2 {{
      margin: 0 0 14px;
      font-size: 24px;
    }}
    .section-intro {{
      color: var(--muted);
      margin-bottom: 16px;
    }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .stat-card {{
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      padding: 18px;
    }}
    .stat-label {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .stat-value {{
      font-size: 26px;
      font-weight: 700;
      line-height: 1.1;
      margin-bottom: 6px;
    }}
    .stat-note {{
      color: var(--muted);
      font-size: 14px;
    }}
    .split {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .panel {{
      background: rgba(255, 255, 255, 0.76);
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      padding: 18px;
    }}
    .panel h3 {{
      margin: 0 0 12px;
      font-size: 18px;
    }}
    .list {{
      display: grid;
      gap: 12px;
    }}
    .list-item {{
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }}
    .list-item:first-child {{
      padding-top: 0;
      border-top: 0;
    }}
    .timeline {{
      display: grid;
      gap: 12px;
    }}
    .timeline-item {{
      position: relative;
      padding: 2px 0 0 18px;
      border-left: 2px solid rgba(45, 90, 99, 0.16);
    }}
    .timeline-item::before {{
      content: "";
      position: absolute;
      left: -6px;
      top: 10px;
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: #fff;
      border: 2px solid rgba(45, 90, 99, 0.24);
    }}
    .timeline-title {{
      font-weight: 700;
      margin-bottom: 2px;
    }}
    .timeline-time {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }}
    .timeline-detail {{
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .gallery {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }}
    .asset-card {{
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      overflow: hidden;
      min-height: 100%;
    }}
    .asset-image {{
      display: block;
      width: 100%;
      max-height: 230px;
      object-fit: cover;
      background: #efe7de;
    }}
    .asset-body {{
      padding: 16px;
    }}
    .asset-title {{
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .asset-meta {{
      color: var(--muted);
      font-size: 14px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .transcript {{
      display: grid;
      gap: 12px;
    }}
    .message {{
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      padding: 18px;
      background: rgba(255, 255, 255, 0.78);
    }}
    .message.client {{ background: rgba(255, 252, 247, 0.82); }}
    .message.operator {{ background: rgba(248, 252, 252, 0.84); }}
    .message.system {{ background: rgba(249, 248, 245, 0.84); }}
    .message-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}
    .message-role {{
      font-weight: 700;
    }}
    .message-time {{
      color: var(--muted);
      font-size: 13px;
    }}
    .message-body {{
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .message-attachment {{
      margin-top: 14px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--line);
      overflow: hidden;
      background: rgba(250, 247, 242, 0.78);
    }}
    .message-attachment .asset-body {{
      padding: 14px;
    }}
    .notes {{
      display: grid;
      gap: 12px;
    }}
    .note {{
      background: rgba(250, 252, 248, 0.84);
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      padding: 18px;
    }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 780px) {{
      body {{ padding: 18px 12px 32px; }}
      .hero {{ padding: 24px 22px; }}
      .hero-grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 32px; }}
      .section {{ padding: 20px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    {_render_hero(report, generated_at)}
    <section class="stats-grid">
      {_stat_card("Статус", _status_label(report.status), _status_hint(report.status))}
      {_stat_card("Сообщения", str(len(report.messages)), "Полная лента переписки по делу")}
      {_stat_card("Вложения", str(attachment_count), "Фото и файлы, сохранённые в материалах")}
      {
        _stat_card(
            "Заметки",
            str(len(report.internal_notes)),
            "Внутренний handoff и рабочий контекст",
        )
    }
    </section>
    <section class="section">
      <h2>Сводка дела</h2>
      <div class="section-intro">
        Короткий обзор обращения, итогов и клиентской обратной связи.
      </div>
      <div class="split">
        <div class="panel">
          <h3>Обращение</h3>
          <div class="list">
            {_list_item("Суть", _first_client_message(report.messages) or report.subject)}
            {
        _list_item(
            "Последний шаг",
            _message_summary(report.messages[-1] if report.messages else None),
        )
    }
            {_list_item("Итог", _closure_summary(report))}
          </div>
        </div>
        <div class="panel">
          <h3>Качество</h3>
          {_render_feedback_summary(report)}
        </div>
      </div>
    </section>
    <section class="section">
      <h2>Карточка</h2>
      <div class="split">
        <div class="panel">
          <h3>Реквизиты</h3>
          <div class="list">
            {_list_item("Публичный ID", str(report.public_id))}
            {_list_item("Клиент", f"Telegram chat ID {report.client_chat_id}")}
            {_list_item("Категория", report.category_title or "Не указана")}
            {_list_item("Код категории", report.category_code or "Не указан")}
            {_list_item_html("Ответственный", _operator_identity_html(report))}
            {_list_item("Теги", ", ".join(report.tags) if report.tags else "Нет")}
          </div>
        </div>
        <div class="panel">
          <h3>Время</h3>
          <div class="list">
            {_list_item("Создана", _format_timestamp(report.created_at))}
            {_list_item("Обновлена", _format_timestamp(report.updated_at))}
            {_list_item("Первый ответ", _format_timestamp(report.first_response_at))}
            {_list_item("До первого ответа", _format_duration(report.first_response_seconds))}
            {_list_item("Закрыта", _format_timestamp(report.closed_at))}
          </div>
        </div>
      </div>
    </section>
    <section class="section">
      <h2>Ход заявки</h2>
      <div class="section-intro">Ключевые продуктовые события по жизненному циклу дела.</div>
      {_render_timeline(report.events)}
    </section>
    <section class="section">
      <h2>Материалы дела</h2>
      <div class="section-intro">
        Фотографии встраиваются прямо в отчёт. Остальные вложения сохраняются как
        структурированные ссылки на материалы.
      </div>
      {_render_attachment_gallery(report.messages)}
    </section>
    <section class="section">
      <h2>Переписка</h2>
      <div class="section-intro">
        Полная последовательность сообщений клиента, оператора и системных
        событий.
      </div>
      {_render_transcript(report.messages)}
    </section>
    <section class="section">
      <h2>Внутренние заметки</h2>
      <div class="section-intro">Рабочие комментарии команды, включённые в выгрузку.</div>
      {_render_internal_notes(report.internal_notes)}
    </section>
  </div>
</body>
</html>
"""
    return html.encode("utf-8")


def _render_hero(report: TicketReport, generated_at: str) -> str:
    return (
        '<section class="hero">'
        '<div class="hero-grid">'
        "<div>"
        '<div class="eyebrow">Case File</div>'
        f"<h1>{escape(report.public_number)}</h1>"
        f'<div class="hero-subtitle">{escape(report.subject)}</div>'
        '<div class="pill-row">'
        f'<span class="pill {_status_css(report.status)}">'
        f"{escape(_status_label(report.status))}</span>"
        f'<span class="pill">Приоритет: {escape(_priority_label(report.priority))}</span>'
        f'<span class="pill">Экспорт: HTML</span>'
        f'<span class="pill">Подготовлен: {escape(generated_at)}</span>'
        "</div>"
        "</div>"
        '<aside class="hero-aside">'
        '<h3 class="hero-aside-title">Навигация по делу</h3>'
        '<div class="hero-aside-list">'
        f"{_hero_meta_item('Категория', report.category_title or 'Не указана')}"
        f"{_hero_meta_item('Ответственный', _plain_operator_identity(report))}"
        f"{_hero_meta_item('Первый ответ', _format_duration(report.first_response_seconds))}"
        f"{_hero_meta_item('Закрыта', _format_timestamp(report.closed_at))}"
        "</div>"
        "</aside>"
        "</div>"
        "</section>"
    )


def _hero_meta_item(label: str, value: str) -> str:
    return (
        "<div>"
        f'<div class="meta-label">{escape(label)}</div>'
        f'<div class="meta-value">{escape(value)}</div>'
        "</div>"
    )


def _stat_card(label: str, value: str, note: str) -> str:
    return (
        '<article class="stat-card">'
        f'<div class="stat-label">{escape(label)}</div>'
        f'<div class="stat-value">{escape(value)}</div>'
        f'<div class="stat-note">{escape(note)}</div>'
        "</article>"
    )


def _render_feedback_summary(report: TicketReport) -> str:
    if report.feedback is None:
        return (
            '<div class="list">'
            f"{_list_item('Оценка', 'Не получена')}"
            f"{_list_item('Комментарий', 'Клиент не оставил комментарий.')}"
            f"{_list_item('Фиксация', 'Дело закрыто без отдельной оценки.')}"
            "</div>"
        )
    return (
        '<div class="list">'
        f"{_list_item('Оценка', f'{report.feedback.rating} / 5')}"
        f"{_list_item('Комментарий', report.feedback.comment or 'Без комментария')}"
        f"{_list_item('Получена', _format_timestamp(report.feedback.submitted_at))}"
        "</div>"
    )


def _list_item(label: str, value: str) -> str:
    return (
        '<div class="list-item">'
        f'<div class="meta-label">{escape(label)}</div>'
        f'<div class="meta-value">{escape(value)}</div>'
        "</div>"
    )


def _list_item_html(label: str, value_html: str) -> str:
    return (
        '<div class="list-item">'
        f'<div class="meta-label">{escape(label)}</div>'
        f'<div class="meta-value">{value_html}</div>'
        "</div>"
    )


def _render_timeline(events: tuple[TicketReportEvent, ...]) -> str:
    if not events:
        return '<div class="muted">Значимых событий по делу не найдено.</div>'

    items = []
    for event in events:
        detail = _event_detail(event)
        detail_html = (
            f'<div class="timeline-detail">{escape(detail)}</div>' if detail is not None else ""
        )
        items.append(
            '<article class="timeline-item">'
            f'<div class="timeline-title">{escape(_event_title(event.event_type))}</div>'
            f'<div class="timeline-time">{escape(_format_timestamp(event.created_at))}</div>'
            f"{detail_html}"
            "</article>"
        )
    return f'<div class="timeline">{"".join(items)}</div>'


def _render_attachment_gallery(messages: Iterable[TicketReportMessage]) -> str:
    attachments = [
        (index, message.created_at, message.attachment)
        for index, message in enumerate(messages, start=1)
        if message.attachment is not None
    ]
    if not attachments:
        return '<div class="muted">Вложений в деле нет.</div>'

    cards: list[str] = []
    for index, created_at, attachment in attachments:
        assert attachment is not None
        embedded_photo = (
            _load_embedded_photo(attachment)
            if attachment.kind == TicketAttachmentKind.PHOTO
            else None
        )
        image_html = (
            (
                f'<img class="asset-image" src="{embedded_photo}" '
                f'alt="{escape(_attachment_label(attachment))}">'
            )
            if embedded_photo is not None
            else ""
        )
        cards.append(
            '<article class="asset-card">'
            f"{image_html}"
            '<div class="asset-body">'
            f'<div class="asset-title">{escape(f"{index}. {_attachment_label(attachment)}")}</div>'
            f'<div class="asset-meta">{escape(_format_timestamp(created_at))}</div>'
            f'<div class="asset-meta">{escape(_attachment_meta_text(attachment))}</div>'
            "</div>"
            "</article>"
        )
    return f'<div class="gallery">{"".join(cards)}</div>'


def _render_transcript(messages: tuple[TicketReportMessage, ...]) -> str:
    if not messages:
        return '<div class="muted">Сообщений в переписке нет.</div>'

    items = []
    for message in messages:
        attachment_html = _render_message_attachment(message.attachment)
        body = escape(message.text) if message.text else '<span class="muted">Без текста</span>'
        items.append(
            f'<article class="message {_message_css(message.sender_type)}">'
            '<div class="message-head">'
            f'<div class="message-role">{escape(_message_sender_label(message))}</div>'
            f'<div class="message-time">{escape(_format_timestamp(message.created_at))}</div>'
            "</div>"
            f'<div class="message-body">{body}</div>'
            f"{attachment_html}"
            "</article>"
        )
    return f'<div class="transcript">{"".join(items)}</div>'


def _render_message_attachment(attachment: TicketReportAttachment | None) -> str:
    if attachment is None:
        return ""

    embedded_photo = (
        _load_embedded_photo(attachment) if attachment.kind == TicketAttachmentKind.PHOTO else None
    )
    image_html = (
        (
            f'<img class="asset-image" src="{embedded_photo}" '
            f'alt="{escape(_attachment_label(attachment))}">'
        )
        if embedded_photo is not None
        else ""
    )
    return (
        '<div class="message-attachment">'
        f"{image_html}"
        '<div class="asset-body">'
        f'<div class="asset-title">{escape(_attachment_label(attachment))}</div>'
        f'<div class="asset-meta">{escape(_attachment_meta_text(attachment))}</div>'
        "</div>"
        "</div>"
    )


def _render_internal_notes(notes: tuple[TicketReportInternalNote, ...]) -> str:
    if not notes:
        return '<div class="muted">Выгрузка внутренних заметок пуста.</div>'

    items = []
    for note in notes:
        items.append(
            '<article class="note">'
            '<div class="message-head">'
            f'<div class="message-role">{escape(_internal_note_author(note))}</div>'
            f'<div class="message-time">{escape(_format_timestamp(note.created_at))}</div>'
            "</div>"
            f'<div class="message-body">{escape(note.text)}</div>'
            "</article>"
        )
    return f'<div class="notes">{"".join(items)}</div>'


def _operator_identity_html(report: TicketReport) -> str:
    plain = escape(_plain_operator_identity(report))
    href = _build_operator_link(report)
    if href is None:
        return plain
    return f'<a href="{escape(href)}">{plain}</a>'


def _plain_operator_identity(report: TicketReport) -> str:
    if report.assigned_operator_id is None:
        return "Не назначен"
    if report.assigned_operator_name:
        return report.assigned_operator_name
    return f"Оператор #{report.assigned_operator_id}"


def _build_operator_link(report: TicketReport) -> str | None:
    if report.assigned_operator_username:
        return f"https://t.me/{quote(report.assigned_operator_username)}"
    if report.assigned_operator_telegram_user_id is not None:
        return f"tg://user?id={report.assigned_operator_telegram_user_id}"
    return None


def _message_sender_label(message: TicketReportMessage) -> str:
    if message.sender_type == TicketMessageSenderType.CLIENT:
        return "Клиент"
    if message.sender_operator_name:
        return f"Оператор · {message.sender_operator_name}"
    if message.sender_type == TicketMessageSenderType.SYSTEM:
        return "Система"
    return "Оператор"


def _message_css(sender_type: TicketMessageSenderType) -> str:
    if sender_type == TicketMessageSenderType.CLIENT:
        return "client"
    if sender_type == TicketMessageSenderType.SYSTEM:
        return "system"
    return "operator"


def _message_summary(message: TicketReportMessage | None) -> str:
    if message is None:
        return "Переписка ещё не велась."
    if message.text:
        return " ".join(message.text.split())
    if message.attachment is not None:
        return _attachment_label(message.attachment)
    return "Сообщение без текста."


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


def _attachment_meta_text(attachment: TicketReportAttachment) -> str:
    parts = [f"Тип: {attachment.kind.value}"]
    if attachment.filename:
        parts.append(f"Имя: {attachment.filename}")
    if attachment.mime_type:
        parts.append(f"MIME: {attachment.mime_type}")
    if attachment.storage_path:
        parts.append(f"Материал: {attachment.storage_path}")
    return " · ".join(parts)


def _internal_note_author(note: TicketReportInternalNote) -> str:
    if note.author_operator_name:
        return f"Внутренняя заметка · {note.author_operator_name}"
    return f"Внутренняя заметка · оператор #{note.author_operator_id}"


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


def _status_hint(status: TicketStatus) -> str:
    hints = {
        TicketStatus.NEW: "Карточка создана, работа ещё не начата",
        TicketStatus.QUEUED: "Дело ожидало назначения",
        TicketStatus.ASSIGNED: "Дело велось оператором",
        TicketStatus.ESCALATED: "Требовалось усиленное внимание",
        TicketStatus.CLOSED: "Дело завершено и передано в архив",
    }
    return hints[status]


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


def _closure_summary(report: TicketReport) -> str:
    if report.closed_at is None:
        return "Дело ещё не закрыто."
    return (
        f"Закрыто {_format_timestamp(report.closed_at)}. "
        f"Первый ответ: {_format_duration(report.first_response_seconds)}."
    )


def _first_client_message(messages: tuple[TicketReportMessage, ...]) -> str | None:
    for message in messages:
        if message.sender_type != TicketMessageSenderType.CLIENT:
            continue
        if message.text:
            return " ".join(message.text.split())
        if message.attachment is not None:
            return _attachment_label(message.attachment)
    return None


def _load_embedded_photo(attachment: TicketReportAttachment) -> str | None:
    if attachment.storage_path is None:
        return None
    asset_path = _resolve_asset_path(attachment.storage_path)
    if asset_path is None or not asset_path.exists():
        return None
    try:
        raw = asset_path.read_bytes()
    except OSError:
        return None
    if len(raw) > EMBEDDED_PHOTO_MAX_BYTES:
        return None
    mime_type = _resolve_photo_mime_type(attachment, asset_path)
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _resolve_asset_path(storage_path: str) -> Path | None:
    try:
        storage = LocalTicketAssetStorage(get_settings().assets.path)
    except Exception:
        return None
    try:
        return storage.resolve_path(storage_path)
    except Exception:
        return None


def _resolve_photo_mime_type(attachment: TicketReportAttachment, asset_path: Path) -> str:
    if attachment.mime_type:
        mime_type = attachment.mime_type.strip().lower()
        if mime_type in SAFE_EMBEDDED_IMAGE_MIME_TYPES:
            return mime_type
        return "image/jpeg"
    guessed, _ = mimetypes.guess_type(asset_path.name)
    guessed_mime = (guessed or "image/jpeg").lower()
    if guessed_mime not in SAFE_EMBEDDED_IMAGE_MIME_TYPES:
        return "image/jpeg"
    return guessed_mime
