import { Grid } from 'antd';

/**
 * Returns true when the viewport is below the `md` breakpoint (768px).
 * Use this to switch between mobile and desktop layouts.
 */
export function useIsMobile(): boolean {
  const screens = Grid.useBreakpoint();
  return !screens.md; // md = 768px, below = mobile
}

/**
 * Thin wrapper around AntD Grid.useBreakpoint() for finer-grained
 * responsive logic (e.g. tablet vs desktop).
 */
export function useBreakpoint() {
  return Grid.useBreakpoint();
}
