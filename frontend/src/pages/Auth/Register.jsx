import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import AuthLayout from "../../components/AuthLayout";
import { Button, Callout, Panel, TextField } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import {
  fieldErrorsFrom,
  passwordStrength,
  validateRegistration,
} from "../../utils/validation";

/**
 * Student registration.
 *
 * There is deliberately no role selector: accounts created here are always
 * students. Instructor and admin accounts are provisioned server-side, so a
 * crafted request cannot self-promote.
 */
export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    password: "",
    passwordConfirm: "",
  });
  const [errors, setErrors] = useState({});
  const [generalError, setGeneralError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Live strength feedback while typing the password.
  const strength = useMemo(
    () => passwordStrength(form.password),
    [form.password],
  );

  function update(field) {
    return (event) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
      setErrors((current) => ({ ...current, [field]: undefined }));
    };
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setGeneralError(null);

    const { valid, errors: localErrors } = validateRegistration(form);
    if (!valid) {
      setErrors(localErrors);
      return;
    }

    setSubmitting(true);
    try {
      await register(form);
      // Registration signs the student in, so send them straight to the dashboard.
      navigate("/dashboard", { replace: true });
    } catch (caught) {
      const mapped = fieldErrorsFrom(caught);
      if (Object.keys(mapped).length) {
        setErrors(mapped);
        if (mapped.non_field_errors) setGeneralError(mapped.non_field_errors);
      } else {
        setGeneralError(
          caught?.message || "Registration failed. Please try again.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  const strengthLabels = ["Too weak", "Weak", "Fair", "Good", "Strong"];
  const strengthTones = [
    "bg-bad",
    "bg-bad",
    "bg-gold",
    "bg-ok",
    "bg-ok",
  ];

  return (
    <AuthLayout>
        <h1 className="h2 !text-[38px]">
          Create your account
        </h1>
        <p className="body mt-3">
          Preview lessons for free. Upgrade whenever you are ready.
        </p>

        <div className="h-7" />

        {generalError && (
          <div className="mb-5">
            <Callout tone="danger">{generalError}</Callout>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <TextField
            id="name"
            label="Full name"
            autoComplete="name"
            required
            value={form.name}
            onChange={update("name")}
            error={errors.name}
            placeholder="Rahul Sharma"
          />

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
            hint="We use your email to sign you in — it is never shown on the leaderboard."
          />

          <TextField
            id="phone"
            label="Phone (optional)"
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            value={form.phone}
            onChange={update("phone")}
            error={errors.phone}
            placeholder="+91 98765 43210"
          />

          <div>
            <TextField
              id="password"
              label="Password"
              type="password"
              autoComplete="new-password"
              required
              value={form.password}
              onChange={update("password")}
              error={errors.password}
              aria-describedby="password-strength"
            />

            {form.password && (
              <div id="password-strength" className="mt-2" aria-live="polite">
                <div className="flex gap-1" aria-hidden="true">
                  {[0, 1, 2, 3].map((index) => (
                    <span
                      key={index}
                      className={`h-1 flex-1 rounded-full ${
                        index < strength.score
                          ? strengthTones[strength.score]
                          : "bg-sunken"
                      }`}
                    />
                  ))}
                </div>
                <p className="mt-1 text-xs text-ink3">
                  Strength: {strengthLabels[strength.score]}
                  {strength.problems[0] ? ` — ${strength.problems[0]}` : ""}
                </p>
              </div>
            )}
          </div>

          <TextField
            id="passwordConfirm"
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            required
            value={form.passwordConfirm}
            onChange={update("passwordConfirm")}
            error={errors.passwordConfirm}
            placeholder="Repeat your password"
          />

          <Button type="submit" loading={submitting} className="btn-lg btn-block">
            {submitting ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-ink3">
          Already have an account?{" "}
          <Link to="/login" className="text-gold-ink hover:underline">
            Sign in
          </Link>
        </p>
    </AuthLayout>
  );
}
