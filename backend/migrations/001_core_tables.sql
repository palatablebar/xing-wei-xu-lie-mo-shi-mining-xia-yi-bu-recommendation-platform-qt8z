-- 核心表结构参考（MySQL 8.0 语法，运行时不执行；建表由 SQLAlchemy create_all 完成）

CREATE TABLE users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    email           VARCHAR(160) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(80)  NOT NULL,
    role            VARCHAR(20)  NOT NULL,
    org             VARCHAR(120),
    created_at      DATETIME     NOT NULL
);

-- 12 个埋点事件口径
CREATE TABLE event_defs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    code            VARCHAR(40)  NOT NULL UNIQUE,   -- 如 board.view
    module          VARCHAR(20)  NOT NULL,          -- account/integration/board/report/alert/billing
    label           VARCHAR(80)  NOT NULL,
    is_key          TINYINT(1)   NOT NULL DEFAULT 0,
    weight          INT          NOT NULL DEFAULT 1,
    sample_count    INT          NOT NULL DEFAULT 0,
    description     TEXT,
    enabled         TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL,
    updated_at      DATETIME     NOT NULL
);

-- 600 条会话：events 为事件码有序数组（JSON）
CREATE TABLE event_seqs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(40)  NOT NULL UNIQUE,
    user_id         VARCHAR(24)  NOT NULL,
    events          JSON,
    event_count     INT          NOT NULL DEFAULT 0,
    modules_path    VARCHAR(160),
    started_at      DATETIME     NOT NULL,
    converted       TINYINT(1)   NOT NULL DEFAULT 0,
    created_at      DATETIME     NOT NULL,
    INDEX ix_event_seqs_user (user_id),
    INDEX ix_event_seqs_started (started_at)
);

-- 一次 PrefixSpan 挖掘
CREATE TABLE mine_runs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    run_no          VARCHAR(40)  NOT NULL UNIQUE,
    min_support_pct DOUBLE       NOT NULL DEFAULT 3,
    max_len         INT          NOT NULL DEFAULT 5,
    top_k           INT          NOT NULL DEFAULT 50,
    trigger         VARCHAR(20)  NOT NULL,
    status          VARCHAR(20)  NOT NULL,
    operator_email  VARCHAR(160) NOT NULL,
    sequence_count  INT          NOT NULL DEFAULT 0,
    pattern_count   INT          NOT NULL DEFAULT 0,
    rec_count       INT          NOT NULL DEFAULT 0,
    covered_users   INT          NOT NULL DEFAULT 0,
    active_users    INT          NOT NULL DEFAULT 0,
    coverage_pct    DOUBLE       NOT NULL DEFAULT 0,
    metrics         JSON,
    log_text        TEXT,
    seed_key        VARCHAR(120) UNIQUE,
    started_at      DATETIME     NOT NULL,
    finished_at     DATETIME
);

-- 频繁序列模式（支持度 / 置信度 / 提升度由后端算出）
CREATE TABLE patterns (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    run_id          INT          NOT NULL,
    seq_key         VARCHAR(255) NOT NULL,
    items           JSON,
    length          INT          NOT NULL DEFAULT 2,
    support_count   INT          NOT NULL DEFAULT 0,
    support_pct     DOUBLE       NOT NULL DEFAULT 0,
    confidence      DOUBLE       NOT NULL DEFAULT 0,
    lift            DOUBLE       NOT NULL DEFAULT 1,
    rank            INT          NOT NULL DEFAULT 0,
    created_at      DATETIME     NOT NULL,
    CONSTRAINT uq_patterns_run_key UNIQUE (run_id, seq_key),
    CONSTRAINT fk_patterns_run FOREIGN KEY (run_id) REFERENCES mine_runs(id) ON DELETE CASCADE
);

-- 下一步推荐（每用户最多 6 条、同模块最多 2 条，由推荐算法保证）
CREATE TABLE recommendations (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    run_id          INT          NOT NULL,
    pattern_id      INT          NOT NULL,
    user_id         VARCHAR(24)  NOT NULL,
    suffix          JSON,
    next_event      VARCHAR(40)  NOT NULL,
    next_module     VARCHAR(20)  NOT NULL,
    confidence      DOUBLE       NOT NULL DEFAULT 0,
    lift            DOUBLE       NOT NULL DEFAULT 1,
    score           DOUBLE       NOT NULL DEFAULT 0,
    priority        VARCHAR(12)  NOT NULL DEFAULT 'medium',
    status          VARCHAR(16)  NOT NULL DEFAULT 'pending',
    reviewer        VARCHAR(160),
    review_note     VARCHAR(1000),
    created_at      DATETIME     NOT NULL,
    updated_at      DATETIME     NOT NULL,
    CONSTRAINT uq_rec_run_user_pattern_next UNIQUE (run_id, user_id, pattern_id, next_event),
    CONSTRAINT fk_rec_run FOREIGN KEY (run_id) REFERENCES mine_runs(id) ON DELETE CASCADE,
    CONSTRAINT fk_rec_pattern FOREIGN KEY (pattern_id) REFERENCES patterns(id) ON DELETE CASCADE
);

CREATE TABLE audit_logs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    actor_email     VARCHAR(160) NOT NULL,
    actor_role      VARCHAR(20)  NOT NULL,
    action          VARCHAR(64)  NOT NULL,
    entity          VARCHAR(40)  NOT NULL,
    entity_id       VARCHAR(64),
    detail          JSON,
    layer           VARCHAR(16)  NOT NULL DEFAULT 'domain',
    ip              VARCHAR(64),
    seed_key        VARCHAR(120) UNIQUE,
    created_at      DATETIME     NOT NULL
);
