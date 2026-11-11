import { expect, test } from "@playwright/test";
import { login, menu } from "./helpers";

test("legacy research links open Study Chat and the admin dashboard has no research page", async ({ page }) => {
  await login(page, "admin-e2e@example.com");
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/admin");
  await expect(page.getByRole("heading", { name: "Admin workspace" })).toBeVisible();
  await expect(page.getByText("Registered users")).toBeVisible();
  await menu(page);
  await expect(page.getByRole("link", { name: /research/i })).toHaveCount(0);
  await page.goto("/app/research?topic=lautech");
  await expect(page).toHaveURL(/\/app\/chat$/);
});
