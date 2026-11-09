import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("admin opens a readable dashboard and researches a LAUTECH question", async ({ page }) => {
  await login(page, "admin-e2e@example.com");
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/admin");
  await expect(page.getByRole("heading", { name: "Admin workspace" })).toBeVisible();
  await expect(page.getByText("Registered users")).toBeVisible();
  await expect(page.getByText("Unavailable")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);

  await page.route("**/api/v1/research", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: { enabled: true } });
    expect(route.request().postDataJSON().question).toContain("LAUTECH");
    return route.fulfill({
      json: {
        answer: "An evidence-backed research example.",
        sources: [{ title: "Fixture source", url: "https://example.org/lautech" }],
        suggestions: [],
      },
    });
  });
  await page.getByRole("link", { name: /LAUTECH research/ }).click();
  await expect(page.getByRole("heading", { name: "Web research" })).toBeVisible();
  await page.getByRole("button", { name: "Search the web" }).click();
  await expect(page.getByRole("link", { name: "Fixture source" }))
    .toHaveAttribute("href", "https://example.org/lautech");
  await expect(page.getByRole("button", { name: "Save research draft for review" })).toBeVisible();
});

test("research stays unavailable when the deployment disables grounding", async ({ page }) => {
  await login(page, "admin-e2e@example.com");
  await expect(page).toHaveURL(/\/app$/);
  const availability = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/research" &&
    response.request().method() === "GET"
  );
  await page.goto("/app/research?topic=lautech");
  const response = await availability;
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({ enabled: false });
  await expect(page.getByRole("status").filter({ hasText: "Live search is disabled" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Search the web" })).toBeDisabled();
  await expect(page.getByRole("link", { name: "Search reviewed answers in the Knowledge API" }))
    .toHaveAttribute("href", "/app/learning");
});
