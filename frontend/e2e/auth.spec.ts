import { test, expect } from "@playwright/test";
import { newEmail, pass, create, login, menu, signout } from "./helpers";

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => {
    throw new Error(`Browser JavaScript failed: ${error.name}`);
  });
});
test("registers, signs in, restores cookies, coordinates tabs and revokes logout", async ({
  page,
  context,
}) => {
  const email = newEmail();
  await page.goto("/app/account");
  await expect(page).toHaveURL("/login");
  await page.goto("/register");
  await page.getByLabel("Full name", { exact: true }).fill("Test Learner");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(pass);
  await page.getByLabel("Confirm password", { exact: true }).fill(pass);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.getByRole("status")).toHaveText(
    "Account created. Sign in to enter your workspace.",
  );
  await expect(page.getByLabel("Email address")).toHaveValue(email);
  await page.getByLabel("Password", { exact: true }).fill(pass);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Hello, Test." }),
  ).toBeVisible();
  await page.goto("/app/account");
  await expect(
    page.getByRole("heading", { name: "Account details" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Account details" }),
  ).toBeVisible();
  const second = await context.newPage();
  await second.goto("/app");
  await expect(
    second.getByRole("heading", { name: "Hello, Test." }),
  ).toBeVisible();
  await Promise.all([page.reload(), second.reload()]);
  await expect(
    page.getByRole("heading", { name: "Account details" }),
  ).toBeVisible();
  await expect(
    second.getByRole("heading", { name: "Hello, Test." }),
  ).toBeVisible();
  const storage = await page.evaluate(() => ({
    local: Object.keys(localStorage),
    session: Object.keys(sessionStorage),
  }));
  expect(storage).toEqual({ local: [], session: [] });
  await signout(page);
  await expect(second).toHaveURL("/login");
  await page.goto("/app");
  await expect(page).toHaveURL("/login");
});

test("handles an incorrect password then a successful sign-in", async ({
  page,
}) => {
  const email = await create(page);
  await login(page, email, "an incorrect passphrase");
  await expect(page.getByRole("alert")).toHaveText(
    "Incorrect email or password.",
  );
  await page.getByLabel("Password", { exact: true }).fill(pass);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("/app");
});

test("validates forms, toggles password visibility and supports mobile navigation", async ({
  page,
}) => {
  await page.goto("/register");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.getByRole("alert")).toHaveText(
    "Check the highlighted fields.",
  );
  await expect(page.getByText("Use at least 15 characters.")).toBeVisible();
  const field = page.getByLabel("Password", { exact: true });
  await page
    .getByRole("button", { name: "Show password", exact: true })
    .click();
  await expect(field).toHaveAttribute("type", "text");
  await page
    .getByRole("button", { name: "Hide password", exact: true })
    .click();
  await expect(field).toHaveAttribute("type", "password");
  await menu(page);
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Sign in", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  expect(overflow).toBe(false);
});

test("changes a password and requires the new credentials", async ({
  page,
}) => {
  const email = await create(page);
  await login(page, email);
  await expect(page).toHaveURL("/app");
  await menu(page);
  await page.getByRole("link", { name: "My account", exact: true }).click();
  await page.getByLabel("Current password", { exact: true }).fill(pass);
  await page
    .getByLabel("New password", { exact: true })
    .fill(pass + "-updated");
  await page
    .getByLabel("Confirm new password", { exact: true })
    .fill(pass + "-updated");
  await page
    .getByRole("button", { name: "Change password", exact: true })
    .click();
  await expect(page).toHaveURL("/login");
  await expect(page.getByRole("status")).toHaveText(
    "Password changed. Sign in again with your new password.",
  );
  await login(page, email);
  await expect(page.getByRole("alert")).toHaveText(
    "Incorrect email or password.",
  );
  await page.getByLabel("Password", { exact: true }).fill(pass + "-updated");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("/app");
});

test("shows a service failure without pretending logout succeeded", async ({
  page,
}) => {
  const email = await create(page);
  await login(page, email);
  await expect(page).toHaveURL("/app");
  await page.route("**/api/v1/auth/logout-all", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: '{"detail":"temporary failure"}',
    }),
  );
  await menu(page);
  await page.getByRole("button", { name: "Sign out on all devices" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "EduMind is temporarily unavailable. Please try again.",
  );
  await expect(page).toHaveURL("/app");
  await page.unroute("**/api/v1/auth/logout-all");
  await page.getByRole("button", { name: "Sign out on all devices" }).click();
  await expect(page).toHaveURL("/login");
});

for (const [email, role] of [
  ["contributor-e2e@example.com", "Contributor"],
  ["admin-e2e@example.com", "Administrator"],
]) {
  test(`renders the server-confirmed ${role.toLowerCase()} account`, async ({
    page,
  }) => {
    await login(page, email);
    await expect(page).toHaveURL("/app");
    await expect(
      page.locator("main").getByText(role, { exact: true }),
    ).toBeVisible();
    await menu(page);
    await page.getByRole("link", { name: "My account", exact: true }).click();
    await expect(page.getByText(email, { exact: true })).toBeVisible();
    await expect(page.getByText(role, { exact: true }).last()).toBeVisible();
  });
}
