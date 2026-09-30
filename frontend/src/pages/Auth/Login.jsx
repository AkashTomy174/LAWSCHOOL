import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Button, Callout, Panel, TextField } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { fieldErrorsFrom, validateLogin } from "../../utils/validation";

/**
 * Sign-in page.
 *
 * Error handling has three layers, deliberately:
 *  1. local validation for obvious mistakes (fast feedback, no round trip);
 *  2. field-level errors mapped from the server's `details` payload;
 *  3. a general message for anything unattributable to a field.
 *
 * The backend returns the same response for "unknown email" and "wrong password",
 * so the UI must not speculate about which was wrong.
 */
export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [form, setForm] = useState({ email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [generalError, setGeneralError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      setErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setGeneralError(null);

    const { valid, errors: localErrors } = validateLogin(form);
    if (!valid) {
      setErrors(localErrors);
      return;
    }

    setSubmitting(true);
    try {
      await login(form);
      // Return the student to wherever the guard intercepted them.
      navigate(location.state?.from || "/dashboard", { replace: true });
    } catch (caught) {
      const mapped = fieldErrorsFrom(caught);
      if (Object.keys(mapped).length) {
        setErrors(mapped);
        if (mapped.non_field_errors) setGeneralError(mapped.non_field_errors);
      } else {
        setGeneralError(caught?.message || "Sign-in failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-md px-4 py-12">
      <Panel className="p-6 sm:p-8">
        <h1 className="font-display text-2xl text-parchment">Welcome back</h1>
        <p className="mt-2 text-sm text-white/55">
          Sign in to continue your coursework.
        </p>

        <div className="gold-rule my-6" />

        {generalError && (
          <div className="mb-5">
            <Callout tone="danger">{generalError}</Callout>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <TextField
            id="email"
            label="Email address"
            type="email"
            autoComplete="email"
            inputMode="email"
            required
            value={form.email}
            onChange={update("email")}
            error={errors.email}
            placeholder="you@example.com"
          />

          <TextField
            id="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            value={form.password}
            onChange={update("password")}
            error={errors.password}
            placeholder="Your password"
          />

          <div className="flex items-center justify-between text-sm">
            <Link
              to="/forgot-password"
              className="text-gold-300 hover:underline"
            >
              Forgot password?
            </Link>
          </div>

          <Button type="submit" loading={submitting} className="w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-white/55">
          New to LawSchool?{" "}
          <Link to="/register" className="text-gold-300 hover:underline">
            Create an account
          </Link>
        </p>
      </Panel>
    </div>
  );
}
