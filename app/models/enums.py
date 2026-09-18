from enum import IntEnum


class RoomType(IntEnum):
    """会话类型，与 docs/05 §7 一致"""

    SINGLE = 1
    GROUP = 2


class MemberRole(IntEnum):
    OWNER = 1
    MEMBER = 2


class MessageType(IntEnum):
    TEXT = 1
    RECALL = 2
    IMAGE = 3
    FILE = 4
    EMOJI = 5
    SYSTEM = 6


class MessageStatus(IntEnum):
    NORMAL = 0
    DELETED = 1


class OutboxStatus(IntEnum):
    PENDING = 0
    SENT = 1
    DEAD = 2
