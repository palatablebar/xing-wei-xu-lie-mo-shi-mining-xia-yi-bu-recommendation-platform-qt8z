import { api } from './api.js';
import { BRAND, NAV, ROLE_LABELS, can } from './config.js';
import { session } from './store.js';
import { errorMessage, esc, fmtPct, toast } from './ui.js';
import loginPage from './pages/login.js';
import overviewPage from './pages/overview.js';
import eventsPage from './pages/events.js';
import sequencesPage from './pages/sequences.js';
import miningPage from './pages/mining.js';
import recommendationsPage from './pages/recommendations.js';
import auditPage from './pages/audit.js';

const routes = [
  { path: '#/overview', page: overviewPage, permission: 'overview:read' },
  { path: '#/events', page: eventsPage, permission: 'event:read' },
  { path: '#/sequences', page: sequencesPage, permission: 'sequence:read' },
  { path: '#/mining', page: miningPage, permission: 'mining:read' },
  { path: '#/recommendations', page: recommendationsPage, permission: 'recommendation:read' },
  { path: '#/audit', page: auditPage, permission: 'audit:read' },
];

let currentUser = null;
let listening = false;

function setActiveNav(path) {
  document.querySelectorAll('.channels a').forEach((link) => {
    link.classList.toggle('active', link.getAttribute('href') === path);
  });
}

function forbidden(view, ctx) {
  view.innerHTML = `<section class="panel"><div class="empty" data-testid="forbidden">
    <div class="mark">没有该通道权限</div>
    <p>当前角色是「${esc(ROLE_LABELS[ctx.user.role] || ctx.user.role)}」，这个模块需要更高权限。</p>
    <button class="btn ghost" data-back>回到总览</button>
  </div></section>`;
  view.querySelector('[data-back]')?.addEventListener('click', () => {
    location.hash = '#/overview';
  });
}

async function renderLogin() {
  currentUser = null;
  const root = document.getElementById('app');
  root.className = '';
  await loginPage.render(root, { reload: boot });
}

async function renderRoute() {
  const view = document.getElementById('view');
  if (!view || !currentUser) return;
  const raw = location.hash || '#/overview';
  const [path, qs] = raw.split('?');
  const query = Object.fromEntries(new URLSearchParams(qs || ''));
  if (path === '#/login') {
    session.clear();
    return renderLogin();
  }
  const route = routes.find((item) => item.path === path) || routes[0];
  if (!can(currentUser.role, route.permission)) {
    setActiveNav('');
    return forbidden(view, { user: currentUser });
  }
  setActiveNav(route.path);
  view.innerHTML = '<div class="empty"><div class="mark">读取信号…</div></div>';
  const ctx = {
    user: currentUser,
    query,
    navigate: (hash) => {
      location.hash = hash;
    },
    reload: boot,
    logout,
  };
  try {
    await route.page.render(view, ctx);
  } catch (err) {
    view.innerHTML = `<div class="error-box"><span>${esc(errorMessage(err))}</span><button class="btn sm ghost" data-retry>重试</button></div>`;
    view.querySelector('[data-retry]')?.addEventListener('click', () => renderRoute());
  }
}

function logout() {
  session.clear();
  toast('已退出信号台');
  location.hash = '#/login';
  boot();
}

function renderTicker(data) {
  const node = document.getElementById('ticker');
  if (!node) return;
  const run = data.latest_run || {};
  node.innerHTML = `
    <span><span class="dot">▮</span> 会话 <b>${esc(data.sequences_total)}</b></span>
    <span>活跃用户 <b>${esc(data.users_total)}</b></span>
    <span>模式库 <b>${esc(data.patterns_total)}</b></span>
    <span>覆盖率 <b>${fmtPct(run.coverage_pct || 0)}</b></span>
    <span>待复核推荐 <b>${esc(data.pending_total)}</b></span>
    <span>worker <b>${data.worker_alive ? '在岗' : '心跳超时'}</b></span>
    <span>${esc(BRAND.org)}</span>`;
}

function renderShell() {
  const root = document.getElementById('app');
  root.className = '';
  const navItems = NAV.filter((item) => can(currentUser.role, item.permission));
  root.innerHTML = `
    <div class="console">
      <header class="command">
        <div class="mark">${esc(BRAND.short)}<small>${esc(BRAND.edition)}</small></div>
        <div class="title">${esc(BRAND.title)}</div>
        <nav class="channels">
          ${navItems
            .map(
              (item) =>
                `<a href="${item.to}" data-nav="${item.to.replace('#/', '')}" data-testid="nav-${item.to.replace('#/', '')}"><i>${item.no}</i>${esc(item.label)}</a>`,
            )
            .join('')}
        </nav>
        <div class="who">
          <b data-testid="who-name">${esc(currentUser.display_name)}</b>
          <span class="tiny">${esc(currentUser.email)}</span>
          <span class="tiny">${esc(ROLE_LABELS[currentUser.role] || currentUser.role)}</span>
        </div>
        <button class="btn sm ghost" id="logout">退出</button>
      </header>
      <section class="view" id="view"></section>
      <footer class="ticker" id="ticker" data-testid="ticker">
        <span><span class="dot">▮</span> 正在采样…</span>
      </footer>
    </div>`;
  root.querySelector('#logout')?.addEventListener('click', logout);
  api
    .get('/api/overview')
    .then((data) => renderTicker(data))
    .catch(() => {});
}

async function boot() {
  if (!listening) {
    window.addEventListener('hashchange', () => {
      if (!session.token()) return renderLogin();
      renderRoute();
    });
    listening = true;
  }
  if (!session.token()) return renderLogin();
  try {
    const me = await api.get('/api/auth/me');
    currentUser = me.user;
    session.setUser(me.user);
  } catch {
    session.clear();
    return renderLogin();
  }
  renderShell();
  await renderRoute();
}

boot();
