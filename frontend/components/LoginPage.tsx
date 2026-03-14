"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const { signInAnonymously, signInWithEmail, signInWithGoogle, signUp, loading } = useAuth();
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

          <button
            className="demo-btn login-google-btn"
            onClick={() => {
              setError(null);
              signInWithGoogle().catch((err: unknown) =>
                setError(err instanceof Error ? err.message : "Google sign-in failed")
              );
            }}
            disabled={loading}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" style={{ marginRight: 8, verticalAlign: "middle" }}>
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Sign in with Google
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
        .login-google-btn {
          width: 100%;
          padding: 0.65rem 1.5rem;
          font-size: 0.9rem;
          background: #fff;
          color: #333;
          border: 1px solid #ddd;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .login-google-btn:hover {
          background: #f5f5f5;
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
