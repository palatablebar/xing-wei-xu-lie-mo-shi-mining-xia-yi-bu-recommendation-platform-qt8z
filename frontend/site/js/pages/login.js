import { api } from '../api.js';
import { session } from '../store.js';
import { BRAND } from '../config.js';
import { errorMessage, esc, toast } from '../ui.js';

const TRACES = [
  ['00:12', 'acct.login › board.view › report.build', '76%'],
  ['00:24', 'board.filter › board.view › report.export', '61%'],
  ['00:36', 'alert.create › alert.ack › board.view', '34%'],
];

export const loginPage = {
  async render(root, ctx) {
    root.className = 'login-host';
    root.innerHTML = `
      <div class="login">
        <section class="login-scope">
          <div class="scope-head">
            <span>${esc(BRAND.short)} / SEQUENCE SCOPE</span>
            <span>12 CH · min_sup 3% · max_len 5</span>
          </div>
          <div>
            <h1>${esc(BRAND.title)}<br /><em>下一步，先看序列。</em></h1>
            <p class="tagline">${esc(BRAND.loginLead)}</p>
          </div>
          <div class="scope-traces">
            ${TRACES.map(
              ([stamp, path, width]) => `<div class="trace">
                <i>${esc(stamp)}</i>
                <span class="line" style="--w:${esc(width)}"></span>
                <span>${esc(path)}</span>
              </div>`,
            ).join('')}
          </div>
          <div class="scope-head"><span>${esc(BRAND.org)}</span><span>INTERNAL · UTC+8</span></div>
        </section>
        <section class="login-panel">
          <div class="coords">[ AUTH ] OPERATOR TERMINAL</div>
          <form class="login-card" id="login-form" novalidate>
            <div>
              <div class="brand">${esc(BRAND.short)}</div>
              <div class="sub">使用内部账号登录。三个演示账号权限不同，通道与按钮随角色变化。</div>
            </div>
            <div class="field">
              <label for="email">OPERATOR</label>
              <input id="email" name="email" type="email" autocomplete="username" value="admin@${esc(BRAND.short)}.io" required />
            </div>
            <div class="field">
              <label for="password">PASSPHRASE</label>
              <input id="password" name="password" type="password" autocomplete="current-password" value="Demo@2026" required />
            </div>
            <div class="form-error" id="login-error" role="alert"></div>
            <button class="btn accent" id="login-submit" type="submit">接入信号台</button>
            <div class="login-hint">
              演示账号（密码 <code>Demo@2026</code>）：<br />
              <code>admin@${esc(BRAND.short)}.io</code> 管理员 · <code>analyst@${esc(BRAND.short)}.io</code> 分析专员 ·
              <code>viewer@${esc(BRAND.short)}.io</code> 只读
            </div>
          </form>
        </section>
      </div>`;

    const form = root.querySelector('#login-form');
    const errorNode = root.querySelector('#login-error');
    const submit = root.querySelector('#login-submit');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorNode.textContent = '';
      submit.disabled = true;
      submit.textContent = '校验中…';
      try {
        const result = await api.post('/api/auth/login', {
          email: form.email.value.trim(),
          password: form.password.value,
        });
        session.set(result.access_token, result.user);
        toast(`欢迎回来，${result.user.display_name}`);
        location.hash = '#/overview';
        await ctx.reload();
      } catch (err) {
        errorNode.textContent = err.code === 'AUTH_INVALID' ? '账号或密码不正确' : errorMessage(err);
      } finally {
        submit.disabled = false;
        submit.textContent = '接入信号台';
      }
    });
  },
};

export default loginPage;
