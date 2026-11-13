import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
import { drawer, errorBox, errorMessage, esc, field, fmtTime, kv, table, toast } from '../ui.js';

const state = { q: '', module: '', isKey: '' };

function openEvent(view, ctx, event) {
  const editable = can(ctx.user.role, 'event:write');
  const { root, close } = drawer({
    title: event.label,
    subtitle: `${event.code} · ${event.module_label} 模块`,
    body: `${kv([
      ['事件码', `<span class="mono">${esc(event.code)}</span>`],
      ['模块', esc(event.module_label)],
      ['关键事件', event.is_key ? '是（进入推荐候选池）' : '否'],
      ['采样权重', esc(event.weight)],
      ['出现次数', `${esc(event.sample_count)} 次`],
      ['口径说明', esc(event.description || '—')],
      ['登记时间', fmtTime(event.created_at)],
    ])}`,
    footer: editable
      ? `<form id="event-form" style="display:grid;gap:10px">
          ${field({ label: '采样权重（1-10）', name: 'weight', type: 'number', value: event.weight })}
          ${field({ label: '是否关键事件', name: 'is_key', value: String(event.is_key), options: [{ value: 'true', label: '关键事件' }, { value: 'false', label: '普通事件' }] })}
          ${field({ label: '状态', name: 'enabled', value: String(event.enabled), options: [{ value: 'true', label: '启用' }, { value: 'false', label: '停用' }] })}
          <button class="btn accent" type="submit">保存口径</button>
        </form>`
      : '<span class="mono muted">只读角色可查看事件口径，不能修改</span>',
  });
  root.querySelector('#event-form')?.addEventListener('submit', async (submitEvent) => {
    submitEvent.preventDefault();
    const form = submitEvent.target;
    try {
      await api.patch(`/api/events/${event.id}`, {
        weight: Number(form.weight.value),
        is_key: form.is_key.value === 'true',
        enabled: form.enabled.value === 'true',
      });
      toast('事件口径已更新');
      close();
      await eventsPage.render(view, ctx);
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  });
}

function openCreate(view, ctx) {
  const { root, close } = drawer({
    title: '登记埋点事件',
    subtitle: '事件码是序列挖掘的原子单位，登记后不可改名',
    body: `<form id="new-event-form" style="display:grid;gap:12px">
      ${field({ label: '事件码（小写，如 board.share）', name: 'code', placeholder: 'board.share' })}
      ${field({ label: '展示名称', name: 'label', placeholder: '分享看板' })}
      ${field({
        label: '所属模块',
        name: 'module',
        value: 'board',
        options: Object.entries(ENUMS.module).map(([value, label]) => ({ value, label })),
      })}
      ${field({ label: '采样权重（1-10）', name: 'weight', type: 'number', value: 3 })}
      ${field({ label: '是否关键事件', name: 'is_key', value: 'false', options: [{ value: 'true', label: '关键事件' }, { value: 'false', label: '普通事件' }] })}
      ${field({ label: '口径说明', name: 'description' })}
      <div class="form-error" id="event-error"></div>
      <button class="btn accent" type="submit">保存事件</button>
    </form>`,
  });
  root.querySelector('#new-event-form').addEventListener('submit', async (submitEvent) => {
    submitEvent.preventDefault();
    const form = submitEvent.target;
    try {
      await api.post('/api/events', {
        code: form.code.value.trim(),
        label: form.label.value.trim(),
        module: form.module.value,
        weight: Number(form.weight.value),
        is_key: form.is_key.value === 'true',
        description: form.description.value.trim() || null,
      });
      toast('事件已登记');
      close();
      await eventsPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#event-error').textContent = err.code === 'CONFLICT' ? '事件码已存在' : errorMessage(err);
    }
  });
}

export const eventsPage = {
  async render(view, ctx) {
    let data;
    try {
      data = await api.get('/api/events', { q: state.q, module: state.module, is_key: state.isKey, limit: 50 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => eventsPage.render(view, ctx));
      return;
    }
    view.innerHTML = `
      <section class="panel">
        <div class="panel-head">
          <h2>事件字典</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${data.total} 个事件</span>
            ${can(ctx.user.role, 'event:write') ? '<button class="btn sm accent" id="new-event">登记事件</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          <div class="filter-bar" id="event-filters">
            ${field({ label: '搜索', name: 'q', value: state.q, placeholder: '事件码 / 名称' })}
            ${field({ label: '模块', name: 'module', value: state.module, options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.module).map(([value, label]) => ({ value, label }))] })}
            ${field({ label: '关键事件', name: 'is_key', value: state.isKey, options: [{ value: '', label: '全部' }, { value: 'true', label: '仅关键' }, { value: 'false', label: '仅普通' }] })}
            <div class="spacer"></div>
          </div>
        </div>
        ${table({
          rows: data.items,
          empty: { title: '没有匹配事件', hint: '管理员可以登记新的埋点事件。' },
          columns: [
            { key: 'code', label: '事件码', className: 'mono' },
            { key: 'label', label: '名称', render: (row) => `<b>${esc(row.label)}</b>` },
            { key: 'module_label', label: '模块' },
            { key: 'is_key', label: '关键', render: (row) => (row.is_key ? '<span class="badge high">关键</span>' : '<span class="badge">普通</span>') },
            { key: 'weight', label: '权重', className: 'num' },
            { key: 'sample_count', label: '出现次数', className: 'num', render: (row) => esc(row.sample_count) },
            { key: 'enabled', label: '状态', render: (row) => (row.enabled ? '<span class="badge ok">启用</span>' : '<span class="badge">停用</span>') },
          ],
        })}
      </section>`;
    const filters = view.querySelector('#event-filters');
    filters?.addEventListener('change', () => {
      state.q = filters.querySelector('[name=q]').value.trim();
      state.module = filters.querySelector('[name=module]').value;
      state.isKey = filters.querySelector('[name=is_key]').value;
      eventsPage.render(view, ctx);
    });
    filters?.querySelector('[name=q]')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        state.q = event.target.value.trim();
        eventsPage.render(view, ctx);
      }
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const item = data.items.find((entry) => String(entry.id) === row.dataset.id);
        if (item) openEvent(view, ctx, item);
      });
    });
    view.querySelector('#new-event')?.addEventListener('click', () => openCreate(view, ctx));
  },
};

export default eventsPage;
