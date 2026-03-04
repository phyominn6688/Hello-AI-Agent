/**
 * Auth abstraction — uses Amplify Cognito in prod, localStorage mock in dev.
 * VITE_AUTH_MODE=mock enables mock auth (no Cognito required).
 */

export interface AuthUser {
  email: string;
  name?: string;
  picture?: string;
}

const IS_MOCK = import.meta.env.VITE_AUTH_MODE === "mock";

export async function getCurrentUser(): Promise<AuthUser | null> {
  if (IS_MOCK) return _getMockUser();
  try {
    const { getCurrentUser: amplifyGetCurrentUser, fetchUserAttributes } =
      await import("aws-amplify/auth");
    await amplifyGetCurrentUser();
    const attrs = await fetchUserAttributes();
    return { email: attrs.email ?? "", name: attrs.name, picture: attrs.picture };
  } catch {
    return null;
  }
}

export async function signIn(): Promise<void> {
  if (IS_MOCK) {
    _setMockUser({ email: "dev@localhost", name: "Dev User" });
    window.location.reload();
    return;
  }
  const { signInWithRedirect } = await import("aws-amplify/auth");
  await signInWithRedirect({ provider: "Google" });
}

export async function signOut(): Promise<void> {
  if (IS_MOCK) {
    localStorage.removeItem("mock_user");
    localStorage.removeItem("mock_token");
    window.location.reload();
    return;
  }
  const { signOut: amplifySignOut } = await import("aws-amplify/auth");
  await amplifySignOut();
}

export async function getAuthHeaders(): Promise<Record<string, string>> {
  if (IS_MOCK) {
    const token = localStorage.getItem("mock_token") ?? "";
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
  try {
    const { fetchAuthSession } = await import("aws-amplify/auth");
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {
    // ignore
  }
  return {};
}

function _getMockUser(): AuthUser | null {
  const stored = localStorage.getItem("mock_user");
  if (!stored) return null;
  return JSON.parse(stored) as AuthUser;
}

function _setMockUser(user: AuthUser): void {
  localStorage.setItem("mock_user", JSON.stringify(user));
  localStorage.setItem("mock_token", "mock-jwt-placeholder");
}
