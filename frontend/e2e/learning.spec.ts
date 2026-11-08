import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { create, login, signout } from "./helpers";

test("a nominated question becomes searchable only after a verified admin review", async ({
  page,
}) => {
  const email = await create(page);
  const key = `acceleration${randomUUID().replaceAll("-", "")}`;
  const question = `Explain ${key}`;
  await login(page, email);
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/learning");
  await expect(
    page.getByRole("heading", { name: "Knowledge that grows with you." }),
  ).toBeVisible();
  await page.getByLabel("Academic question", { exact: true }).fill(question);
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Submit question for review" })
    .click();
  await expect(page.getByText(/Question submitted for review/)).toBeVisible();
  await page.getByLabel("Search question").fill(key);
  await page
    .getByRole("button", { name: "Search knowledge", exact: true })
    .click();
  await expect(page.getByText(/No matching approved knowledge/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download training JSONL" }),
  ).toHaveCount(0);
  await signout(page);
  await login(page, "admin-e2e@example.com");
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/learning");
  const item = page.getByRole("article").filter({
    has: page.getByRole("heading", { name: question, exact: true }),
  });
  await item
    .getByLabel("Verified answer")
    .fill(`${key} describes change in velocity per unit time.`);
  await item
    .getByLabel("Evidence and source reference")
    .fill("Reviewer-authored test physics explanation.");
  await item.getByRole("checkbox").check();
  await item.getByLabel("Decision", { exact: true }).selectOption("approved");
  await item.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByText(/Review saved/)).toBeVisible();
  await page.getByLabel("Search question").fill(key);
  await page
    .getByRole("button", { name: "Search knowledge", exact: true })
    .click();
  await expect(
    page
      .locator(".learning-results")
      .getByText(`${key} describes change in velocity per unit time.`, {
        exact: true,
      }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "API progress" }),
  ).toContainText("not configured");
});
