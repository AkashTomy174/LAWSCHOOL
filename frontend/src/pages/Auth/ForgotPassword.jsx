import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  Button,
  Callout,
  EmptyState,
  Panel,
  TextField,
} from "../../components/ui";
import { authService } from "../../services/authService";
import { useUI } from "../../context/UIContext";

/**
 * Password reset flow — two screens in one route.
 *
 * `?uid=&token=` present → the confirm step (arrived from the email link).
 * Otherwise            → the request step.
 *
 * The request step always reports success, matching the backend's
 * non-enumerating behaviour: a student cannot use this page to discover whether an
 * email is registered.
 */
export default function ForgotPassword() {
  const [searchParams] = useSearchParams();
  const { pushToast } = useUI();

  const uid = searchParams.get("uid");
  const token = searchParams.get("token");
  const isConfirmStep = Boolean(uid && token);

  const [email, setEmail] = useState("");
  const [passwords, setPasswords] = useState({
    newPassword: "",
    newPasswordConfirm: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});

  async function requestReset(event) {
    event.preventDefault();
    setError(null);

    if (!email.trim()) {
      setFieldErrors({ email: "Enter your email address." });
      return;
    }

    setSubmitting(true);
    try {
      await authService.requestPasswordReset(email);
      setDone(true);
    } catch (caught) {
      // Even a server failure is reported vaguely: the endpoint must not become an
      // account-existence oracle.
      setError(
        caught?.message || "Could not send the reset link. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmReset(event) {
    event.preventDefault();
    setError(null);

    const errors = {};
    if (passwords.newPassword.length < 10) {
      errors.newPassword = "Use at least 10 characters.";
    }
    if (passwords.newPassword !== passwords.newPasswordConfirm) {
      errors.newPasswordConfirm = "Passwords do not match.";
    }
    if (Object.keys(errors).length) {
      setFieldErrors(errors);
      return;
    }

    setSubmitting(true);
    try {
      await authService.confirmPasswordReset({
        uid,
        token,
        newPassword: passwords.newPassword,
        newPasswordConfirm: passwords.newPasswordConfirm,
      });
      setDone(true);
      pushToast({
        message: "Password updated. You can sign in now.",
        tone: "success",
      });
    } catch (caught) {
      setError(caught?.message || "This reset link is invalid or has expired.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-md px-4 py-12">
      <Panel className="p-6 sm:p-8">
        {done ? (
          <EmptyState
            title={isConfirmStep ? "Password updated" : "Check your inbox"}
            description={
              isConfirmStep
                ? "Your password has been changed and all other sessions were signed out."
                : "If an account exists for that email, we have sent a reset link. It expires shortly."
            }
            action={
              <Link to="/login" className="btn btn-primary">
                Back to sign in
              </Link>
            }
          />
        ) : (
          <>
            <h1 className="font-display text-2xl text-parchment">
              {isConfirmStep ? "Choose a new password" : "Reset your password"}
            </h1>
            <p className="mt-2 text-sm text-white/55">
              {isConfirmStep
                ? "Pick a strong password you have not used before."
                : "Enter your account email and we will send you a reset link."}
            </p>

            <div className="gold-rule my-6" />

            {error && (
              <div className="mb-5">
                <Callout tone="danger">{error}</Callout>
              </div>
            )}

            {isConfirmStep ? (
              <form onSubmit={confirmReset} noValidate className="space-y-4">
                <TextField
                  id="new-password"
                  label="New password"
                  type="password"
                  autoComplete="new-password"
                  value={passwords.newPassword}
                  onChange={(event) =>
                    setPasswords((current) => ({
                      ...current,
                      newPassword: event.target.value,
                    }))
                  }
                  error={fieldErrors.newPassword}
                  hint="At least 10 characters with letters and numbers."
                />
                <TextField
                  id="confirm-new-password"
                  label="Confirm new password"
                  type="password"
                  autoComplete="new-password"
                  value={passwords.newPasswordConfirm}
                  onChange={(event) =>
                    setPasswords((current) => ({
                      ...current,
                      newPasswordConfirm: event.target.value,
                    }))
                  }
                  error={fieldErrors.newPasswordConfirm}
                />
                <Button type="submit" loading={submitting} className="w-full">
                  Set new password
                </Button>
              </form>
            ) : (
              <form onSubmit={requestReset} noValidate className="space-y-4">
                <TextField
                  id="reset-email"
                  label="Email address"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setFieldErrors({});
                  }}
                  error={fieldErrors.email}
                  placeholder="you@example.com"
                />
                <Button type="submit" loading={submitting} className="w-full">
                  Send reset link
                </Button>
              </form>
            )}

            <p className="mt-6 text-center text-sm text-white/55">
              Remembered it?{" "}
              <Link to="/login" className="text-gold-300 hover:underline">
                Sign in
              </Link>
            </p>
          </>
        )}
      </Panel>
    </div>
  );
}

/** Email verification landing page (link from the verification email). */
export function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const [state, setState] = useState("pending");
  const [error, setError] = useState(null);

  const uid = searchParams.get("uid");
  const token = searchParams.get("token");

  async function verify() {
    setState("working");
    try {
      await authService.verifyEmail({ uid, token });
      setState("done");
    } catch (caught) {
      setError(
        caught?.message || "This verification link is invalid or has expired.",
      );
      setState("error");
    }
  }

  // Auto-verify on arrival: the student already clicked the link, so asking for a
  // second click is pointless friction.
  useState(() => {
    if (uid && token) verify();
  });

  return (
    <div className="mx-auto w-full max-w-md px-4 py-12">
      <Panel className="p-6 sm:p-8">
        {state === "done" ? (
          <EmptyState
            title="Email verified"
            description="Your account is fully set up."
            action={
              <Link to="/dashboard" className="btn btn-primary">
                Go to dashboard
              </Link>
            }
          />
        ) : state === "error" ? (
          <EmptyState
            icon="lock"
            title="Verification failed"
            description={error}
            action={
              <Link to="/profile" className="btn btn-ghost">
                Open profile
              </Link>
            }
          />
        ) : (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <p className="text-sm text-white/65">
              Verifying your email address…
            </p>
          </div>
        )}
      </Panel>
    </div>
  );
}

/** 404 page. */
export function NotFound() {
  return (
    <div className="mx-auto w-full max-w-lg px-4 py-20">
      <Panel className="p-8 text-center">
        <p
          className="font-display text-5xl text-gold-500/50"
          aria-hidden="true"
        >
          404
        </p>
        <h1 className="mt-4 font-display text-2xl text-parchment">
          Page not found
        </h1>
        <p className="mt-3 text-sm text-white/60">
          The page you were looking for does not exist or has moved.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link to="/" className="btn btn-primary">
            Back to home
          </Link>
          <Link to="/courses" className="btn btn-ghost">
            Browse courses
          </Link>
        </div>
      </Panel>
    </div>
  );
}
