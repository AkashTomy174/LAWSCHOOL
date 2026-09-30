import { useState } from "react";

import { PageHeader } from "../../components/Layout";
import {
  Avatar,
  Badge,
  Button,
  Callout,
  ErrorState,
  Panel,
  TextField,
} from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useUI } from "../../context/UIContext";
import { authService } from "../../services/authService";
import {
  fieldErrorsFrom,
  passwordStrength,
  validateProfile,
} from "../../utils/validation";
import { formatDate } from "../../utils/format";

/**
 * Profile management: details, avatar, and password.
 *
 * Two behaviours worth noting:
 *
 * * `email`, `role` and `is_email_verified` are rendered as read-only. They are also
 *   read-only server-side, so even a crafted PATCH cannot change them — the UI just
 *   avoids offering something that would fail.
 * * Changing the password invalidates every session (by design), so the student is
 *   told they will need to sign in again rather than being silently logged out.
 */
export default function Profile() {
  const { user, updateUser, refreshUser } = useAuth();
  const { pushToast } = useUI();

  const [details, setDetails] = useState({
    name: user?.name || "",
    phone: user?.phone || "",
    bio: user?.bio || "",
    city: user?.city || "",
    state: user?.state || "",
  });
  const [detailErrors, setDetailErrors] = useState({});
  const [savingDetails, setSavingDetails] = useState(false);

  const [passwords, setPasswords] = useState({
    currentPassword: "",
    newPassword: "",
    newPasswordConfirm: "",
  });
  const [passwordErrors, setPasswordErrors] = useState({});
  const [savingPassword, setSavingPassword] = useState(false);

  const [generalError, setGeneralError] = useState(null);

  const strength = passwordStrength(passwords.newPassword);

  /* ------------------------------- Details ------------------------------- */
  async function saveDetails(event) {
    event.preventDefault();
    setGeneralError(null);

    const { valid, errors } = validateProfile(details);
    if (!valid) {
      setDetailErrors(errors);
      return;
    }

    setSavingDetails(true);
    try {
      const updated = await authService.updateProfile(details);
      // Push the server's response into context so the navbar/avatar update too.
      updateUser(updated);
      pushToast({ message: "Profile updated.", tone: "success" });
    } catch (caught) {
      const mapped = fieldErrorsFrom(caught);
      if (Object.keys(mapped).length) setDetailErrors(mapped);
      else setGeneralError(caught.message);
    } finally {
      setSavingDetails(false);
    }
  }

  async function handleAvatar(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    // Cheap client-side guard; the server validates the real image bytes.
    if (file.size > 5 * 1024 * 1024) {
      pushToast({ message: "Image must be smaller than 5 MB.", tone: "error" });
      event.target.value = "";
      return;
    }

    try {
      const updated = await authService.uploadAvatar(file);
      updateUser(updated);
      pushToast({ message: "Avatar updated.", tone: "success" });
    } catch (caught) {
      pushToast({ message: caught.message, tone: "error" });
    } finally {
      event.target.value = "";
    }
  }

  /* ------------------------------- Password ------------------------------ */
  async function savePassword(event) {
    event.preventDefault();
    setGeneralError(null);

    const errors = {};
    if (!passwords.currentPassword)
      errors.currentPassword = "Enter your current password.";
    if (!strength.valid)
      errors.newPassword =
        strength.problems[0] || "Choose a stronger password.";
    if (passwords.newPassword !== passwords.newPasswordConfirm) {
      errors.newPasswordConfirm = "Passwords do not match.";
    }
    if (Object.keys(errors).length) {
      setPasswordErrors(errors);
      return;
    }

    setSavingPassword(true);
    try {
      await authService.changePassword(passwords);
      setPasswords({
        currentPassword: "",
        newPassword: "",
        newPasswordConfirm: "",
      });
      pushToast({
        message:
          "Password changed. Please sign in again on your other devices.",
        tone: "success",
      });
      // changePassword clears local tokens; re-resolve the session state.
      refreshUser();
    } catch (caught) {
      const mapped = fieldErrorsFrom(caught);
      if (Object.keys(mapped).length) setPasswordErrors(mapped);
      else setGeneralError(caught.message);
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:py-10">
      <PageHeader
        title="Your profile"
        description="Keep your details current so course notifications reach you."
        breadcrumbs={[
          { label: "Dashboard", to: "/dashboard" },
          { label: "Profile" },
        ]}
      />

      {generalError && (
        <div className="mb-6">
          <ErrorState error={{ message: generalError }} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr] lg:items-start">
        {/* --------------------------------------------------------- Identity */}
        <Panel className="p-5">
          <div className="flex flex-col items-center gap-3 text-center">
            <Avatar user={user} size={96} />
            <div>
              <p className="font-display text-lg text-parchment">
                {user?.name}
              </p>
              <p className="text-sm text-white/50">{user?.email}</p>
            </div>
            <Badge tone="gold">{user?.role}</Badge>
            {user?.is_email_verified ? (
              <Badge tone="success">Email verified</Badge>
            ) : (
              <Badge tone="warning">Email not verified</Badge>
            )}
          </div>

          <div className="mt-5">
            <label htmlFor="avatar" className="label">
              Change photo
            </label>
            <input
              id="avatar"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              onChange={handleAvatar}
              className="block w-full text-sm text-white/60 file:mr-3 file:rounded-full file:border-0 file:bg-gold-500 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-black"
            />
            <p className="mt-1 text-xs text-white/40">
              PNG, JPEG, WebP or GIF. Maximum 5 MB.
            </p>
          </div>

          <dl className="mt-6 space-y-2 border-t border-[var(--color-border-subtle)] pt-4 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-white/45">Member since</dt>
              <dd className="text-white/75">{formatDate(user?.date_joined)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-white/45">Account type</dt>
              <dd className="text-white/75">
                {user?.role_display || user?.role}
              </dd>
            </div>
          </dl>
        </Panel>

        <div className="space-y-6">
          {/* -------------------------------------------------------- Details */}
          <Panel className="p-5">
            <h2 className="font-display text-lg text-parchment">
              Personal details
            </h2>
            <div className="gold-rule my-4" />

            <form onSubmit={saveDetails} noValidate className="space-y-4">
              <TextField
                id="profile-email"
                label="Email address"
                value={user?.email || ""}
                readOnly
                disabled
                hint="Email is your sign-in identifier and cannot be changed here. Contact support if it needs updating."
              />

              <TextField
                id="profile-name"
                label="Full name"
                value={details.name}
                onChange={(event) =>
                  setDetails((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
                error={detailErrors.name}
              />

              <TextField
                id="profile-phone"
                label="Phone"
                type="tel"
                value={details.phone}
                onChange={(event) =>
                  setDetails((current) => ({
                    ...current,
                    phone: event.target.value,
                  }))
                }
                error={detailErrors.phone}
              />

              <div className="grid gap-4 sm:grid-cols-2">
                <TextField
                  id="profile-city"
                  label="City"
                  value={details.city}
                  onChange={(event) =>
                    setDetails((current) => ({
                      ...current,
                      city: event.target.value,
                    }))
                  }
                />
                <TextField
                  id="profile-state"
                  label="State"
                  value={details.state}
                  onChange={(event) =>
                    setDetails((current) => ({
                      ...current,
                      state: event.target.value,
                    }))
                  }
                />
              </div>

              <TextField
                id="profile-bio"
                as="textarea"
                rows={3}
                label="About you"
                value={details.bio}
                onChange={(event) =>
                  setDetails((current) => ({
                    ...current,
                    bio: event.target.value,
                  }))
                }
                hint="Shown on your instructor profile if you teach."
              />

              <Button type="submit" loading={savingDetails}>
                Save changes
              </Button>
            </form>
          </Panel>

          {/* ------------------------------------------------------- Password */}
          <Panel className="p-5">
            <h2 className="font-display text-lg text-parchment">Password</h2>
            <div className="gold-rule my-4" />

            <form onSubmit={savePassword} noValidate className="space-y-4">
              <TextField
                id="current-password"
                label="Current password"
                type="password"
                autoComplete="current-password"
                value={passwords.currentPassword}
                onChange={(event) =>
                  setPasswords((current) => ({
                    ...current,
                    currentPassword: event.target.value,
                  }))
                }
                error={passwordErrors.currentPassword}
              />

              <div>
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
                  error={passwordErrors.newPassword}
                  hint={
                    passwords.newPassword && strength.valid
                      ? "Strong password."
                      : "At least 10 characters with letters and numbers."
                  }
                />
              </div>

              <TextField
                id="confirm-password"
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
                error={passwordErrors.newPasswordConfirm}
              />

              <Callout tone="info">
                Changing your password signs you out everywhere, including this
                device.
              </Callout>

              <Button type="submit" loading={savingPassword}>
                Change password
              </Button>
            </form>
          </Panel>
        </div>
      </div>
    </div>
  );
}
