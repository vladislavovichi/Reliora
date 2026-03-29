from enum import StrEnum


class TicketStatus(StrEnum):
    NEW = "new"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    ESCALATED = "escalated"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TicketMessageSenderType(StrEnum):
    CLIENT = "client"
    OPERATOR = "operator"
    SYSTEM = "system"


class TicketEventType(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    REASSIGNED = "reassigned"
    MESSAGE_ADDED = "message_added"
    CLIENT_MESSAGE_ADDED = "client_message_added"
    OPERATOR_MESSAGE_ADDED = "operator_message_added"
    TAG_ADDED = "tag_added"
    TAG_REMOVED = "tag_removed"
    ESCALATED = "escalated"
    CLOSED = "closed"
