import { useState } from "react";

import {
  Avatar,
  Button,
  Callout,
  ErrorState,
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
    <div className="wrap pb-24 pt-12 lg:pt-16">
      <div className="flex flex-col gap-3 pb-10">
        <h1 className="d2">Your profile</h1>
        <p className="body max-w-[560px]">
          Keep your details current so course notifications reach you.
        </p>
      </div>

      {generalError && (
        <div className="mb-6">
          <ErrorState error={{ message: generalError }} />
        </div>
      )}

      <div className="grid gap-12 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-start lg:gap-16">
        {/* --------------------------------------------------------- Identity */}
        <section className="flex flex-col" aria-label="Account">
          <div className="flex flex-col items-start gap-4">
            <Avatar user={user} size={88} />
            <div>
              <p className="h3 !text-[28px]">{user?.name}</p>
              <p className="small mt-1">{user?.email}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="tag tag-gold">{user?.role_display || user?.role}</span>
              {user?.is_email_verified ? (
                <span className="tag tag-ok">Email verified</span>
              ) : (
                <span className="tag">Email not verified</span>
              )}
            </div>
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
              className="block w-full text-sm text-ink3 file:mr-3 file:h-11 file:cursor-pointer file:rounded-lg file:border-0 file:bg-gold file:px-5 file:text-[15px] file:font-medium file:text-on-gold"
            />
            <p className="cap mt-2">PNG, JPEG, WebP or GIF. Maximum 5 MB.</p>
          </div>

          <dl className="m-0 mt-6 flex flex-col border-t border-line text-[15px]">
            <div className="flex justify-between gap-3 border-b border-line py-3">
              <dt className="text-ink3">Member since</dt>
              <dd className="m-0">{formatDate(user?.date_joined)}</dd>
            </div>
            <div className="flex justify-between gap-3 border-b border-line py-3">
              <dt className="text-ink3">Account type</dt>
              <dd className="m-0">{user?.role_display || user?.role}</dd>
            </div>
          </dl>
        </section>

        <div className="flex flex-col gap-14">
          {/* -------------------------------------------------------- Details */}
          <section aria-labelledby="details-heading">
            <h2 id="details-heading" className="h3 border-b border-line-strong pb-4">
              Personal details
            </h2>
            <div className="h-6" />

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

              <Button type="submit" loading={savingDetails} className="btn-lg">
                Save changes
              </Button>
            </form>
          </section>

          {/* ------------------------------------------------------- Password */}
          <section aria-labelledby="password-heading">
            <h2 id="password-heading" className="h3 border-b border-line-strong pb-4">
              Password
            </h2>
            <div className="h-6" />

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

              <Button type="submit" loading={savingPassword} className="btn-lg">
                Change password
              </Button>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
