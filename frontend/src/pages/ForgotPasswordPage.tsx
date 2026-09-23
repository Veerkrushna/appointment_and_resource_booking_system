import { useState, useEffect, useRef } from "react";
import type { FormEvent, KeyboardEvent, ClipboardEvent } from "react";
import { useNavigate } from "react-router-dom";

type Step = "request" | "verify" | "confirm";

function passwordScore(value: string) {
  return [
    value.length >= 8,
    /[A-Z]/.test(value),
    /\d/.test(value),
    /[^A-Za-z0-9]/.test(value),
  ].filter(Boolean).length;
}

function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("request");
  
  // Step 1 state
  const [email, setEmail] = useState("");
  
  // Step 2 state
  const [pin, setPin] = useState<string[]>(Array(6).fill(""));
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const [cooldown, setCooldown] = useState(0);
  
  // Step 3 state
  const [resetToken, setResetToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  
  // Generic state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let timer: number;
    if (cooldown > 0) {
      timer = window.setInterval(() => setCooldown((c) => c - 1), 1000);
    }
    return () => window.clearInterval(timer);
  }, [cooldown]);

  async function handleRequest(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setIsSubmitting(true);
    try {
      const res = await fetch("/api/password-reset/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to request code");
      setMessage(data.message);
      setStep("verify");
      setCooldown(60);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleVerify(e: FormEvent) {
    e.preventDefault();
    const fullPin = pin.join("");
    if (fullPin.length !== 6) {
      setError("Please enter the 6-digit code.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const res = await fetch("/api/password-reset/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, pin: fullPin }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Invalid or expired code");
      setResetToken(data.reset_token);
      setStep("confirm");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleConfirm(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (passwordScore(password) < 2) {
      setError("Please choose a stronger password.");
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await fetch("/api/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset_token: resetToken, new_password: password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to reset password");
      navigate("/login", { state: { message: "Password updated successfully. Please log in." } });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handlePinChange(index: number, val: string) {
    const newPin = [...pin];
    newPin[index] = val;
    setPin(newPin);
    if (val && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  }

  function handlePinKeyDown(index: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !pin[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  }

  function handlePinPaste(e: ClipboardEvent<HTMLInputElement>) {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted) {
      const newPin = [...pin];
      for (let i = 0; i < pasted.length; i++) {
        newPin[i] = pasted[i];
      }
      setPin(newPin);
      const nextFocus = Math.min(pasted.length, 5);
      inputRefs.current[nextFocus]?.focus();
    }
  }

  const score = passwordScore(password);

  return (
    <main className="auth-page">
      <section className="auth-shell">
        <div className="auth-form-side" style={{ margin: "0 auto", borderRight: "none" }}>
          <div className="auth-brand" style={{ cursor: "pointer" }} onClick={() => navigate("/login")}>
            <span>← Back to login</span>
          </div>
          <div className="auth-form-content">
            <div className="auth-heading">
              <h1>Reset your password</h1>
              <p>Follow the steps to regain access to your account.</p>
            </div>

            {error && <p className="auth-error" role="alert">{error}</p>}
            {message && <p className="auth-error" style={{ background: "#e6f4ea", color: "#1e8e3e" }} role="status">{message}</p>}

            {step === "request" && (
              <form className="auth-form" onSubmit={handleRequest} noValidate>
                <label className="auth-field">
                  <span>Email address</span>
                  <input
                    autoComplete="email"
                    required
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                  />
                </label>
                <button className="auth-submit" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Sending..." : "Send Reset Code"}
                </button>
              </form>
            )}

            {step === "verify" && (
              <form className="auth-form" onSubmit={handleVerify} noValidate>
                <div className="auth-field">
                  <span>Enter 6-digit code sent to {email}</span>
                  <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
                    {pin.map((digit, index) => (
                      <input
                        key={index}
                        ref={(el) => (inputRefs.current[index] = el)}
                        type="text"
                        inputMode="numeric"
                        pattern="\d*"
                        maxLength={1}
                        value={digit}
                        onChange={(e) => handlePinChange(index, e.target.value.replace(/\D/g, ""))}
                        onKeyDown={(e) => handlePinKeyDown(index, e)}
                        onPaste={handlePinPaste}
                        style={{ width: "3rem", height: "3rem", textAlign: "center", fontSize: "1.5rem" }}
                      />
                    ))}
                  </div>
                </div>
                <button className="auth-submit" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Verifying..." : "Verify Code"}
                </button>
                <p className="auth-footer" style={{ marginTop: "1rem" }}>
                  Didn't receive a code?{" "}
                  <button
                    type="button"
                    disabled={cooldown > 0}
                    onClick={handleRequest}
                  >
                    {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
                  </button>
                </p>
              </form>
            )}

            {step === "confirm" && (
              <form className="auth-form" onSubmit={handleConfirm} noValidate>
                <label className="auth-field">
                  <span>New Password</span>
                  <div className="auth-input-wrap">
                    <input
                      autoComplete="new-password"
                      required
                      minLength={8}
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="At least 8 characters"
                    />
                    <button
                      className="password-toggle"
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                    >
                      {showPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                  {password && (
                    <div className="password-meter" aria-live="polite">
                      <div className="password-meter__bars">
                        {[1, 2, 3, 4].map((bar) => (
                          <i className={bar <= score ? `is-level-${score}` : ""} key={bar} />
                        ))}
                      </div>
                      <span>
                        {score < 2
                          ? "Needs more strength"
                          : score < 4
                          ? "Good password"
                          : "Strong password"}
                      </span>
                    </div>
                  )}
                </label>
                <label className="auth-field">
                  <span>Confirm New Password</span>
                  <div className="auth-input-wrap">
                    <input
                      autoComplete="new-password"
                      required
                      minLength={8}
                      type={showPassword ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Re-enter your password"
                    />
                  </div>
                </label>
                <button className="auth-submit" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Updating..." : "Set New Password"}
                </button>
              </form>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

export default ForgotPasswordPage;
