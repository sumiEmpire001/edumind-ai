import { test, expect } from "@playwright/test";
import { create, login } from "./helpers";

// Exercise layout transitions as well as common phone/tablet/desktop sizes.
test("workspace tools remain usable across responsive breakpoints", async ({
  page,
}, testInfo) => {
  const email = await create(page);
  await login(page, email);
  await expect(page).toHaveURL("/app");
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
      await expect(page).toHaveURL(route);
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
        await page.screenshot({
          fullPage: true,
          path: testInfo.outputPath(
            `ui${route.replaceAll("/", "-")}-${width}.png`,
          ),
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
  await expect(page).toHaveURL("/app");
  await page.goto("/app/chat");
  await page.getByRole("button", { name: "Create a conversation" }).click();
  await page
    .getByRole("button", { name: "Explain a concept", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Your question", exact: true }),
  ).toHaveValue("Explain this concept step by step: ");
  await expect(
    page.getByRole("textbox", { name: "Your question", exact: true }),
  ).toBeFocused();
  await expect(page.getByRole("article")).toHaveCount(0);
});

test("finds saved chats and keeps the composer usable on short phone screens", async ({
  page,
}, testInfo) => {
  test.setTimeout(60000);
  const email = await create(page);
  await login(page, email);
  await expect(page).toHaveURL("/app");
  for (const title of ["Mechanics revision", "Biology revision"]) {
    await page.goto("/app/chat");
    await page
      .getByRole("button", { name: "Create a conversation", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Your question", exact: true }),
    ).toBeEnabled();
    await page.getByRole("button", { name: "Rename", exact: true }).click();
    await page.getByLabel("Conversation title", { exact: true }).fill(title);
    await page.getByRole("button", { name: "Save title", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
  }
  const question = page.getByRole("textbox", {
    name: "Your question",
    exact: true,
  });
  await question.fill("Keep this unfinished question");
  const toggle = page.getByRole("button", { name: /^Conversations/ });
  if (await toggle.isVisible()) await toggle.click();
  const search = page.getByRole("searchbox", {
    name: "Search conversation titles",
  });
  const history = page.getByRole("navigation", {
    name: "Conversation history",
  });
  await search.fill(" MECHANICS ");
  await expect(
    history.getByRole("link", { name: /Mechanics revision/ }),
  ).toBeVisible();
  await expect(
    history.getByRole("link", { name: /Biology revision/ }),
  ).toHaveCount(0);
  await expect(question).toHaveValue("Keep this unfinished question");
  await search.fill("No matching title");
  await expect(page.getByText(/No matching titles/)).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(search).toBeFocused();
  await history.getByRole("link", { name: /Mechanics revision/ }).click();
  await expect(
    page.getByRole("heading", { name: "Mechanics revision", exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 500 });
  for (let i = 1; i <= 2; i++) {
    await question.fill(`Explain forces and motion, example ${i}`);
    await page
      .getByRole("button", { name: "Send question", exact: true })
      .click();
    await expect(
      page.getByRole("article", { name: "EduMind response", exact: true }),
    ).toHaveCount(i);
    await expect(question).toHaveValue("");
  }
  const messages = page.locator(".chat-messages");
  await messages.evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.getByRole("button", { name: "Jump to latest" }).click();
  await expect
    .poll(() =>
      messages.evaluate(
        (element) =>
          element.scrollHeight - element.clientHeight - element.scrollTop,
      ),
    )
    .toBeLessThan(50);
  await page.reload();
  await expect(
    page.getByRole("article", { name: "EduMind response", exact: true }),
  ).toHaveCount(2);
  await expect
    .poll(() =>
      messages.evaluate(
        (element) =>
          element.scrollHeight - element.clientHeight - element.scrollTop,
      ),
    )
    .toBeLessThan(50);
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("ui-chat-short-screen.png"),
  });
});

test("finds saved documents without discarding unsaved section edits", async ({
  page,
}, testInfo) => {
  const email = await create(page);
  await login(page, email);
  await expect(page).toHaveURL("/app");
  for (const title of ["Mechanics report", "Biology report"]) {
    await page.goto("/app/studio");
    await page.getByLabel("Document title", { exact: true }).fill(title);
    await page
      .getByLabel("What should this report cover?", { exact: true })
      .fill("Explain the topic with clear examples and a conclusion.");
    await page
      .getByRole("button", { name: "Create document", exact: true })
      .click();
    await expect(page).toHaveURL(/\/app\/studio\/[0-9a-f-]+$/);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
  }
  const section = page.getByLabel("Section text", { exact: true });
  await section.fill("Keep this unsaved section text.");
  const search = page.getByRole("searchbox", { name: "Search draft titles" });
  await search.fill(" MECHANICS ");
  await expect(
    page.getByRole("link", { name: /Mechanics report/ }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /Biology report/ })).toHaveCount(
    0,
  );
  await expect(section).toHaveValue("Keep this unsaved section text.");
  await search.fill("unknown title");
  await expect(page.getByText(/No matching draft titles/)).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(search).toBeFocused();
  await expect(
    page.getByRole("link", { name: /Biology report/ }),
  ).toBeVisible();
  await expect(section).toHaveValue("Keep this unsaved section text.");
  await page.screenshot({
    fullPage: true,
    path: testInfo.outputPath("ui-studio-draft-finder.png"),
  });
});
