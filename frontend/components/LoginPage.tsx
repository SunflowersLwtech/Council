"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const { signInAnonymously, signInWithEmail, signUp, loading } = useAuth();
  const [showEmail, setShowEmail] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnonymous = async () => {
    setError(null);
    try {
      await signInAnonymously();
    } catch {
      // Fallback: anonymous sign-in disabled — create guest via backend admin API
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
        const resp = await fetch(`${apiBase}/api/auth/guest`, { method: "POST" });
        if (!resp.ok) throw new Error("Failed to create guest account");
        const { email, password } = await resp.json();
        await signInWithEmail(email, password);
      } catch (err2) {
        setError(err2 instanceof Error ? err2.message : "Failed to sign in");
      }
    }
  };

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      if (isSignUp) {
        await signUp(email, password);
      } else {
        await signInWithEmail(email, password);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <h1 className="login-title welcome-gradient-text">COUNCIL</h1>
          <p className="login-subtitle">
            An AI-powered social deduction game
          </p>
        </div>

        <div className="login-actions">
          <button
            className="demo-btn login-anon-btn"
            onClick={handleAnonymous}
            disabled={loading}
          >
            {loading ? "Signing in..." : "Play as Guest"}
          </button>

          <div className="login-divider">
            <span>or</span>
          </div>

          {!showEmail ? (
            <button
              className="demo-btn demo-btn-secondary"
              onClick={() => setShowEmail(true)}
            >
              Sign in with Email
            </button>
          ) : (
            <form onSubmit={handleEmailAuth} className="login-email-form">
              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="login-input"
                required
              />
              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="login-input"
                required
                minLength={6}
              />
              <button
                type="submit"
                className="demo-btn"
                disabled={loading}
              >
                {loading
                  ? "..."
                  : isSignUp
                  ? "Create Account"
                  : "Sign In"}
              </button>
              <button
                type="button"
                className="login-toggle"
                onClick={() => setIsSignUp(!isSignUp)}
              >
                {isSignUp
                  ? "Already have an account? Sign in"
                  : "Need an account? Sign up"}
              </button>
            </form>
          )}
        </div>

        {error && <p className="login-error">{error}</p>}
      </div>

      <style jsx>{`
        .login-page {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #060612;
          padding: 1rem;
        }
        .login-container {
          max-width: 380px;
          width: 100%;
          display: flex;
          flex-direction: column;
          gap: 2rem;
        }
        .login-header {
          text-align: center;
        }
        .login-title {
          font-size: 2.5rem;
          font-weight: 700;
          letter-spacing: 0.15em;
          margin-bottom: 0.5rem;
        }
        .login-subtitle {
          color: #888;
          font-size: 0.875rem;
        }
        .login-actions {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .login-anon-btn {
          width: 100%;
          padding: 0.75rem 1.5rem;
          font-size: 1rem;
        }
        .login-divider {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          color: #555;
          font-size: 0.8rem;
        }
        .login-divider::before,
        .login-divider::after {
          content: "";
          flex: 1;
          height: 1px;
          background: #333;
        }
        .login-email-form {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .login-input {
          width: 100%;
          padding: 0.6rem 0.75rem;
          border: 1px solid #333;
          border-radius: 6px;
          background: #111;
          color: #eee;
          font-size: 0.875rem;
          outline: none;
        }
        .login-input:focus {
          border-color: #666;
        }
        .login-toggle {
          background: none;
          border: none;
          color: #888;
          font-size: 0.8rem;
          cursor: pointer;
          text-align: center;
        }
        .login-toggle:hover {
          color: #bbb;
        }
        .login-error {
          color: #ef4444;
          font-size: 0.8rem;
          text-align: center;
        }
      `}</style>
    </div>
  );
}
