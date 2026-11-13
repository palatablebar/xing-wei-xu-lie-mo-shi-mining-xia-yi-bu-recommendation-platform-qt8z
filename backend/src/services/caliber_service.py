"""事件口径版本化服务：草稿 → 预演 → 统一发布（失败回滚）。

口径规则（参与挖掘/推荐的关键标记 = is_key / enabled）：
- 新口径下，会话序列先剔除「停用或非关键」事件，再进入 PrefixSpan 与推荐；
- 口径未发布前，正式挖掘/复核/导出继续按 event_defs 当前值（最近一次 published 版本）；
- 预演只在内存模拟，不写 patterns/recommendations，不影响任何正式数据；
- 发布在单事务内切换 event_defs 并落 CaliberVersion，任一步失败整体回滚；
- 回滚把 event_defs 还原到上一版本快照，并把当前版本标记为 rolled_back。
"""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.caliber import CaliberDraft, CaliberRehearsal, CaliberVersion
from src.models.event_def import EventDef
from src.models.event_seq import EventSeq
from src.models.pattern import Pattern
from src.models.recommendation import Recommendation
from src.services import recommender
from src.services.prefixspan import mine_patterns
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, local_now, utcnow

PATTERN_MIN_LEN = 2
DEFAULT_TOP_K = 50
DEFAULT_MIN_SUPPORT = 3.0
DEFAULT_MAX_LEN = 5
# 预演名单只带回前 N 条，避免响应体过大；计数仍为全量
REHEARSAL_SAMPLE_LIMIT = 50


# --------------------------------------------------------------------------- #
# 基础读取
# --------------------------------------------------------------------------- #
def current_caliber(db: Session) -> dict[str, dict]:
    """正式口径快照（event_defs 当前值），按事件码索引。"""
    return {
        row.code: {
            "code": row.code,
            "module": row.module,
            "label": row.label,
            "is_key": bool(row.is_key),
            "enabled": bool(row.enabled),
        }
        for row in db.scalars(select(EventDef).order_by(EventDef.id)).all()
    }


def active_draft(db: Session) -> CaliberDraft | None:
    return db.scalar(select(CaliberDraft).where(CaliberDraft.status == "active").order_by(CaliberDraft.id.desc()).limit(1))


def latest_version(db: Session) -> CaliberVersion | None:
    return db.scalar(select(CaliberVersion).order_by(CaliberVersion.id.desc()).limit(1))


def latest_published_version(db: Session) -> CaliberVersion | None:
    return db.scalar(
        select(CaliberVersion).where(CaliberVersion.status == "published").order_by(CaliberVersion.id.desc()).limit(1)
    )


def get_draft(db: Session, draft_id: int) -> CaliberDraft:
    row = db.get(CaliberDraft, draft_id)
    if row is None:
        raise AppError("NOT_FOUND", 404, {"entity": "caliber_draft", "id": draft_id})
    return row


def get_rehearsal(db: Session, rehearsal_id: int) -> CaliberRehearsal:
    row = db.get(CaliberRehearsal, rehearsal_id)
    if row is None:
        raise AppError("NOT_FOUND", 404, {"entity": "caliber_rehearsal", "id": rehearsal_id})
    return row


def get_version(db: Session, version_id: int) -> CaliberVersion:
    row = db.get(CaliberVersion, version_id)
    if row is None:
        raise AppError("NOT_FOUND", 404, {"entity": "caliber_version", "id": version_id})
    return row


# --------------------------------------------------------------------------- #
# 草稿
# --------------------------------------------------------------------------- #
def _draft_targets(caliber: dict[str, dict], changes: dict) -> dict[str, dict]:
    """把草稿变更叠加到正式口径上，得到目标口径（只含 is_key/enabled）。"""
    targets: dict[str, dict] = {}
    for code, item in caliber.items():
        patch = changes.get(code, {})
        targets[code] = {
            "is_key": bool(patch.get("is_key", item["is_key"])),
            "enabled": bool(patch.get("enabled", item["enabled"])),
        }
    return targets


def changed_codes(caliber: dict[str, dict], changes: dict) -> list[str]:
    codes: list[str] = []
    for code, patch in changes.items():
        base = caliber.get(code)
        if base is None:
            continue
        if patch.get("is_key") is not None and bool(patch["is_key"]) != bool(base["is_key"]):
            codes.append(code)
        elif patch.get("enabled") is not None and bool(patch["enabled"]) != bool(base["enabled"]):
            codes.append(code)
    return sorted(set(codes))


def ensure_draft(db: Session, actor_email: str) -> CaliberDraft:
    """取当前活跃草稿；没有则以最新版本为基准创建空草稿。"""
    draft = active_draft(db)
    if draft is not None:
        return draft
    base = latest_published_version(db)
    draft = CaliberDraft(
        status="active",
        base_version_id=base.id if base else None,
        changes={},
        created_by=actor_email,
    )
    db.add(draft)
    db.flush()
    return draft


def stage_draft(db: Session, payload: dict, actor_email: str) -> CaliberDraft:
    """把一次 is_key/enabled 修改写入草稿（不直接改正式 event_defs）。

    若改回的值与正式口径一致，则清掉该事件的草稿条目，避免无意义残留。
    """
    draft = ensure_draft(db, actor_email)
    code = payload["code"]
    event = db.scalar(select(EventDef).where(EventDef.code == code))
    if event is None:
        raise AppError("NOT_FOUND", 404, {"entity": "event", "code": code})
    changes = dict(draft.changes or {})
    entry = dict(changes.get(code, {}))
    if payload.get("is_key") is not None:
        entry["is_key"] = bool(payload["is_key"])
    if payload.get("enabled") is not None:
        entry["enabled"] = bool(payload["enabled"])
    # 与正式口径完全一致（只比较条目里实际存在的字段）-> 该事件无需变更，移除草稿条目
    same_as_live = all(entry[field] == bool(getattr(event, field)) for field in entry)
    if same_as_live:
        changes.pop(code, None)
    else:
        changes[code] = entry
    draft.changes = changes
    if payload.get("change_note"):
        draft.change_note = payload["change_note"]
    # 草稿内容变化后，旧预演失效
    for old in db.scalars(select(CaliberRehearsal).where(CaliberRehearsal.draft_id == draft.id)).all():
        if old.status == "ready":
            old.status = "stale"
    db.flush()
    return draft


def discard_draft(db: Session, draft: CaliberDraft) -> None:
    draft.status = "discarded"
    for item in db.scalars(select(CaliberRehearsal).where(CaliberRehearsal.draft_id == draft.id)).all():
        item.status = "stale"
    db.flush()


def _serialize_draft(db: Session, draft: CaliberDraft) -> dict:
    caliber = current_caliber(db)
    targets = _draft_targets(caliber, draft.changes or {})
    codes = changed_codes(caliber, draft.changes or {})
    rehearsal = db.scalar(
        select(CaliberRehearsal)
        .where(CaliberRehearsal.draft_id == draft.id, CaliberRehearsal.status == "ready")
        .order_by(CaliberRehearsal.id.desc())
        .limit(1)
    )
    items = []
    for code in sorted(caliber):
        base = caliber[code]
        target = targets[code]
        items.append(
            {
                "code": code,
                "label": base["label"],
                "module": base["module"],
                "is_key": target["is_key"],
                "enabled": target["enabled"],
                "base_is_key": base["is_key"],
                "base_enabled": base["enabled"],
                "changed": code in codes,
            }
        )
    return {
        "id": draft.id,
        "status": draft.status,
        "base_version_id": draft.base_version_id,
        "change_note": draft.change_note,
        "changed_codes": codes,
        "changed_count": len(codes),
        "items": items,
        "rehearsal_id": rehearsal.id if rehearsal else None,
        "created_by": draft.created_by,
        "created_at": iso_utc(draft.created_at),
        "updated_at": iso_utc(draft.updated_at),
    }


def draft_detail(db: Session, draft: CaliberDraft) -> dict:
    return _serialize_draft(db, draft)


def draft_state(db: Session) -> dict:
    """总览/事件字典用：当前是否有待发布草稿及其差异摘要。"""
    draft = active_draft(db)
    if draft is None:
        return {"has_draft": False}
    data = _serialize_draft(db, draft)
    return {
        "has_draft": True,
        "draft_id": draft.id,
        "changed_count": data["changed_count"],
        "changed_codes": data["changed_codes"],
        "rehearsal_id": data["rehearsal_id"],
        "change_note": draft.change_note,
        "updated_at": iso_utc(draft.updated_at),
    }


# --------------------------------------------------------------------------- #
# 预演（内存模拟，不碰正式库）
# --------------------------------------------------------------------------- #
def _eligible_codes(targets: dict[str, dict]) -> set[str]:
    """新口径下保留的事件：启用且关键。停用或非关键动作一律排除。"""
    return {code for code, item in targets.items() if item["enabled"] and item["is_key"]}


def _filter_sequences(sequences: list[list[str]], eligible: set[str]) -> tuple[list[list[str]], int]:
    filtered: list[list[str]] = []
    affected_sessions = 0
    for seq in sequences:
        kept = [code for code in seq if code in eligible]
        if kept != seq:
            affected_sessions += 1
        if kept:
            filtered.append(kept)
    return filtered, affected_sessions


def simulate(db: Session, targets: dict[str, dict]) -> dict:
    """按目标口径在内存里重跑挖掘 + 推荐，返回影响面（不写库）。"""
    rows = db.scalars(select(EventSeq).order_by(EventSeq.started_at, EventSeq.id)).all()
    raw_sequences = [list(row.events or []) for row in rows]
    eligible = _eligible_codes(targets)
    filtered, affected_sessions = _filter_sequences(raw_sequences, eligible)

    mined = mine_patterns(filtered, DEFAULT_MIN_SUPPORT, DEFAULT_MAX_LEN, DEFAULT_TOP_K, min_len=PATTERN_MIN_LEN)
    module_of = {row.code: row.module for row in db.scalars(select(EventDef)).all()}

    # 预演推荐：用过滤后的会话重建用户后缀，再走与正式链路相同的纯函数
    suffixes = _suffixes_from_sequences(rows, eligible)
    refs = [
        recommender.PatternRef(
            pattern_id=index,
            items=tuple(item.items),
            confidence=item.confidence,
            lift=item.lift,
        )
        for index, item in enumerate(mined, start=1)
    ]
    result = recommender.recommend(suffixes, refs, module_of)

    # 正式基线（当前口径），用于差异对比
    base_pattern_count = db.scalar(select(func.count()).select_from(Pattern)) or 0
    base_rec_count = db.scalar(select(func.count()).select_from(Recommendation)) or 0

    excluded_codes = sorted(
        code for code, item in targets.items() if not (item["enabled"] and item["is_key"])
    )
    return {
        "eligible_codes": sorted(eligible),
        "excluded_codes": excluded_codes,
        "sequences_total": len(raw_sequences),
        "sequences_after": len(filtered),
        "affected_sessions": affected_sessions,
        "pattern_count_after": len(mined),
        "pattern_count_base": base_pattern_count,
        "rec_count_after": len(result.recommendations),
        "rec_count_base": base_rec_count,
        "covered_users_after": result.covered_users,
        "active_users": result.active_users,
        "coverage_pct_after": result.coverage_pct,
        "top_patterns": [
            {
                "seq_key": item.seq_key,
                "length": item.length,
                "support_count": item.support_count,
                "support_pct": round(item.support_count / len(filtered) * 100, 1) if filtered else 0.0,
                "confidence": round(item.confidence, 4),
                "lift": round(item.lift, 4),
            }
            for item in mined[:10]
        ],
        "recommendations_sample": [
            {
                "user_id": item.user_id,
                "next_event": item.next_event,
                "module": item.module,
                "score": item.score,
                "priority": item.priority,
            }
            for item in result.recommendations[:REHEARSAL_SAMPLE_LIMIT]
        ],
    }


def _suffixes_from_sequences(rows: list[EventSeq], eligible: set[str], k: int = 3) -> dict[str, list[str]]:
    """与 sequence_service.latest_suffixes 同口径，但事件先按新口径过滤。

    注意不能直接 zip(rows, filtered)：filtered 会丢掉过滤后为空的会话导致错位，
    这里对每条原始会话独立过滤，再按 started_at 倒序取每用户最近一条。
    """
    pairs: list[tuple[EventSeq, list[str]]] = []
    for row in rows:
        kept = [code for code in (row.events or []) if code in eligible]
        pairs.append((row, kept))
    pairs.sort(key=lambda pair: (pair[0].started_at, pair[0].id), reverse=True)
    out: dict[str, list[str]] = {}
    for row, seq in pairs:
        if row.user_id in out:
            continue
        if not seq:
            continue
        out[row.user_id] = seq[-k:]
    return out


def run_rehearsal(db: Session, draft: CaliberDraft, actor_email: str) -> CaliberRehearsal:
    caliber = current_caliber(db)
    changes = dict(draft.changes or {})
    codes = changed_codes(caliber, changes)
    if not codes:
        raise AppError("DRAFT_EMPTY", 422, {"message": "草稿没有相对正式口径的实质变更，无需预演"})
    targets = _draft_targets(caliber, changes)
    impact = simulate(db, targets)
    impact["changed_codes"] = codes
    rehearsal = CaliberRehearsal(
        draft_id=draft.id,
        status="ready",
        changes_snapshot=changes,
        impact=impact,
        created_by=actor_email,
    )
    db.add(rehearsal)
    db.flush()
    return rehearsal


def serialize_rehearsal(rehearsal: CaliberRehearsal, draft: CaliberDraft | None = None) -> dict:
    return {
        "id": rehearsal.id,
        "draft_id": rehearsal.draft_id,
        "status": rehearsal.status,
        "impact": rehearsal.impact or {},
        "created_by": rehearsal.created_by,
        "created_at": iso_utc(rehearsal.created_at),
        "draft_status": draft.status if draft else None,
    }


# --------------------------------------------------------------------------- #
# 发布（单事务，失败整体回滚）
# --------------------------------------------------------------------------- #
def _next_version_no(db: Session) -> str:
    prefix = f"C{local_now():%Y%m%d}"
    count = (
        db.scalar(select(func.count()).select_from(CaliberVersion).where(CaliberVersion.version_no.like(f"{prefix}%")))
        or 0
    )
    return f"{prefix}-{count + 1:03d}"


def publish(db: Session, draft: CaliberDraft, rehearsal: CaliberRehearsal, actor_email: str, note: str | None) -> CaliberVersion:
    """统一时点发布：校验 → 改 event_defs → 落版本，全程同一事务。

    调用方负责 commit；此处任何异常都会向外抛，由 session 回滚，正式口径保持旧版。
    """
    if draft.status != "active":
        raise AppError("DRAFT_NOT_ACTIVE", 409, {"draft_id": draft.id, "status": draft.status})
    if rehearsal.status != "ready" or rehearsal.draft_id != draft.id:
        raise AppError("REHEARSAL_NOT_READY", 409, {"rehearsal_id": rehearsal.id})
    # 预演输入必须与当前草稿一致，防止「预演 A、发布 B」
    if json.dumps(rehearsal.changes_snapshot or {}, sort_keys=True) != json.dumps(draft.changes or {}, sort_keys=True):
        raise AppError("REHEARSAL_STALE", 409, {"message": "草稿在预演后又被修改，请重新预演"})

    caliber = current_caliber(db)
    changes = dict(draft.changes or {})
    codes = changed_codes(caliber, changes)
    if not codes:
        raise AppError("DRAFT_EMPTY", 422, {"message": "草稿没有实质变更，无法发布"})

    # 1) 统一切换正式口径
    events = {row.code: row for row in db.scalars(select(EventDef)).all()}
    for code in codes:
        event = events.get(code)
        patch = changes.get(code, {})
        if event is None:
            raise AppError("NOT_FOUND", 404, {"entity": "event", "code": code})
        if patch.get("is_key") is not None:
            event.is_key = bool(patch["is_key"])
        if patch.get("enabled") is not None:
            event.enabled = bool(patch["enabled"])
    db.flush()

    # 2) 落不可变版本快照
    new_caliber = current_caliber(db)
    version = CaliberVersion(
        version_no=_next_version_no(db),
        status="published",
        change_note=note or draft.change_note,
        snapshot=new_caliber,
        event_count=len(new_caliber),
        key_count=sum(1 for item in new_caliber.values() if item["is_key"]),
        enabled_count=sum(1 for item in new_caliber.values() if item["enabled"]),
        changed_codes=codes,
        rehearsal_id=rehearsal.id,
        rehearsal_summary={
            "affected_sessions": (rehearsal.impact or {}).get("affected_sessions"),
            "pattern_count_after": (rehearsal.impact or {}).get("pattern_count_after"),
            "rec_count_after": (rehearsal.impact or {}).get("rec_count_after"),
            "coverage_pct_after": (rehearsal.impact or {}).get("coverage_pct_after"),
        },
        published_by=actor_email,
        published_at=utcnow(),
    )
    db.add(version)
    db.flush()

    # 3) 草稿与预演收口
    draft.status = "published"
    draft.published_at = utcnow()
    rehearsal.status = "consumed"
    db.flush()
    return version


def rollback(db: Session, version: CaliberVersion, actor_email: str, reason: str | None) -> CaliberVersion:
    """发布失败/人工回滚：把 event_defs 还原到该版本之前的口径，该版本标记 rolled_back。

    约束：
    - 只能回滚当前最新生效（head）的 published 版本，中间还压着新版本时拒绝；
    - 还原来源 = 它之前最近一条仍为 published 的版本快照（已 rolled_back 的不算）；
    - 首版没有更早基线，直接 409 拒绝。
    """
    if version.status != "published":
        raise AppError("VERSION_NOT_PUBLISHED", 409, {"version_id": version.id, "status": version.status})
    newer = db.scalar(
        select(CaliberVersion).where(CaliberVersion.id > version.id, CaliberVersion.status == "published").limit(1)
    )
    if newer is not None:
        raise AppError("VERSION_NOT_HEAD", 409, {"message": "只能回滚最新生效的口径版本", "head_version_id": newer.id})
    previous = db.scalar(
        select(CaliberVersion)
        .where(CaliberVersion.id < version.id, CaliberVersion.status == "published")
        .order_by(CaliberVersion.id.desc())
        .limit(1)
    )
    if previous is None or not previous.snapshot:
        raise AppError("ROLLBACK_NO_BASELINE", 409, {"message": "该版本是首个口径版本，没有可回滚的上一版"})
    events = {row.code: row for row in db.scalars(select(EventDef)).all()}
    for code, item in (previous.snapshot or {}).items():
        event = events.get(code)
        if event is None:
            continue
        event.is_key = bool(item["is_key"])
        event.enabled = bool(item["enabled"])
    version.status = "rolled_back"
    version.rolled_back_at = utcnow()
    version.rollback_reason = reason
    db.flush()
    return version


# --------------------------------------------------------------------------- #
# 差异与版本列表
# --------------------------------------------------------------------------- #
def serialize_version(db: Session, version: CaliberVersion) -> dict:
    caliber = current_caliber(db)
    diff = []
    for code in sorted(version.snapshot or {}):
        snap = version.snapshot[code]
        live = caliber.get(code)
        diff.append(
            {
                "code": code,
                "label": snap.get("label", code),
                "module": snap.get("module"),
                "version_is_key": snap["is_key"],
                "version_enabled": snap["enabled"],
                "live_is_key": live["is_key"] if live else None,
                "live_enabled": live["enabled"] if live else None,
                "drifted": bool(live and (live["is_key"] != snap["is_key"] or live["enabled"] != snap["enabled"])),
            }
        )
    return {
        "id": version.id,
        "version_no": version.version_no,
        "status": version.status,
        "change_note": version.change_note,
        "event_count": version.event_count,
        "key_count": version.key_count,
        "enabled_count": version.enabled_count,
        "changed_codes": version.changed_codes or [],
        "rehearsal_id": version.rehearsal_id,
        "rehearsal_summary": version.rehearsal_summary,
        "snapshot_diff": diff,
        "published_by": version.published_by,
        "published_at": iso_utc(version.published_at),
        "rolled_back_at": iso_utc(version.rolled_back_at) if version.rolled_back_at else None,
        "rollback_reason": version.rollback_reason,
    }


def list_versions(db: Session, limit: int = 20, offset: int = 0) -> dict:
    total = db.scalar(select(func.count()).select_from(CaliberVersion)) or 0
    rows = db.scalars(select(CaliberVersion).order_by(CaliberVersion.id.desc()).limit(limit).offset(offset)).all()
    return {
        "items": [
            {
                "id": row.id,
                "version_no": row.version_no,
                "status": row.status,
                "change_note": row.change_note,
                "changed_codes": row.changed_codes or [],
                "key_count": row.key_count,
                "enabled_count": row.enabled_count,
                "rehearsal_summary": row.rehearsal_summary,
                "published_by": row.published_by,
                "published_at": iso_utc(row.published_at),
                "rolled_back_at": iso_utc(row.rolled_back_at) if row.rolled_back_at else None,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def pending_vs_live_diff(db: Session) -> dict:
    """总览/事件字典/审计共用：待发布草稿相对正式版本的差异。"""
    draft = active_draft(db)
    if draft is None:
        return {"has_draft": False, "changes": []}
    caliber = current_caliber(db)
    targets = _draft_targets(caliber, draft.changes or {})
    codes = changed_codes(caliber, draft.changes or {})
    changes = []
    for code in codes:
        base, target = caliber[code], targets[code]
        changes.append(
            {
                "code": code,
                "label": base["label"],
                "module": base["module"],
                "base_is_key": base["is_key"],
                "base_enabled": base["enabled"],
                "target_is_key": target["is_key"],
                "target_enabled": target["enabled"],
                "excluded_after": not (target["enabled"] and target["is_key"]),
            }
        )
    rehearsal = db.scalar(
        select(CaliberRehearsal)
        .where(CaliberRehearsal.draft_id == draft.id, CaliberRehearsal.status == "ready")
        .order_by(CaliberRehearsal.id.desc())
        .limit(1)
    )
    return {
        "has_draft": True,
        "draft_id": draft.id,
        "status": draft.status,
        "change_note": draft.change_note,
        "changes": changes,
        "rehearsal_id": rehearsal.id if rehearsal else None,
        "rehearsal_ready": rehearsal is not None,
        "updated_at": iso_utc(draft.updated_at),
    }
