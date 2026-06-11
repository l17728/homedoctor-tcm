export const ELDERLY_PATHS = ['/dashboard', '/chat', '/profile'];

export const ADMIN_PATHS = ['/settings', '/users', '/schema', '/backup'];

export function isSystemPath(pathname: string): boolean {
  return ADMIN_PATHS.some((p) => pathname.startsWith(p));
}
