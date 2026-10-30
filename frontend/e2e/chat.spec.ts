import { test, expect, type Page } from "@playwright/test";
import { api, origin, pass, create } from "./helpers";

async function openChat(page: Page) {
  const email = await create(page);
  const response = await page.request.post(`${api}/auth/login`, {
    headers: { Origin: origin },
    data: { email, password: pass },
  });
  expect(response.status()).toBe(200);
  const token = (await response.json()).access_token as string;
  await page.goto("/app/chat");
  await expect(
    page.getByText(/responses are scripted test fixtures/),
  ).toBeVisible();
  return token;
}
async function newConversation(page: Page) {
  await page
    .getByRole("button", { name: "Create a conversation", exact: true })
    .click();
  await expect(page).toHaveURL(/\/app\/chat\/[0-9a-f-]{36}$/);
  await expect(page.getByLabel("Your question")).toBeEnabled();
  return page.url().split("/").pop()!;
}
async function ask(page: Page, question: string, count: number) {
  await page.getByLabel("Your question").fill(question);
  await page
    .getByRole("button", { name: "Send question", exact: true })
    .click();
  await expect(
    page.getByRole("article", { name: "EduMind response", exact: true }),
  ).toHaveCount(count);
  await expect(page.getByLabel("Your question")).toHaveValue("");
}

test.beforeEach(({ page }) => {
  page.on("pageerror", (error) => {
    throw new Error(`Browser JavaScript failed: ${error.name}`);
  });
});

test("persists a formatted conversation, follows up, copies, renames and removes it", async ({
  page,
  context,
  browserName,
}) => {
  await openChat(page);
  await newConversation(page);
  await ask(page, "What is force?", 1);
  await ask(page, "Why are those units correct?", 2);
  await expect(
    page.getByText("Context contains 2 user question(s).", { exact: true }),
  ).toBeVisible();
  const answer = page
    .getByRole("article", { name: "EduMind response", exact: true })
    .first();
  expect(await answer.locator(".katex").count()).toBeGreaterThan(0);
  await expect(answer.getByRole("table")).toBeVisible();
  await expect(answer.getByRole("button", { name: "Copy code" })).toBeVisible();
  if (browserName === "chromium")
    await context.grantPermissions(["clipboard-read", "clipboard-write"], {
      origin,
    });
  await answer.getByRole("button", { name: "Copy answer" }).click();
  if (browserName === "chromium") {
    await expect(answer.getByText("Copied", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
      "scripted verification response",
    );
  } else {
    await expect(
      answer
        .locator(".copy-status")
        .filter({ hasText: /Copied|Copy unavailable/ }),
    ).toBeVisible();
  }
  await page.reload();
  await expect(
    page.getByRole("article", { name: "Your question", exact: true }),
  ).toHaveCount(2);
  await expect(
    page.getByRole("article", { name: "EduMind response", exact: true }),
  ).toHaveCount(2);
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await page.getByLabel("Conversation title").fill("My mechanics notes");
  await page.getByRole("button", { name: "Save title", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "My mechanics notes", exact: true }),
  ).toBeVisible();
  const historyToggle = page.getByRole("button", { name: /^Conversations/ });
  if (await historyToggle.isVisible()) await historyToggle.click();
  await expect(
    page
      .getByRole("navigation", { name: "Conversation history" })
      .getByRole("link", { name: /My mechanics notes/ }),
  ).toBeVisible();
  if (await historyToggle.isVisible()) await historyToggle.click();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  expect(overflow).toBe(false);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page).toHaveURL("/app/chat");
  await expect(
    page
      .getByRole("navigation", { name: "Conversation history" })
      .getByRole("link", { name: /My mechanics notes/ }),
  ).toHaveCount(0);
});

test("recovers a lost response and replays the same request without duplicate messages", async ({
  page,
}) => {
  const token = await openChat(page);
  const cid = await newConversation(page);
  let sent: { request_id: string; content: string } | undefined;
  await page.route("**/api/v1/conversations/*/messages", async (route) => {
    sent = route.request().postDataJSON();
    await route.fetch(); // The real server saves the answer; only its browser delivery is interrupted.
    await route.abort("failed");
  });
  await page
    .getByLabel("Your question")
    .fill("Recover this mechanics question");
  await page
    .getByRole("button", { name: "Send question", exact: true })
    .click();
  await expect(
    page.getByText(
      "Your saved answer was recovered after a connection interruption.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.unroute("**/api/v1/conversations/*/messages");
  const replay = await page.request.post(
    `${api}/conversations/${cid}/messages`,
    {
      headers: { Origin: origin, Authorization: `Bearer ${token}` },
      data: sent,
    },
  );
  expect(replay.status()).toBe(200);
  expect((await replay.json()).replayed).toBe(true);
  await page.reload();
  await expect(
    page.getByRole("article", { name: "Your question", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("article", { name: "EduMind response", exact: true }),
  ).toHaveCount(1);
});

test("does not reveal another account’s conversation through a direct link", async ({
  page,
  browser,
}) => {
  await openChat(page);
  const cid = await newConversation(page);
  await ask(page, "Private mechanics topic", 1);
  const separate = await browser.newContext();
  try {
    const other = await separate.newPage();
    await openChat(other);
    await other.goto(`/app/chat/${cid}`);
    await expect(other.getByRole("alert")).toHaveText(
      /This conversation is not available/,
    );
    await expect(
      other.getByText("Private mechanics topic", { exact: true }),
    ).toHaveCount(0);
    await expect(other.getByLabel("Your question")).toHaveCount(0);
  } finally {
    await separate.close();
  }
});

test("shows an honest unconfigured state while conversation management still works", async ({
  page,
}) => {
  await page.route("**/api/v1/chat/capabilities", (route) =>
    route.fulfill({
      json: { available: false, mode: "unconfigured", timeout_seconds: 20 },
    }),
  );
  const email = await create(page);
  expect(
    (
      await page.request.post(`${api}/auth/login`, {
        headers: { Origin: origin },
        data: { email, password: pass },
      })
    ).status(),
  ).toBe(200);
  await page.goto("/app/chat");
  await page
    .getByRole("button", { name: "Create a conversation", exact: true })
    .click();
  await expect(page.getByText(/AI answers aren’t connected yet/)).toBeVisible();
  await expect(page.getByLabel("Your question")).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Send question", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("article", { name: "EduMind response", exact: true }),
  ).toHaveCount(0);
});
