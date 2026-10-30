import { expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

export const api = "http://127.0.0.1:8000/api/v1";
export const origin = "http://127.0.0.1:4173";
const password = process.env.E2E_TEST_PASSWORD;
if (!password)
  throw new Error(
    "E2E_TEST_PASSWORD is required for the disposable test environment.",
  );
export const pass = password;
export const newEmail = () => `learner-${randomUUID()}@example.com`;

export async function create(page: Page) {
  const email = newEmail();
  const response = await page.request.post(`${api}/auth/register`, {
    headers: { Origin: origin },
    data: { full_name: "Test Learner", email, password: pass },
  });
  expect(response.status()).toBe(201);
  return email;
}
export async function login(page: Page, email: string, value = pass) {
  await page.goto("/login");
  await page.getByLabel("Email address", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(value);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}
export async function menu(page: Page) {
  const toggle = page.getByRole("button", { name: /^Menu/ });
  if (await toggle.isVisible()) await toggle.click();
}
export async function signout(page: Page) {
  await menu(page);
  await page.getByRole("button", { name: "Sign out on all devices" }).click();
  await expect(page).toHaveURL("/login");
}
