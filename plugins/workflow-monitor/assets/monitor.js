const stageNames = {scan: '并行扫描', review: '复核', synthesis: '综合', independent_review: '独立评审'};
const stateNames = {queued: '待开始', running: '执行中', returned: '已返回', submitted: '待验收', accepted: '已验收', rework: '待修订', revision_requested: '要求修订'};
const el = id => document.getElementById(id);
function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = String(text);
  if (className) item.className = className;
  return item;
}
function render(data) {
  const tasks = data.tasks || [];
  const accepted = tasks.filter(t => t.state === 'accepted' && t.acceptance_valid).length;
  const returned = tasks.filter(t => t.attempts.at(-1)?.returned).length;
  el('summary').textContent = `${data.state === 'finished' ? '已完成' : '进行中'} · 已返回 ${returned}/${tasks.length} · 已验收 ${accepted}/${tasks.length}`;
  const stages = el('stages'); stages.replaceChildren();
  const current = data.stages.indexOf(data.stage);
  data.stages.forEach((name, index) => {
    const relevant = tasks.filter(t => t.stage === name && t.state !== 'revision_requested');
    const card = node('div', undefined, `stage ${index === current && data.state !== 'finished' ? 'active' : ''} ${index < current || data.state === 'finished' ? 'done' : ''}`);
    card.append(node('span', `0${index + 1}`, 'index'), node('strong', stageNames[name] || name));
    const returnedCount = relevant.filter(t => t.attempts.at(-1)?.returned).length;
    const acceptedCount = relevant.filter(t => t.state === 'accepted' && t.acceptance_valid).length;
    card.append(node('small', `返回 ${returnedCount}/${relevant.length} · 验收 ${acceptedCount}/${relevant.length}`));
    stages.append(card);
  });
  const list = el('tasks'); list.replaceChildren();
  tasks.forEach(t => {
    const card = node('article', undefined, 'task');
    const head = node('div', undefined, 'task-head');
    head.append(node('h3', t.name), node('span', stateNames[t.state] || t.state));
    card.append(head);
    const returnedAttempts = t.attempts.filter(a => a.returned).length;
    const interruptedAttempts = t.attempts.filter(a => a.interrupted).length;
    card.append(node('p', `${stageNames[t.stage] || t.stage} · 尝试 ${t.attempts.length} 次，返回 ${returnedAttempts} 次${interruptedAttempts ? `，中断 ${interruptedAttempts} 次` : ''}${t.accepted_version ? ` · 验收报告 v${t.accepted_version}` : ''}${t.accepted_version && !t.acceptance_valid ? ' · 报告已变化' : ''}`, 'meta'));
    const links = node('div', undefined, 'reports');
    t.reports.forEach(r => {
      const link = node('a', `报告 v${r.version}${r.valid ? '' : '（原文件已变化）'}`);
      link.href = `/api/reports/${encodeURIComponent(t.id)}/${r.version}`;
      link.target = '_blank'; link.rel = 'noopener';
      links.append(link);
    });
    card.append(links); list.append(card);
  });
  if (!tasks.length) list.append(node('p', '尚无任务。', 'meta'));
  const revisions = el('revisions'); revisions.replaceChildren();
  (data.revisions || []).forEach((r, index) => revisions.append(node('div', `第 ${index + 1} 次修订：评审报告 v${r.review_version} 要求修改综合报告 v${r.synthesis_version}`, 'revision')));
  if (!(data.revisions || []).length) revisions.append(node('p', '暂无修订。', 'meta'));
  const health = {registered: '已注册', degraded: '插件采集曾出现故障，需检查', unregistered: '未注册', unavailable: '状态不可用', unknown: '未提供注册信息', finished: '已结束'};
  el('activity').textContent = `采集：${health[data.collector_health] || '状态未知'} · 最近活动：${data.last_observation_at ? new Date(data.last_observation_at * 1000).toLocaleString() : '暂无'} · 事件 ${data.observations}`;
  el('connection').textContent = data.state === 'finished' ? '已完成' : '已连接';
  el('connection').classList.remove('offline');
}
async function refresh() {
  try {
    const response = await fetch('/api/status', {cache: 'no-store'});
    if (!response.ok) throw new Error('status unavailable');
    render(await response.json());
  } catch (_) {
    el('connection').textContent = '连接中断，正在重试';
    el('connection').classList.add('offline');
  }
}
refresh(); setInterval(refresh, 2500);
