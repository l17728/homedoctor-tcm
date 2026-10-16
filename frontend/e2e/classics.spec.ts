/**
 * Classics (经典读诵) bookshelf and reader E2E tests.
 *
 * Covers:
 * - Bookshelf page renders with title, category filters, book cards
 * - Category filter interaction
 * - Book card click navigates to reader page
 * - Reader page shows chapter list, tabs (原文/翻译/心得)
 * - Reader chapter text is visible after load
 * - Back button returns to bookshelf
 */
import { test, expect } from '@playwright/test';
import { registerWithConsent as register } from './test-helpers';

test.describe('Classics Bookshelf — 经典读诵书柜', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should load bookshelf page with title and description', async ({ page }) => {
    await page.goto('/classics');

    await expect(page).toHaveURL('/classics');
    // Page title heading "经典读诵" (use heading role to avoid sidebar menu match)
    await expect(page.getByRole('heading', { name: /经典读诵/ })).toBeVisible();
    // Description text
    await expect(page.getByText(/千年医典/)).toBeVisible();
  });

  test('should show category filter pills (全部/医经/方书/伤寒/温病)', async ({
    page,
  }) => {
    await page.goto('/classics');

    const categories = ['全部', '医经', '方书', '伤寒', '温病'];
    for (const cat of categories) {
      await expect(page.locator('.cls-cat-pill').filter({ hasText: cat })).toBeVisible();
    }
  });

  test('should switch filter when clicking a category pill', async ({ page }) => {
    await page.goto('/classics');

    // Click "医经" filter
    const pill = page.locator('.cls-cat-pill').filter({ hasText: '医经' });
    await pill.click();

    // The clicked pill should get the active class
    await expect(pill).toHaveClass(/is-active/);

    // Switch back to 全部
    const allPill = page.locator('.cls-cat-pill').filter({ hasText: '全部' });
    await allPill.click();
    await expect(allPill).toHaveClass(/is-active/);
  });

  test('should show either book cards, loading skeleton, or empty state', async ({
    page,
  }) => {
    await page.goto('/classics');

    // Wait for loading to finish
    await page.waitForTimeout(1000);

    await expect(page.locator('.ant-skeleton')).toHaveCount(0);
    const hasBooks = await page.locator('.cls-book').first().isVisible().catch(() => false);
    const hasEmpty = await page.locator('.ant-empty').isVisible().catch(() => false);

    // At least one of the three states must be present
    expect(hasBooks || hasEmpty).toBeTruthy();
  });

  test('should show seal (典) badge in header', async ({ page }) => {
    await page.goto('/classics');

    // The seal span with title="经典"
    await expect(page.locator('.cls-seal')).toBeVisible();
  });
});

test.describe('Classics Reader — 经典阅读器', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should navigate to reader page when clicking a book card', async ({ page }) => {
    await page.goto('/classics');

    // Wait for content to load
    await page.waitForTimeout(1500);

    const bookCards = page.locator('.cls-book');
    const cardCount = await bookCards.count();

    if (cardCount > 0) {
      // Click first book to open reader
      await bookCards.first().click();

      // Should navigate to /classics/:id
      await page.waitForURL(/\/classics\/[^/]+/);
      await expect(page).toHaveURL(/\/classics\/[^/]+/);

      // Reader should show "返回书柜" button
      await expect(page.getByRole('button', { name: /返回书柜/ })).toBeVisible();
    } else {
      // No books — skip (empty state covered in bookshelf tests)
      test.skip();
    }
  });

  test('should show chapter list sidebar and tabs in reader', async ({ page }) => {
    await page.goto('/classics');
    await page.waitForTimeout(1500);

    const bookCards = page.locator('.cls-book');
    const cardCount = await bookCards.count();

    if (cardCount === 0) {
      test.skip();
      return;
    }

    await bookCards.first().click();
    await page.waitForURL(/\/classics\/[^/]+/);
    await page.waitForTimeout(2000);

    // Chapter list section — desktop shows "章节目录" text
    await expect(page.getByText('章节目录')).toBeVisible();

    // Tabs: 原文, 翻译, 学习心得
    await expect(page.getByRole('tab', { name: /原文/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /翻译/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /学习心得/ })).toBeVisible();
  });

  test('should display chapter text in original tab', async ({ page }) => {
    await page.goto('/classics');
    await page.waitForTimeout(1500);

    const bookCards = page.locator('.cls-book');
    const cardCount = await bookCards.count();

    if (cardCount === 0) {
      test.skip();
      return;
    }

    await bookCards.first().click();
    await page.waitForURL(/\/classics\/[^/]+/);
    await page.waitForTimeout(2000);

    // The classic text container (div, not the h4 title which shares the class)
    const textContainer = page.locator('div.cls-classic-text');
    await expect(textContainer).toBeVisible();

    // If there are chapter items, clicking one should load text
    const chapterItems = page.locator('.cls-chapter-item');
    const chapterCount = await chapterItems.count();

    if (chapterCount > 1) {
      // Click second chapter
      await chapterItems.nth(1).click();
      await page.waitForTimeout(1500);

      // Text container should still be visible (re-rendered with new chapter)
      await expect(textContainer).toBeVisible();
    }
  });

  test('should switch to translation tab', async ({ page }) => {
    await page.goto('/classics');
    await page.waitForTimeout(1500);

    const bookCards = page.locator('.cls-book');
    const cardCount = await bookCards.count();

    if (cardCount === 0) {
      test.skip();
      return;
    }

    await bookCards.first().click();
    await page.waitForURL(/\/classics\/[^/]+/);
    await page.waitForTimeout(2000);

    // Click translation tab
    await page.getByRole('tab', { name: /翻译/ }).click();
    await page.waitForTimeout(500);

    // Should show translation-related content:
    // Either 白话译文 heading, "AI 一键翻译本章" button, or "本章暂无翻译" empty
    const hasTranslationUI = await page
      .getByText(/白话译文|AI.*翻译本章|本章暂无翻译/)
      .first()
      .isVisible()
      .catch(() => false);
    expect(hasTranslationUI).toBeTruthy();
  });

  test('should return to bookshelf via back button', async ({ page }) => {
    await page.goto('/classics');
    await page.waitForTimeout(1500);

    const bookCards = page.locator('.cls-book');
    const cardCount = await bookCards.count();

    if (cardCount === 0) {
      test.skip();
      return;
    }

    await bookCards.first().click();
    await page.waitForURL(/\/classics\/[^/]+/);

    // Click back button
    await page.getByRole('button', { name: /返回书柜/ }).click();
    await page.waitForURL('/classics');
    await expect(page).toHaveURL('/classics');
    await expect(page.getByRole('heading', { name: /经典读诵/ })).toBeVisible();
  });
});
