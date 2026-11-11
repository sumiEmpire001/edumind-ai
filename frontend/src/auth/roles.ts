import type { Role } from "./session";

export function canAccessKnowledgeApi(role?: Role) {
  return role === "contributor" || role === "admin";
}

export const roleLabels: Record<Role, string> = {
  student: "Student",
  contributor: "Contributor",
  admin: "Administrator",
};
