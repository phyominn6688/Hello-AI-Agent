/**
 * Auth abstraction — uses Amplify Cognito in prod, mock-auth in dev.
 * Components import from here, never directly from aws-amplify.
 */
export interface AuthUser {
  email: string;
  name?: string;
  picture?: string;
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  if (process.env.NEXT_PUBLIC_AUTH_MODE === "mock") {
    return _getMockUser();
  }
  try {
    const { getCurrentUser: amplifyGetCurrentUser } = await import("aws-amplify/auth");
    const { fetchUserAttributes } = await import("aws-amplify/auth");
    await amplifyGetCurrentUser(); // throws if not signed in
    const attrs = await fetchUserAttributes();
    return {
      email: attrs.email ?? "",
      name: attrs.name,
      picture: attrs.picture,
    };
  } catch {
    return null;
  }
}

export async function signIn(): Promise<void> {
  if (process.env.NEXT_PUBLIC_AUTH_MODE === "mock") {
    _setMockUser({ email: "dev@localhost", name: "Dev User" });
    window.location.reload();
    return;
  }
  const { signInWithRedirect } = await import("aws-amplify/auth");
  await signInWithRedirect({ provider: "Google" });
}

export async function signOut(): Promise<void> {
  if (process.env.NEXT_PUBLIC_AUTH_MODE === "mock") {
    localStorage.removeItem("mock_user");
    localStorage.removeItem("mock_token");
    window.location.reload();
    return;
  }
  const { signOut: amplifySignOut } = await import("aws-amplify/auth");
  await amplifySignOut();
}

function _getMockUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem("mock_user");
  if (!stored) return null;
  return JSON.parse(stored);
}

function _setMockUser(user: AuthUser): void {
  localStorage.setItem("mock_user", JSON.stringify(user));
  // Set a mock JWT (the mock-auth service issues real RS256 JWTs)
  // In dev, the user logs in via the mock-auth UI which sets this
  localStorage.setItem("mock_token", "mock-jwt-placeholder");
}
