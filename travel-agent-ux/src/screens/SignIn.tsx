import { useState } from "react";
import { signIn } from "../lib/auth";

interface Props {
  onSignedIn: () => void;
}

export default function SignIn({ onSignedIn }: Props) {
  const [loading, setLoading] = useState(false);

  const handleSignIn = async () => {
    setLoading(true);
    try {
      await signIn();
      // In mock mode signIn() reloads the page; in prod it redirects.
      // After Cognito redirect comes back, App.tsx re-checks getCurrentUser.
      onSignedIn();
    } catch (err) {
      console.error("Sign in failed:", err);
      setLoading(false);
    }
  };

  return (
    <div className="signin">
      <div className="signin-icon">✈</div>
      <h1>Travel AI</h1>
      <p>Your AI-powered travel planning companion. Plan smarter, travel better.</p>
      <button
        className="btn-signin"
        onClick={handleSignIn}
        disabled={loading}
      >
        <span>G</span>
        <span>{loading ? "Signing in…" : "Continue with Google"}</span>
      </button>
    </div>
  );
}
