import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { api, origin, pass, login, signout } from "./helpers";

test("contributor upload, administrator preview/review, processing and removal", async ({
  page,
}) => {
  const title = `Mechanics ${randomUUID()}`;
  await login(page, "contributor-e2e@example.com");
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/knowledge");
  await expect(
    page.getByRole("button", { name: "Submit for review" }),
  ).toBeEnabled();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Discipline", { exact: true }).fill("Physics");
  await page.getByLabel("Document", { exact: true }).setInputFiles({
    name: "mechanics.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(`Force equals mass times acceleration. ${title}`),
  });
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(
    page.getByText(/Submitted for administrator review/),
  ).toBeVisible();
  let submission = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(submission.getByText("pending", { exact: true })).toBeVisible();
  await expect(
    submission.getByRole("button", { name: "Approve", exact: true }),
  ).toHaveCount(0);
  await signout(page);
  await login(page, "admin-e2e@example.com");
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/knowledge");
  submission = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) });
  await submission
    .getByRole("button", { name: "Preview document text" })
    .click();
  await expect(
    page.getByText(/Force equals mass times acceleration/),
  ).toBeVisible();
  await submission
    .getByRole("button", { name: "Approve", exact: true })
    .click();
  await expect(
    page.getByText(/Approved. Documents become searchable/),
  ).toBeVisible();
  const r = await page.request.post(`${api}/auth/login`, {
    headers: { Origin: origin },
    data: { email: "admin-e2e@example.com", password: pass },
  });
  const token = (await r.json()).access_token;
  const processed = await page.request.post(
    "http://127.0.0.1:8000/__test/process-knowledge",
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(processed.status()).toBe(200);
  expect((await processed.json()).processed).toBe(true);
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  const approved = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) })
    .filter({
      has: page.getByRole("button", { name: "Remove from retrieval" }),
    });
  await expect(approved).toContainText("succeeded");
  page.once("dialog", (dialog) => dialog.accept());
  await approved.getByRole("button", { name: "Remove from retrieval" }).click();
  await expect(
    page.getByText("Removed from retrieval.", { exact: true }),
  ).toBeVisible();
});
