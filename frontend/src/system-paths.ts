// 角色限定路径 — 单一来源，所有消费者引用（App.tsx 路由守卫 / AdminPage 等）。
// 路径与 App.tsx 真实路由表对齐（首页为 index 路由 '/'，不存在 /dashboard）。

// 长辈模式 3 Tab 实际路径（spec §6.6：首页 / 问答 / 我的）
export const ELDERLY_PATHS = ['/', '/chat', '/profile'];

// 长辈模式额外允许的常用健康页白名单（提醒/药箱/安全检查/体质/设置）
export const ELDERLY_ALLOWED_PATHS = [
  ...ELDERLY_PATHS,
  '/reminders',
  '/medicines',
  '/safety',
  '/constitution',
  '/settings',
];

// 管理员专属路径（/users、/schema、/backup 无对应路由，已移除；/settings 为用户设置页，非管理员专属）
export const ADMIN_PATHS = ['/admin'];

export function isSystemPath(pathname: string): boolean {
  return ADMIN_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/'),
  );
}
