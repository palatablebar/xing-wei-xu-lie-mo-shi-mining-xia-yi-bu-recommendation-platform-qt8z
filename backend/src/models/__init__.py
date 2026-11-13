"""ORM 模型聚合导出（Base 用于 create_all）。"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from src.models.user import User  # noqa: E402
from src.models.audit import AuditLog  # noqa: E402
from src.models.event_def import EventDef  # noqa: E402
from src.models.event_seq import EventSeq  # noqa: E402
from src.models.mine_run import MineRun  # noqa: E402
from src.models.pattern import Pattern  # noqa: E402
from src.models.recommendation import Recommendation  # noqa: E402

__all__ = [
    "Base",
    "User",
    "AuditLog",
    "EventDef",
    "EventSeq",
    "MineRun",
    "Pattern",
    "Recommendation",
]
