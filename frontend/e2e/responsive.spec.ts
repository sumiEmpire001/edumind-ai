import { test, expect } from "@playwright/test";
import { create, login } from "./helpers";

// Exercise layout transitions as well as common phone/tablet/desktop sizes.
test("workspace tools remain usable across responsive breakpoints", async ({
  page,
}, testInfo) => {
  const email = await create(page);
  await login(page, email);
  for (const width of [360, 390, 768, 920, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of [
      "/app",
      "/app/chat",
      "/app/studio",
      "/app/account",
      "/app/knowledge",
    ]) {
      await page.goto(route);
      await expect(page.locator("#main-content")).toBeVisible();
      await expect(page.getByRole("heading").first()).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth + 1,
        ),
        `${route} overflows at ${width}px`,
      ).toBe(true);
      if (route === "/app/chat" && width > 900) {
        const history = await page.locator(".chat-history").boundingBox();
        const panel = await page.locator(".chat-panel").boundingBox();
        expect(history).not.toBeNull();
        expect(panel).not.toBeNull();
        expect(history!.x + history!.width).toBeLessThanOrEqual(panel!.x + 1);
      }
      if (width === 390 || width === 1440) {
        await testInfo.attach(`${route.replaceAll("/", "-")}-${width}`, {
          body: await page.screenshot({ fullPage: true }),
          contentType: "image/png",
        });
      }
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app");
  const menu = page.getByRole("button", { name: /^Menu/ });
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await page
    .getByRole("link", { name: "Document Studio", exact: true })
    .focus();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await expect(menu).toBeFocused();
  await menu.click();
  await page
    .getByRole("link", { name: "Document Studio", exact: true })
    .click();
  await expect(page).toHaveURL("/app/studio");
  await expect(menu).toHaveAttribute("aria-expanded", "false");
});

test("question starters populate the composer without submitting", async ({
  page,
}) => {
  const email = await create(page);
  await login(page, email);
  await page.goto("/app/chat");
  await page.getByRole("button", { name: "Create a conversation" }).click();
  await page
    .getByRole("button", { name: "Explain a concept", exact: true })
    .click();
  await expect(page.getByLabel("Your question", { exact: true })).toHaveValue(
    "Explain this concept step by step: ",
  );
  await expect(page.getByLabel("Your question", { exact: true })).toBeFocused();
  await expect(page.getByRole("article")).toHaveCount(0);
});
