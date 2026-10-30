import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { create, login } from "./helpers";

test("drafts, expands, edits, reloads and exports a document", async ({
  page,
}) => {
  const email = await create(page);
  await login(page, email);
  await expect(page).toHaveURL("/app");
  await page.goto("/app/studio");
  await page
    .getByLabel("Document title", { exact: true })
    .fill("Mechanics study report");
  await page
    .getByLabel("What should this report cover?", { exact: true })
    .fill(
      "Teach Newtonian mechanics with clear worked examples and explanations.",
    );
  await page.getByLabel("Target length", { exact: true }).selectOption("35");
  await page
    .getByLabel("Outline · one section heading per line", { exact: true })
    .fill("Introduction\nAnalysis\nConclusion");
  await page
    .getByRole("button", { name: "Create document", exact: true })
    .click();
  await expect(page).toHaveURL(/\/app\/studio\/[0-9a-f-]+$/);
  await page
    .getByRole("button", { name: "Draft remaining sections", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Drafting finished");
  await expect(
    page.getByRole("button", { name: /3\. Conclusion/ }),
  ).toContainText("Drafted");
  const original = await page
    .getByLabel("Section text", { exact: true })
    .inputValue();
  await page
    .getByRole("button", { name: "Expand selected section", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Drafting finished");
  await expect(
    page.getByLabel("Section text", { exact: true }),
  ).not.toHaveValue(original);
  await page
    .getByLabel("Section text", { exact: true })
    .fill(
      "# Edited conclusion\nForce is mass times acceleration. Verify all calculations.",
    );
  await page.getByRole("button", { name: "Save section", exact: true }).click();
  await expect(page.getByText("Section saved.", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /3\. Conclusion/ }).click();
  await expect(page.getByLabel("Section text", { exact: true })).toHaveValue(
    /Force is mass/,
  );
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF", exact: true }).click();
  const file = await downloaded;
  const path = await file.path();
  expect(path).toBeTruthy();
  expect((await readFile(path!)).subarray(0, 5).toString()).toBe("%PDF-");
  await expect(page.getByRole("status")).toContainText("actual pages");
});

test("attaches an image to chat and downloads the answer PDF", async ({
  page,
}) => {
  const email = await create(page);
  await login(page, email);
  await expect(page).toHaveURL("/app");
  await page.goto("/app/chat");
  await page.getByRole("button", { name: /Create a conversation/ }).click();
  await expect(page).toHaveURL(/\/app\/chat\/[0-9a-f-]+$/);
  const upload = page.getByLabel("Attach an image or text note", {
    exact: true,
  });
  await expect(upload).toBeEnabled();
  await upload.setInputFiles({
    name: "exercise.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAGElEQVR4nGNkaGAgCTCRpnxUw6iGoaQBALsfAKDg6Y6zAAAAAElFTkSuQmCC",
      "base64",
    ),
  });
  await expect(
    page.getByRole("button", { name: "Remove attachment exercise.png" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Your question", exact: true })
    .fill("Explain the image step by step.");
  await page.getByRole("button", { name: /Send question/ }).click();
  await expect(
    page
      .getByRole("article", { name: "Your question" })
      .getByText("exercise.png", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download answer PDF", exact: true }),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download answer PDF", exact: true })
    .click();
  const file = await downloaded;
  expect((await readFile((await file.path())!)).subarray(0, 5).toString()).toBe(
    "%PDF-",
  );
  await page.reload();
  await expect(
    page
      .getByRole("article", { name: "Your question" })
      .getByText("exercise.png", { exact: true }),
  ).toBeVisible();
});
