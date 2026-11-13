"""导出服务：推荐名单 / 模式库 CSV（UTF-8 BOM，Excel 直开不乱码）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import MODULE_LABELS, REC_PRIORITY_LABELS, REVIEW_STATUS_LABELS
from src.models.event_def import EventDef
from src.models.mine_run import MineRun
from src.models.pattern import Pattern
from src.models.recommendation import Recommendation
from src.utils.csv_export import to_csv


def _labels(db: Session) -> dict[str, str]:
    return {row.code: row.label for row in db.scalars(select(EventDef)).all()}


def recommendations_csv(db: Session, run_id: int | None = None) -> bytes:
    stmt = select(Recommendation)
    if run_id:
        stmt = stmt.where(Recommendation.run_id == run_id)
    rows_db = db.scalars(stmt.order_by(Recommendation.score.desc(), Recommendation.id)).all()
    labels = _labels(db)
    headers = [
        "用户ID",
        "最近事件后缀",
        "推荐下一步",
        "下一步名称",
        "模块",
        "置信度",
        "提升度",
        "分数",
        "优先级",
        "复核状态",
        "复核人",
        "复核备注",
        "生成时间",
    ]
    rows = [
        [
            item.user_id,
            " > ".join(item.suffix or []),
            item.next_event,
            labels.get(item.next_event, item.next_event),
            MODULE_LABELS.get(item.next_module, item.next_module),
            f"{item.confidence:.4f}",
            f"{item.lift:.4f}",
            f"{item.score:.4f}",
            REC_PRIORITY_LABELS.get(item.priority, item.priority),
            REVIEW_STATUS_LABELS.get(item.status, item.status),
            item.reviewer or "",
            item.review_note or "",
            item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else "",
        ]
        for item in rows_db
    ]
    return to_csv(headers, rows)


def patterns_csv(db: Session, run_id: int | None = None) -> bytes:
    stmt = select(Pattern)
    if run_id:
        stmt = stmt.where(Pattern.run_id == run_id)
    rows_db = db.scalars(stmt.order_by(Pattern.support_count.desc(), Pattern.id)).all()
    labels = _labels(db)
    headers = ["排名", "模式", "长度", "支持会话数", "支持度%", "置信度", "提升度", "运行ID"]
    rows = [
        [
            item.rank,
            " > ".join(labels.get(code, code) for code in (item.items or [])),
            item.length,
            item.support_count,
            f"{item.support_pct:.1f}",
            f"{item.confidence:.4f}",
            f"{item.lift:.4f}",
            item.run_id,
        ]
        for item in rows_db
    ]
    return to_csv(headers, rows)


def runs_csv(db: Session) -> bytes:
    runs = db.scalars(select(MineRun).order_by(MineRun.id)).all()
    headers = ["运行号", "最小支持度%", "最大长度", "模式数", "推荐数", "覆盖率%", "状态", "操作人", "开始时间", "结束时间"]
    rows = [
        [
            run.run_no,
            f"{run.min_support_pct:.1f}",
            run.max_len,
            run.pattern_count,
            run.rec_count,
            f"{run.coverage_pct:.1f}",
            run.status,
            run.operator_email,
            run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "",
            run.finished_at.strftime("%Y-%m-%d %H:%M") if run.finished_at else "",
        ]
        for run in runs
    ]
    return to_csv(headers, rows)
