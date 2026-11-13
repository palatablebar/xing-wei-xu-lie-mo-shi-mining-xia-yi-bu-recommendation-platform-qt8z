import { api } from '../api.js';
import { can } from '../config.js';
import { errorBox, errorMessage, esc, fmtTime, table, toast } from '../ui.js';
import { loadCaliberState, openCaliberConsole } from '../caliber.js';

const CALIBER_ACTIONS = [
  { value: '', label: '全部动作' },
  { value: 'event.stage', label: '口径变更入草稿' },
  { value: 'caliber.rehearse', label: '预演' },
  { value: 'caliber.publish', label: '发布版本' },
  { value: 'caliber.rollback', label: '回滚版本' },
  { value: 'event.draft_discard', label: '作废草稿' },
];

const state = { action: '' };

export const auditPage = {
  async render(view, ctx) {
    let data;
    let caliber;
    try {
      [data, caliber] = await Promise.all([
        api.get('/api/audit', { limit: 100, action: state.action }),
        loadCaliberState().catch(() => null),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => auditPage.render(view, ctx));
      return;
    }
    const draft = caliber;
    view.innerHTML = `
      ${
        draft && draft.has_draft
          ? `<section class="caliber-banner" data-testid="audit-caliber-banner">
              <div class="caliber-head">
                <h2>审计提示：存在待发布口径草稿</h2>
                <span class="badge pending">${esc(draft.changes.length)} 项未生效</span>
                ${draft.rehearsal_ready ? '<span class="badge ok">已预演</span>' : '<span class="badge warn">未预演</span>'}
                <div class="caliber-actions">
                  ${can(ctx.user.role, 'event:write') ? '<button class="btn sm ghost" data-audit-caliber>打开口径发布台</button>' : ''}
                </div>
              </div>
              <div class="caliber-diff">
                ${(draft.changes || [])
                  .map(
                    (item) => `<div class="diff-row">
                      <span><b>${esc(item.label)}</b> <span class="muted mono">${esc(item.code)}</span></span>
                      <span class="muted">正式：${item.base_is_key ? '关键' : '普通'} / ${item.base_enabled ? '启用' : '停用'}</span>
                      <span class="arrow-mark">→</span>
                      <span class="${item.excluded_after ? 'excluded' : ''}">待发布：${item.target_is_key ? '关键' : '普通'} / ${item.target_enabled ? '启用' : '停用'}${item.excluded_after ? '（新名单排除）' : ''}</span>
                    </div>`,
                  )
                  .join('')}
              </div>
            </section>`
          : ''
      }
      <section class="panel">
        <div class="panel-head">
          <h2>审计日志</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${data.total} 条 · 最近 100 条</span>
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="audit-filters">
            <div class="field">
              <label for="audit-action">口径动作</label>
              <select name="action" id="audit-action">
                ${CALIBER_ACTIONS.map((opt) => `<option value="${esc(opt.value)}" ${opt.value === state.action ? 'selected' : ''}>${esc(opt.label)}</option>`).join('')}
              </select>
            </div>
            <div class="spacer"></div>
          </div>
        </div>
        ${table({
          rows: data.items,
          empty: { title: '还没有审计记录', hint: '登录、登记事件、挖掘、复核、口径发布都会留痕。' },
          columns: [
            { key: 'created_at', label: '时间', render: (row) => fmtTime(row.created_at) },
            { key: 'actor_email', label: '操作人', className: 'mono' },
            { key: 'actor_role', label: '角色' },
            { key: 'action_label', label: '动作' },
            { key: 'entity', label: '对象' },
            { key: 'layer', label: '层', render: (row) => `<span class="badge">${esc(row.layer)}</span>` },
            { key: 'detail', label: '详情', render: (row) => `<span class="mono muted">${esc(JSON.stringify(row.detail || {}))}</span>` },
          ],
        })}
      </section>`;
    view.querySelector('[data-audit-caliber]')?.addEventListener('click', () => {
      openCaliberConsole(view, ctx, () => auditPage.render(view, ctx));
    });
    view.querySelector('#audit-action')?.addEventListener('change', (event) => {
      state.action = event.target.value;
      auditPage.render(view, ctx);
    });
  },
};

export default auditPage;
