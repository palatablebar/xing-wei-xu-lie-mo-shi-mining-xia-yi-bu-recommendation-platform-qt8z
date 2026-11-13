import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
import { barList, emptyState, errorBox, errorMessage, esc, fmtPct, fmtTime, ladder, readouts, waterfall } from '../ui.js';
import { bindBanner, openCaliberConsole, pendingBanner } from '../caliber.js';

export const overviewPage = {
  async render(view, ctx) {
    view.innerHTML = '<div class="empty"><div class="mark">采样中…</div></div>';
    let data;
    let patterns;
    try {
      data = await api.get('/api/overview');
      patterns = await api.get('/api/patterns', { run_id: data.latest_run ? data.latest_run.id : '', limit: 8 });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => overviewPage.render(view, ctx));
      return;
    }
    const run = data.latest_run;
    const caliber = data.caliber || {};
    const latestVersion = caliber.latest_version;
    view.innerHTML = `
      ${pendingBanner(caliber.draft, ctx.user.role)}
      ${readouts([
        { label: '会话总量', value: data.sequences_total, unit: '条', hint: `均值 ${data.avg_events} 事件 / 会话` },
        { label: '推荐覆盖率', value: fmtPct(run ? run.coverage_pct : 0), hint: run ? `${run.covered_users}/${run.active_users} 位活跃用户` : '尚未挖掘', tone: 'hot' },
        { label: '模式库', value: data.patterns_total, unit: '条', hint: run ? `min_sup ${run.min_support_pct}% · 最长 ${run.max_len} 步` : '尚未挖掘' },
        { label: '待复核推荐', value: data.pending_total, unit: '条', hint: data.worker_alive ? 'worker 在岗' : 'worker 心跳超时', tone: 'cool' },
      ])}
      <section class="panel" style="margin:14px 0">
        <div class="panel-head">
          <h2>事件口径版本</h2>
          <div style="display:flex;gap:8px;align-items:center">
            <span class="meta">待发布 vs 正式</span>
            ${can(ctx.user.role, 'event:write') ? '<button class="btn sm ghost" id="overview-caliber">口径发布台</button>' : ''}
          </div>
        </div>
        <div class="panel-body">
          ${
            latestVersion
              ? `<dl class="kv">
                  <dt>当前版本</dt><dd class="mono">${esc(latestVersion.version_no)}
                    ${latestVersion.status === 'published' ? '<span class="badge ok">正式生效</span>' : '<span class="badge danger">已回滚</span>'}</dd>
                  <dt>变更事件</dt><dd>${esc((latestVersion.changed_codes || []).join(', ') || '初始基线')}</dd>
                  <dt>发布人 / 时间</dt><dd class="mono">${esc(latestVersion.published_by)} · ${fmtTime(latestVersion.published_at)}</dd>
                  <dt>预演摘要</dt><dd class="mono muted">${esc(JSON.stringify(latestVersion.rehearsal_summary || {}))}</dd>
                </dl>`
              : emptyState({ title: '还没有口径版本', hint: '首次 seed 会建立初始基线。' })
          }
          ${
            caliber.draft && caliber.draft.has_draft
              ? `<div class="legend" style="margin-top:10px">
                  <span class="hl">有 ${esc(caliber.draft.changes.length)} 项标记变更待发布；未发布前复核与导出仍按当前正式口径。</span>
                </div>`
              : '<div class="legend" style="margin-top:10px"><span>没有待发布草稿，正式口径即当前事件字典。</span></div>'
          }
        </div>
      </section>
      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>信号瀑布</h2><span class="meta">12 buckets · modules</span></div>
          <div class="panel-body">${waterfall(data.waterfall, data.modules)}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>模块事件量</h2><span class="meta">7d · events</span></div>
          <div class="panel-body">
            ${data.modules.length ? barList(data.modules) : emptyState({ title: '还没有埋点事件', hint: '管理员先登记事件字典。' })}
            <div class="legend" style="margin-top:12px"><span>转化会话 ${esc(data.converted_total)} / ${esc(data.sequences_total)}（${fmtPct(data.conversion_pct)}）</span></div>
          </div>
        </section>
      </div>
      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>模式支持度 TOP 8</h2><span class="meta">support / confidence</span></div>
          <div class="panel-body">
            ${ladder(patterns.items)}
            <div class="track" style="margin-top:10px">${(patterns.items || [])
              .slice(0, 3)
              .map((item) => `<span class="chip board">${esc(item.seq_key.split('>')[0])} › … <i>${esc(item.length)} 步</i></span>`)
              .join('')}</div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>最近一次挖掘</h2><span class="meta">latest run</span></div>
          <div class="panel-body">
            ${
              run
                ? `<dl class="kv">
                    <dt>运行号</dt><dd class="mono">${esc(run.run_no)}</dd>
                    <dt>状态</dt><dd>${esc(ENUMS.mineStatus[run.status] || run.status)}</dd>
                    <dt>开始</dt><dd>${fmtTime(run.started_at)}</dd>
                    <dt>模式</dt><dd>${esc(run.pattern_count)} 条 · top 支持度 ${fmtPct(run.top_support_pct)}</dd>
                    <dt>推荐</dt><dd>${esc(run.rec_count)} 条 · 覆盖 ${esc(run.covered_users)}/${esc(run.active_users)} 用户</dd>
                  </dl>
                  <div class="legend" style="margin-top:12px">
                    <span>复核：${(data.review || []).map((item) => `${esc(item.label)} ${esc(item.count)}`).join(' · ') || '暂无'}</span>
                  </div>`
                : emptyState({ title: '还没有挖掘记录', hint: '去「模式挖掘」发起一次 PrefixSpan。' })
            }
          </div>
        </section>
      </div>`;
    const refresh = () => overviewPage.render(view, ctx);
    bindBanner(view, ctx, refresh);
    view.querySelector('#overview-caliber')?.addEventListener('click', () => openCaliberConsole(view, ctx, refresh));
  },
};

export default overviewPage;
