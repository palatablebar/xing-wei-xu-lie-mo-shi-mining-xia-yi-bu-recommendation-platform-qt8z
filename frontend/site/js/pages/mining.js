import { api } from '../api.js';
import { ENUMS, can, statusTone } from '../config.js';
import { drawer, emptyState, errorBox, errorMessage, esc, field, fmtPct, fmtTime, kv, ladder, table, toast, track } from '../ui.js';

const state = { status: '', runId: '' };

function runLog(run) {
  return `<pre class="code">${esc(run.log_text || '（无日志）')}</pre>`;
}

function openRun(view, ctx, run) {
  drawer({
    title: `挖掘 ${run.run_no}`,
    subtitle: `${ENUMS.trigger[run.trigger] || run.trigger} · ${ENUMS.mineStatus[run.status] || run.status}`,
    body: `${kv([
      ['最小支持度', `${esc(run.min_support_pct)}%（${esc((run.metrics || {}).min_support_count || 0)} 条会话）`],
      ['最大长度', `${esc(run.max_len)} 步`],
      ['模式库上限', `${esc(run.top_k)} 条`],
      ['会话数', esc(run.sequence_count)],
      ['模式数', `${esc(run.pattern_count)} 条 · top 支持度 ${fmtPct((run.metrics || {}).top_support_pct || 0)}`],
      ['推荐数', `${esc(run.rec_count)} 条 · 覆盖 ${esc(run.covered_users)}/${esc(run.active_users)} 用户（${fmtPct(run.coverage_pct)}）`],
      ['操作人', esc(run.operator_email)],
      ['开始 / 结束', `${fmtTime(run.started_at)} → ${fmtTime(run.finished_at)}`],
    ])}
    <h3 style="font-size:0.95rem;margin:6px 0 2px">top1 模式</h3>
    <div class="mono hl">${esc((run.metrics || {}).top_pattern || '—')}</div>
    <h3 style="font-size:0.95rem;margin:6px 0 2px">运行日志</h3>
    ${runLog(run)}`,
    footer: `<button class="btn accent" data-goto>查看本次模式库</button>`,
  }).root.querySelector('[data-goto]')?.addEventListener('click', () => {
    state.runId = String(run.id);
    document.querySelectorAll('.drawer-backdrop').forEach((node) => node.remove());
    miningPage.render(view, ctx);
  });
}

function openRunForm(view, ctx) {
  const { root, close } = drawer({
    title: '发起序列挖掘',
    subtitle: 'PrefixSpan：最小支持度 / 最大长度 / 模式库上限',
    body: `<form id="run-form" style="display:grid;gap:12px">
      ${field({ label: '最小支持度（%）', name: 'min_support_pct', type: 'number', value: '3', attrs: 'step="0.5" min="0.5" max="50"' })}
      ${field({ label: '模式最大长度', name: 'max_len', type: 'number', value: '5', attrs: 'min="2" max="8"' })}
      ${field({ label: '模式库保留条数', name: 'top_k', type: 'number', value: '50', attrs: 'min="5" max="200"' })}
      <div class="form-error" id="run-error"></div>
      <button class="btn accent" type="submit">开始挖掘</button>
    </form>`,
  });
  root.querySelector('#run-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    button.textContent = '挖掘中…';
    try {
      const run = await api.post('/api/mine-runs', {
        min_support_pct: Number(form.min_support_pct.value),
        max_len: Number(form.max_len.value),
        top_k: Number(form.top_k.value),
        trigger: 'manual',
      });
      toast(`挖掘完成：${run.pattern_count} 条模式 / ${run.rec_count} 条推荐 / 覆盖 ${run.coverage_pct}%`);
      close();
      state.runId = String(run.id);
      await miningPage.render(view, ctx);
    } catch (err) {
      root.querySelector('#run-error').textContent = errorMessage(err);
      button.disabled = false;
      button.textContent = '开始挖掘';
    }
  });
}

function openPattern(pattern) {
  drawer({
    title: `模式 #${pattern.rank}`,
    subtitle: `${pattern.length} 步 · 支持度 ${fmtPct(pattern.support_pct)}`,
    body: `${kv([
      ['模式', `<span class="mono hl">${esc(pattern.seq_key)}</span>`],
      ['长度', `${esc(pattern.length)} 步`],
      ['支持会话', `${esc(pattern.support_count)} 条`],
      ['支持度', fmtPct(pattern.support_pct)],
      ['置信度', esc(pattern.confidence.toFixed(4))],
      ['提升度', esc(pattern.lift.toFixed(4))],
    ])}
    <h3 style="font-size:0.95rem;margin:6px 0 2px">事件轨道</h3>
    ${track(pattern.items_detail, 20)}`,
  });
}

export const miningPage = {
  async render(view, ctx) {
    let runs;
    let patterns;
    try {
      runs = await api.get('/api/mine-runs', { status: state.status, limit: 20 });
      if (!state.runId && runs.items.length) state.runId = String(runs.items[0].id);
      patterns = await api.get('/api/patterns', { run_id: state.runId, limit: 50 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => miningPage.render(view, ctx));
      return;
    }
    const active = runs.items.find((item) => String(item.id) === state.runId) || runs.items[0];
    view.innerHTML = `
      <div class="grid-2">
        <section class="panel">
          <div class="panel-head">
            <h2>挖掘运行</h2>
            <div style="display:flex;gap:8px;align-items:center">
              <span class="meta">${runs.total} 次</span>
              ${can(ctx.user.role, 'mining:create') ? '<button class="btn sm accent" id="new-run">发起挖掘</button>' : ''}
            </div>
          </div>
          ${table({
            rows: runs.items,
            empty: { title: '还没有挖掘记录', hint: '分析专员可以发起一次 PrefixSpan。' },
            columns: [
              { key: 'run_no', label: '运行号', className: 'mono' },
              { key: 'status', label: '状态', render: (row) => `<span class="badge ${statusTone(row.status)}">${esc(ENUMS.mineStatus[row.status] || row.status)}</span>` },
              { key: 'pattern_count', label: '模式', className: 'num' },
              { key: 'rec_count', label: '推荐', className: 'num' },
              { key: 'coverage_pct', label: '覆盖率', className: 'num', render: (row) => fmtPct(row.coverage_pct) },
              { key: 'started_at', label: '开始', render: (row) => fmtTime(row.started_at) },
            ],
          })}
        </section>
        <section class="panel">
          <div class="panel-head"><h2>参数与口径</h2><span class="meta">prefixspan</span></div>
          <div class="panel-body">
            ${
              active
                ? `<dl class="kv">
                    <dt>运行号</dt><dd class="mono">${esc(active.run_no)}</dd>
                    <dt>最小支持度</dt><dd>${esc(active.min_support_pct)}% · ${esc((active.metrics || {}).min_support_count || 0)} 条会话</dd>
                    <dt>最大长度</dt><dd>${esc(active.max_len)} 步</dd>
                    <dt>top1 支持度</dt><dd>${fmtPct((active.metrics || {}).top_support_pct || 0)}</dd>
                    <dt>平均序列长</dt><dd>${esc((active.metrics || {}).avg_sequence_len || 0)} 事件</dd>
                    <dt>覆盖率</dt><dd>${fmtPct(active.coverage_pct)}（${esc(active.covered_users)}/${esc(active.active_users)}）</dd>
                  </dl>
                  <div class="mono muted" style="margin-top:10px">${esc((active.metrics || {}).top_pattern || '')}</div>
                  ${can(ctx.user.role, 'export:read') ? '<button class="btn sm ghost" id="export-patterns" style="margin-top:10px">导出模式库 CSV</button>' : ''}`
                : emptyState({ title: '暂无参数', hint: '先发起一次挖掘。' })
            }
          </div>
        </section>
      </div>
      <section class="panel">
        <div class="panel-head">
          <h2>模式库</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">${patterns.total} 条 · 按支持度倒序</span>
            <select id="run-filter" class="mono" style="background:var(--void-2);border:1px solid var(--grid);padding:3px 6px">
              <option value="">全部运行</option>
              ${runs.items.map((run) => `<option value="${run.id}" ${String(run.id) === state.runId ? 'selected' : ''}>${esc(run.run_no)}</option>`).join('')}
            </select>
          </div>
        </div>
        <div class="panel-body">${ladder(patterns.items.slice(0, 12))}</div>
        ${table({
          rows: patterns.items,
          empty: { title: '模式库为空', hint: '降低最小支持度或先导入会话数据。' },
          columns: [
            { key: 'rank', label: '#', className: 'num' },
            { key: 'seq_key', label: '模式（事件码）', className: 'mono' },
            { key: 'length', label: '步数', className: 'num' },
            { key: 'support_count', label: '支持会话', className: 'num' },
            { key: 'support_pct', label: '支持度', className: 'num', render: (row) => fmtPct(row.support_pct) },
            { key: 'confidence', label: '置信度', className: 'num', render: (row) => row.confidence.toFixed(3) },
            { key: 'lift', label: '提升度', className: 'num', render: (row) => row.lift.toFixed(3) },
          ],
        })}
      </section>`;
    view.querySelectorAll('section.panel:first-of-type table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const run = runs.items.find((item) => String(item.id) === row.dataset.id);
        if (run) openRun(view, ctx, run);
      });
    });
    view.querySelectorAll('section.panel:last-of-type table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const pattern = patterns.items.find((item) => String(item.id) === row.dataset.id);
        if (pattern) openPattern(pattern);
      });
    });
    view.querySelector('#new-run')?.addEventListener('click', () => openRunForm(view, ctx));
    view.querySelector('#run-filter')?.addEventListener('change', (event) => {
      state.runId = event.target.value;
      miningPage.render(view, ctx);
    });
    view.querySelector('#export-patterns')?.addEventListener('click', async () => {
      try {
        await api.download(`/api/exports/patterns.csv${state.runId ? `?run_id=${state.runId}` : ''}`, 'patterns.csv');
        toast('已开始下载模式库');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
  },
};

export default miningPage;
