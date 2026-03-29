from enum import Enum

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass


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
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    MESSAGE_ADDED = "message_added"
    TAG_ADDED = "tag_added"
    TAG_REMOVED = "tag_removed"
    ESCALATED = "escalated"
    CLOSED = "closed"
