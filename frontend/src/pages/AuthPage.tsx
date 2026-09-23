import { useState, useEffect } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate, Link } from "react-router-dom";

import { useAuth } from "../auth/useAuth";

type Mode = "login" | "register";

function Icon({ name }: { name: "calendar" | "check" | "clock" | "eye" | "eye-off" | "google" | "apple" }) {
  if (name === "google") return <span className="oauth-icon oauth-icon--google" aria-hidden="true">G</span>;
  if (name === "apple") return <span className="oauth-icon oauth-icon--apple" aria-hidden="true">●</span>;
  const paths = {
    calendar: <><rect x="3" y="4.5" width="18" height="16" rx="2" /><path d="M7 2.5v4M17 2.5v4M3 9.5h18" /></>,
    check: <path d="m5 12 4.2 4L19 6.5" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    eye: <><path d="M2.5 12s3.5-5 9.5-5 9.5 5 9.5 5-3.5 5-9.5 5-9.5-5-9.5-5Z" /><circle cx="12" cy="12" r="2.2" /></>,
    "eye-off": <><path d="m3 3 18 18M10.6 6.9A10.8 10.8 0 0 1 12 6.8c6 0 9.5 5.2 9.5 5.2a17 17 0 0 1-3.2 3.4M6.1 6.2C3.8 7.7 2.5 12 2.5 12s3.5 5.2 9.5 5.2a10 10 0 0 0 2.5-.3" /></>,
  };
  return <svg className="auth-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function passwordScore(value: string) {
  return [value.length >= 8, /[A-Z]/.test(value), /\d/.test(value), /[^A-Za-z0-9]/.test(value)].filter(Boolean).length;
}

function AuthPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>(location.pathname === "/register" ? "register" : "login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(
    location.state?.message || null
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setName("");
    setEmail("");
    setPhone("");
    setPassword("");
    setConfirmPassword("");
    setValidationError(null);
    setError(null);
    setSuccessMessage(null);
  }, [mode, location.pathname]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setValidationError(null);
    if (mode === "register") {
      if (password !== confirmPassword) { setValidationError("Passwords do not match."); return; }
      if (!acceptedTerms) { setValidationError("Please agree to the Terms of Service and Privacy Policy."); return; }
    }
    setIsSubmitting(true);
    try { if (mode === "login") await login(email, password); else await register(name, email, password, phone); navigate("/dashboard"); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to authenticate."); }
    finally { setIsSubmitting(false); }
  }

  const score = passwordScore(password);
  const isRegister = mode === "register";

  return <main className="auth-page">
    <section className="auth-shell" aria-labelledby="auth-title">
      <div className="auth-form-side">
        <div className="auth-brand"><span className="auth-brand__mark"><Icon name="calendar" /></span><span>Appointment Booking</span></div>
        <div className="auth-form-content">
          <div className="auth-heading"><p className="auth-kicker">{isRegister ? "Start organizing" : "Welcome back"}</p><h1 id="auth-title">{isRegister ? "Create your account" : "Sign in to your account"}</h1><p>{isRegister ? "Book appointments and manage your schedule in one place." : "Your schedule is ready when you are."}</p></div>
          <div className="auth-switch" role="tablist" aria-label="Authentication options"><button className={isRegister ? "active" : ""} type="button" role="tab" aria-selected={isRegister} onClick={() => setMode("register")}>Create account</button><button className={!isRegister ? "active" : ""} type="button" role="tab" aria-selected={!isRegister} onClick={() => setMode("login")}>Sign in</button></div>
          {successMessage && <p className="auth-error" style={{ background: "#e6f4ea", color: "#1e8e3e", marginBottom: "1rem" }} role="status">{successMessage}</p>}
          {isRegister && <div className="oauth-options"><button className="oauth-button" type="button"><Icon name="google" />Sign up with Google</button><button className="oauth-button" type="button"><Icon name="apple" />Sign up with Apple</button></div>}
          {isRegister && <div className="auth-divider"><span>or continue with email</span></div>}
          <form className="auth-form" onSubmit={submit} noValidate>
            {isRegister && <label className="auth-field"><span>Full name</span><input autoComplete="off" required value={name} onChange={(event) => setName(event.target.value)} placeholder="Alex Morgan" /></label>}
            <label className="auth-field"><span>Email address</span><input autoComplete="off" required type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
            {isRegister && <label className="auth-field"><span>Phone number <em>Optional</em></span><input autoComplete="off" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="(555) 123-4567" /></label>}
            <label className="auth-field"><span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>Password {!isRegister && <Link to="/forgot-password" style={{ fontSize: '0.8rem', color: '#e2784d', textDecoration: 'none' }}>Forgot password?</Link>}</span><div className="auth-input-wrap"><input autoComplete="new-password" required minLength={8} type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" /><button className="password-toggle" type="button" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((visible) => !visible)}><Icon name={showPassword ? "eye-off" : "eye"} /></button></div>{isRegister && password && <div className="password-meter" aria-live="polite"><div className="password-meter__bars">{[1, 2, 3, 4].map((bar) => <i className={bar <= score ? `is-level-${score}` : ""} key={bar} />)}</div><span>{score < 2 ? "Needs more strength" : score < 4 ? "Good password" : "Strong password"}</span></div>}</label>
            {isRegister && <label className="auth-field"><span>Confirm password</span><div className="auth-input-wrap"><input autoComplete="new-password" required minLength={8} type={showPassword ? "text" : "password"} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Re-enter your password" /></div></label>}
            {isRegister && <label className="terms-check"><input type="checkbox" checked={acceptedTerms} onChange={(event) => setAcceptedTerms(event.target.checked)} /><span>I agree to the <a href="/terms">Terms of Service</a> and <a href="/privacy">Privacy Policy</a></span></label>}
            {(validationError || error) && <p className="auth-error" role="alert">{validationError || error}</p>}
            <button className="auth-submit" type="submit" disabled={isSubmitting}>{isSubmitting ? <><span className="auth-spinner" />{isRegister ? "Creating your account..." : "Signing you in..."}</> : isRegister ? "Create Account" : "Sign In"}</button>
          </form>
          <p className="auth-footer">{isRegister ? "Already have an account?" : "New to Appointment Booking?"} <button type="button" onClick={() => setMode(isRegister ? "login" : "register")}>{isRegister ? "Sign In" : "Create an account"}</button></p>
        </div>
      </div>
      <aside className="auth-visual" aria-label="Appointment planning preview"><div className="auth-visual__top"><span className="auth-visual__icon"><Icon name="calendar" /></span><span>Plan with confidence</span></div><div className="auth-visual__copy"><h2>Your time, thoughtfully organized.</h2><p>One clear place for every appointment, provider, and plan.</p></div><div className="schedule-card"><div className="schedule-card__head"><div><small>Monday, October 14</small><strong>Your schedule</strong></div><span>Today</span></div><div className="schedule-item"><span className="schedule-item__time">09:30</span><div className="schedule-item__line schedule-item__line--blue"><strong>Project consultation</strong><small>with Jordan Lee · 45 min</small></div><Icon name="check" /></div><div className="schedule-item"><span className="schedule-item__time">13:00</span><div className="schedule-item__line schedule-item__line--teal"><strong>Design review</strong><small>with Casey Chen · 30 min</small></div><Icon name="clock" /></div><div className="schedule-card__footer"><span><i />3 appointments today</span><span>View calendar <b>↗</b></span></div></div><div className="auth-visual__dots" aria-hidden="true"><i /><i /><i /></div></aside>
    </section>
  </main>;
}

export default AuthPage;
