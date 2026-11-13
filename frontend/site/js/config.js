/**
 * 品牌、通道导航、角色权限与枚举文案（前端唯一定义处）。
 * 后端对应：backend/src/constants/{roles,enums}.py；README 列出全部出现位置。
 */
export const BRAND = {
  short: 'nextbest',
  title: '行为序列模式挖掘与下一步推荐台',
  org: '织云 SaaS · 增长团队',
  edition: 'SEQ CONSOLE · 12 CH',
  subtitle: '12 个埋点事件 → PrefixSpan 模式库 → 下一步推荐 → 运营复核名单',
  loginLead:
    '先看信号有没有形状，再决定推什么。每一次推荐都能追到一条模式、一条会话、一个支持度。',
  loginPoints: [
    ['01', '600 条会话按事件时序入库，均值 8 个事件，转化会话单独可筛。'],
    ['02', 'PrefixSpan 最小支持度 3%（18 条会话），最长 5 步，取支持度前 50 条入模式库。'],
    ['03', '推荐按「置信度 × 提升度」排序，同模块最多 2 条，每用户最多 6 条。'],
  ],
};

export const NAV = [
  { to: '#/overview', no: '01', label: '总览', permission: 'overview:read' },
  { to: '#/events', no: '02', label: '事件字典', permission: 'event:read' },
  { to: '#/sequences', no: '03', label: '序列浏览', permission: 'sequence:read' },
  { to: '#/mining', no: '04', label: '模式挖掘', permission: 'mining:read' },
  { to: '#/recommendations', no: '05', label: '推荐名单', permission: 'recommendation:read' },
  { to: '#/audit', no: '06', label: '审计', permission: 'audit:read' },
];

export const ROLE_LABELS = {
  admin: '增长平台管理员',
  analyst: '行为分析专员',
  viewer: '运营只读',
};

export const PERMISSIONS = {
  admin: [
    'overview:read', 'event:read', 'event:write', 'sequence:read', 'mining:read', 'mining:create',
    'pattern:read', 'recommendation:read', 'recommendation:review', 'export:read', 'audit:read',
  ],
  analyst: [
    'overview:read', 'event:read', 'sequence:read', 'mining:read', 'mining:create',
    'pattern:read', 'recommendation:read', 'recommendation:review', 'export:read',
  ],
  viewer: ['overview:read', 'event:read', 'sequence:read', 'mining:read', 'pattern:read', 'recommendation:read'],
};

export const ENUMS = {
  module: {
    account: '账户',
    integration: '集成',
    board: '看板',
    report: '报表',
    alert: '告警',
    billing: '计费',
  },
  mineStatus: {
    queued: '排队中',
    running: '挖掘中',
    success: '成功',
    partial: '部分成功',
    failed: '失败',
  },
  trigger: {
    manual: '手动',
    schedule: '定时',
    seed: '初始化',
  },
  reviewStatus: {
    pending: '待复核',
    confirmed: '已采纳',
    dismissed: '已驳回',
  },
  priority: {
    high: '高',
    medium: '中',
    low: '低',
  },
};

export function can(role, permission) {
  return (PERMISSIONS[role] || []).includes(permission);
}

export function badgeTone(priority) {
  return { high: 'high', medium: 'warn', low: 'info' }[priority] || 'info';
}

export function reviewTone(status) {
  return { pending: 'pending', confirmed: 'ok', dismissed: 'danger' }[status] || 'info';
}

export function statusTone(status) {
  return { success: 'ok', partial: 'warn', failed: 'danger', running: 'info', queued: 'info' }[status] || 'info';
}
