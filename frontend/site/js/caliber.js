/**
 * 口径版本化前端封装：草稿 → 预演 → 发布 / 回滚。
 * 与后端 /api/caliber 对应；只有 admin 有写按钮（PERMISSIONS 里的 event:write）。
 */
import { api } from './api.js';
import { ENUMS, can } from './config.js';
import { drawer, errorMessage, esc, field, fmtPct, fmtTime, kv, table, toast } from './ui.js';

export const caliberState = {
  state: null, // /api/caliber/state
};

export async function loadCaliberState() {
  caliberState.state = await api.get('/api/caliber/state');
  return caliberState.state;
}

function boolText(value) {
  return value ? '关键 / 启用' : '非关键或停用';
}

function keyBadge(isKey, enabled) {
  if (!enabled) return '<span class="badge danger">停用</span>';
  return isKey ? '<span class="badge ok">关键</span>' : '<span class="badge warn">非关键</span>';
}

/** 顶部待发布横幅：总览 / 事件字典复用，展示待发布与正式版本差异。 */
export function pendingBanner(state, role, onRefresh) {
  if (!state || !state.has_draft) return '';
  const writable = can(role, 'event:write');
  const rows = (state.changes || [])
    .map(
      (item) => `<div class="diff-row">
        <span><b>${esc(item.label)}</b> <span class="muted mono">${esc(item.code)}</span></span>
        <span>${keyBadge(item.base_is_key, item.base_enabled)}</span>
        <span class="arrow-mark">→</span>
        <span class="${item.excluded_after ? 'excluded' : ''}">${keyBadge(item.target_is_key, item.target_enabled)}${
          item.excluded_after ? ' <small>（新名单排除）</small>' : ''
        }</span>
      </div>`,
    )
    .join('');
  return `<section class="caliber-banner" data-testid="caliber-banner">
    <div class="caliber-head">
      <h2>待发布口径草稿</h2>
      <span class="badge pending">${esc(state.changes.length)} 个事件标记待生效</span>
      <span class="caliber-note">更新于 ${fmtTime(state.updated_at)}${state.rehearsal_ready ? ' · 已预演' : ' · 未预演'}</span>
      <div class="caliber-actions">
        ${writable ? '<button class="btn sm ghost" data-caliber-open>查看草稿 / 预演 / 发布</button>' : ''}
      </div>
    </div>
    <div class="caliber-diff">${rows}</div>
  </section>`;
}

export function bindBanner(view, ctx, onRefresh) {
  view.querySelector('[data-caliber-open]')?.addEventListener('click', () => {
    openCaliberConsole(view, ctx, onRefresh);
  });
}

function rehearsalMetrics(impact) {
  const metrics = [
    ['受影响会话', `${esc(impact.affected_sessions)} / ${esc(impact.sequences_total)}`],
    ['入模会话（新）', esc(impact.sequences_after)],
    ['模式数', `${esc(impact.pattern_count_after)} <small class="muted">（现 ${esc(impact.pattern_count_base)}）</small>`],
    ['推荐条数', `${esc(impact.rec_count_after)} <small class="muted">（现 ${esc(impact.rec_count_base)}）</small>`],
    ['覆盖率', fmtPct(impact.coverage_pct_after)],
    ['覆盖用户', `${esc(impact.covered_users_after)} / ${esc(impact.active_users)}`],
  ];
  return `<div class="caliber-metrics">${metrics
    .map(([k, v]) => `<div class="metric"><span class="k">${k}</span><span class="v">${v}</span></div>`)
    .join('')}</div>`;
}

function rehearsalBody(rehearsal) {
  const impact = rehearsal.impact || {};
  const excluded = (impact.excluded_codes || []).map((code) => `<span class="chip billing">${esc(code)}</span>`).join(' ') || '—';
  const top = (impact.top_patterns || [])
    .slice(0, 5)
    .map(
      (p) => `<div class="diff-row">
        <span class="mono">${esc(p.seq_key)}</span>
        <span class="muted">支持 ${esc(p.support_count)} · ${fmtPct(p.support_pct)}</span>
        <span class="arrow-mark">${esc(p.confidence.toFixed(2))}×</span>
      </div>`,
    )
    .join('');
  const sample = table({
    rows: impact.recommendations_sample || [],
    empty: { title: '新口径下没有推荐', hint: '关键动作被收紧后，可能没有可匹配模式。' },
    columns: [
      { key: 'user_id', label: '用户', className: 'mono' },
      { key: 'next_event', label: '推荐下一步', className: 'mono' },
      { key: 'module', label: '模块', render: (r) => esc(ENUMS.module[r.module] || r.module) },
      { key: 'score', label: '分数', className: 'num', render: (r) => Number(r.score).toFixed(3) },
      {
        key: 'priority',
        label: '优先级',
        render: (r) => `<span class="badge ${r.priority === 'high' ? 'high' : r.priority === 'medium' ? 'warn' : 'info'}">${esc(ENUMS.priority[r.priority] || r.priority)}</span>`,
      },
    ],
  });
  return `
    <h3 style="font-size:0.95rem;margin:8px 0 6px">预演影响面（不写正式库）</h3>
    ${rehearsalMetrics(impact)}
    <h3 style="font-size:0.95rem;margin:12px 0 6px">新名单排除的动作（停用或非关键）</h3>
    <div class="track">${excluded}</div>
    <h3 style="font-size:0.95rem;margin:12px 0 6px">新模式 TOP 5</h3>
    <div class="caliber-diff">${top || '<span class="muted">无频繁模式</span>'}</div>
    <h3 style="font-size:0.95rem;margin:12px 0 6px">新推荐名单样例（前 50 条）</h3>
    ${sample}`;
}

async function openRehearsalDrawer(view, ctx, draftId, onRefresh) {
  const instance = drawer({
    title: '口径变更预演',
    subtitle: `草稿 #${draftId} · 内存模拟，正式复核与导出不受影响`,
    body: '<div class="empty"><div class="mark">预演计算中…</div></div>',
  });
  try {
    const rehearsal = await api.post(`/api/caliber/draft/${draftId}/rehearse`, {});
    instance.root.querySelector('.drawer-body').innerHTML = rehearsalBody(rehearsal);
    instance.root.querySelector('.drawer-foot')?.remove();
    const foot = document.createElement('div');
    foot.className = 'drawer-foot';
    foot.innerHTML = `
      <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;flex-wrap:wrap">
        <span class="caliber-note">确认影响面后再发布；发布从统一时点生效</span>
        <button class="btn ghost sm" data-close>再看看</button>
        <button class="btn accent sm" data-publish>确认并发布</button>
      </div>`;
    instance.root.querySelector('.drawer').appendChild(foot);
    foot.querySelector('[data-publish]').addEventListener('click', () => openPublishDrawer(view, ctx, draftId, rehearsal.id, onRefresh));
    foot.querySelector('[data-close]').addEventListener('click', instance.close);
    onRefresh?.();
  } catch (err) {
    instance.root.querySelector('.drawer-body').innerHTML = `<div class="error-box"><span>${esc(errorMessage(err))}</span></div>`;
  }
}

function openPublishDrawer(view, ctx, draftId, rehearsalId, onRefresh) {
  const instance = drawer({
    title: '发布口径版本',
    subtitle: `草稿 #${draftId} · 预演 #${rehearsalId}`,
    body: `<div class="caliber-note" style="margin-bottom:10px">
        发布在单事务内统一切换事件字典并生成不可变版本；任一步失败整体回滚，不会半新半旧。
        发布后需重新发起挖掘，新模式与推荐才按新口径生成；此前的复核与导出仍按旧口径名单。
      </div>
      <form id="publish-form" style="display:grid;gap:10px">
        ${field({ label: '变更说明（可选）', name: 'change_note', placeholder: '例：收紧关键动作，只保留转化链路上的事件' })}
        <div class="form-error" id="publish-error"></div>
      </form>`,
    footer: `<div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn ghost sm" data-close>取消</button>
      <button class="btn accent sm" type="submit" form="publish-form">确认统一发布</button>
    </div>`,
  });
  instance.root.querySelector('#publish-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const note = instance.root.querySelector('[name=change_note]').value.trim() || null;
    try {
      const version = await api.post(`/api/caliber/draft/${draftId}/publish/${rehearsalId}`, { change_note: note });
      toast(`口径版本 ${version.version_no} 已发布`);
      instance.close();
      await onRefresh?.();
    } catch (err) {
      instance.root.querySelector('#publish-error').textContent = errorMessage(err);
    }
  });
}

function openRollbackDrawer(view, ctx, version, onRefresh) {
  const instance = drawer({
    title: `回滚口径版本 ${version.version_no}`,
    subtitle: '还原到该版本之前的正式口径',
    body: `<div class="caliber-note" style="margin-bottom:10px">
        回滚同样在单事务内完成：事件字典还原到上一版本，当前版本标记为 rolled_back。
      </div>
      <form id="rollback-form" style="display:grid;gap:10px">
        ${field({ label: '回滚原因（可选）', name: 'reason', placeholder: '例：发布后覆盖率显著下降' })}
        <div class="form-error" id="rollback-error"></div>
      </form>`,
    footer: `<div style="display:flex;gap:8px;justify-content:flex-end">
      <button class="btn ghost sm" data-close>取消</button>
      <button class="btn accent sm" type="submit" form="rollback-form">确认回滚</button>
    </div>`,
  });
  instance.root.querySelector('#rollback-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const reason = instance.root.querySelector('[name=reason]').value.trim() || null;
    try {
      await api.post(`/api/caliber/versions/${version.id}/rollback`, { reason });
      toast('已回滚到上一版口径');
      instance.close();
      await onRefresh?.();
    } catch (err) {
      instance.root.querySelector('#rollback-error').textContent = errorMessage(err);
    }
  });
}

function openVersionDrawer(view, ctx, version, onRefresh) {
  const writable = can(ctx.user.role, 'event:write');
  const instance = drawer({
    title: `口径版本 ${version.version_no}`,
    subtitle: `${version.status === 'published' ? '正式生效' : '已回滚'} · ${fmtTime(version.published_at)}`,
    body: `<div id="version-detail"><div class="empty"><div class="mark">加载版本…</div></div></div>`,
    footer: writable && version.status === 'published'
      ? `<div style="display:flex;justify-content:flex-end"><button class="btn accent sm" data-rollback>回滚此版本</button></div>`
      : '<span class="mono muted">该版本不可回滚（已回滚或无权限）</span>',
  });
  api
    .get(`/api/caliber/versions/${version.id}`)
    .then((detail) => {
      const diff = table({
        rows: detail.snapshot_diff,
        empty: { title: '版本无快照', hint: '' },
        columns: [
          { key: 'code', label: '事件', className: 'mono', render: (r) => `${esc(r.label)}<div class="muted">${esc(r.code)}</div>` },
          { key: 'version_is_key', label: '版本口径', render: (r) => keyBadge(r.version_is_key, r.version_enabled) },
          { key: 'live_is_key', label: '当前正式', render: (r) => (r.live_is_key === null ? '—' : keyBadge(r.live_is_key, r.live_enabled)) },
          { key: 'drifted', label: '差异', render: (r) => (r.drifted ? '<span class="badge warn">已偏离</span>' : '<span class="badge ok">一致</span>') },
        ],
      });
      instance.root.querySelector('#version-detail').innerHTML = `
        ${kv([
          ['变更说明', esc(detail.change_note || '—')],
          ['事件 / 关键 / 启用', `${esc(detail.event_count)} / ${esc(detail.key_count)} / ${esc(detail.enabled_count)}`],
          ['变更事件', (detail.changed_codes || []).map((c) => `<span class="chip">${esc(c)}</span>`).join(' ') || '—'],
          ['发布人', esc(detail.published_by)],
          ['发布时间', fmtTime(detail.published_at)],
          ['预演摘要', `<span class="mono">${esc(JSON.stringify(detail.rehearsal_summary || {}))}</span>`],
        ])}
        <h3 style="font-size:0.95rem;margin:12px 0 6px">版本快照 vs 当前正式口径</h3>
        ${diff}`;
      instance.root.querySelector('[data-rollback]')?.addEventListener('click', () => {
        instance.close();
        openRollbackDrawer(view, ctx, detail, onRefresh);
      });
    })
    .catch((err) => {
      instance.root.querySelector('#version-detail').innerHTML = `<div class="error-box"><span>${esc(errorMessage(err))}</span></div>`;
    });
}

/** 口径工作台抽屉：草稿明细 + 预演 + 发布 + 历史版本。 */
export function openCaliberConsole(view, ctx, onRefresh) {
  const writable = can(ctx.user.role, 'event:write');
  const instance = drawer({
    title: '事件口径发布台',
    subtitle: '草稿 → 预演 → 统一发布（失败自动回滚）',
    body: '<div class="empty"><div class="mark">加载草稿…</div></div>',
    footer: writable
      ? `<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">
          <button class="btn ghost sm" data-discard>作废草稿</button>
          <button class="btn ghost sm" data-rehearse>预演影响面</button>
          <button class="btn accent sm" data-publish disabled>先预演才能发布</button>
        </div>`
      : '<span class="mono muted">只读角色可查看口径差异与版本，不能发布</span>',
  });

  async function reload() {
    const [draft, versions] = await Promise.all([
      api.get('/api/caliber/draft'),
      api.get('/api/caliber/versions', { limit: 20 }),
    ]);
    const changed = (draft.items || []).filter((item) => item.changed);
    const diff = table({
      rows: changed,
      empty: { title: '草稿没有实质变更', hint: '在事件字典里修改关键/停用标记会自动进入草稿。' },
      columns: [
        { key: 'code', label: '事件', className: 'mono', render: (r) => `${esc(r.label)}<div class="muted">${esc(r.code)}</div>` },
        { key: 'base', label: '正式口径', render: (r) => keyBadge(r.base_is_key, r.base_enabled) },
        { key: 'arrow', label: '', render: () => '<span class="arrow-mark">→</span>' },
        { key: 'target', label: '草稿口径', render: (r) => keyBadge(r.is_key, r.enabled) },
      ],
    });
    const versionRows = table({
      rows: versions.items,
      empty: { title: '还没有发布过口径版本', hint: '' },
      columns: [
        { key: 'version_no', label: '版本号', className: 'mono' },
        { key: 'status', label: '状态', render: (r) => (r.status === 'published' ? '<span class="badge ok">正式</span>' : '<span class="badge danger">已回滚</span>') },
        { key: 'changed_codes', label: '变更事件', render: (r) => esc((r.changed_codes || []).join(', ') || '基线') },
        { key: 'published_by', label: '发布人', className: 'mono' },
        { key: 'published_at', label: '时间', render: (r) => fmtTime(r.published_at) },
      ],
    });
    instance.root.querySelector('.drawer-body').innerHTML = `
      <h3 style="font-size:0.95rem;margin:4px 0 6px">待发布草稿 #${esc(draft.id)}（${esc(draft.changed_count)} 项变更）</h3>
      ${diff}
      ${draft.change_note ? `<div class="caliber-note" style="margin-top:6px">说明：${esc(draft.change_note)}</div>` : ''}
      <h3 style="font-size:0.95rem;margin:14px 0 6px">历史版本（待发布 vs 正式差异可点开）</h3>
      ${versionRows}`;
    // 版本行点击看详情
    instance.root.querySelectorAll('.drawer-body table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = versions.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) openVersionDrawer(view, ctx, item, onRefresh);
      });
    });
    // 发布按钮：必须有 ready 预演
    const publishBtn = instance.root.querySelector('[data-publish]');
    if (publishBtn) {
      if (draft.rehearsal_id && changed.length) {
        publishBtn.disabled = false;
        publishBtn.textContent = '确认并发布';
      } else {
        publishBtn.disabled = true;
        publishBtn.textContent = changed.length ? '先预演才能发布' : '草稿无变更';
      }
    }
    return draft;
  }

  reload()
    .then((draft) => {
      instance.root.querySelector('[data-rehearse]')?.addEventListener('click', async () => {
        instance.close();
        await openRehearsalDrawer(view, ctx, draft.id, onRefresh);
      });
      instance.root.querySelector('[data-publish]')?.addEventListener('click', () => {
        if (!draft.rehearsal_id) return;
        openPublishDrawer(view, ctx, draft.id, draft.rehearsal_id, onRefresh);
      });
      instance.root.querySelector('[data-discard]')?.addEventListener('click', async () => {
        if (!window.confirm('作废该草稿？正式口径不会受影响。')) return;
        try {
          await api.post(`/api/caliber/draft/${draft.id}/discard`, {});
          toast('草稿已作废');
          instance.close();
          await onRefresh?.();
        } catch (err) {
          toast(errorMessage(err), 'err');
        }
      });
    })
    .catch((err) => {
      instance.root.querySelector('.drawer-body').innerHTML = `<div class="error-box"><span>${esc(errorMessage(err))}</span></div>`;
    });
}
