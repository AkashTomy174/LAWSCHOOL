/**
 * Validation helpers shared by the auth and profile forms.
 *
 * These are **UX** checks only. Every rule here is also enforced by a Django
 * serializer: client-side validation exists to give fast feedback, never to be
 * the authority.
 */

export const PASSWORD_MIN_LENGTH = 10;

export function isEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test((value || "").trim());
}

export function isPhone(value) {
  const cleaned = (value || "").trim();
  if (!cleaned) return true; // optional field
  return /^[+]?[\d\s-]{7,20}$/.test(cleaned);
}

/**
 * Local mirror of the password policy.
 *
 * The backend runs Django's four validators (length, common password, numeric,
 * similarity). Reproducing all of them here would inevitably drift, so the client
 * checks what it can cheaply and defers the rest to the server's error payload.
 */
export function passwordStrength(password) {
  const value = password || "";
  const problems = [];

  if (value.length < PASSWORD_MIN_LENGTH) {
    problems.push(`Use at least ${PASSWORD_MIN_LENGTH} characters.`);
  }
  if (!/[A-Za-z]/.test(value)) problems.push("Include at least one letter.");
  if (!/\d/.test(value)) problems.push("Include at least one number.");
  if (/^\d+$/.test(value)) problems.push("Do not use only numbers.");

  const common = [
    "password",
    "qwerty",
    "letmein",
    "welcome",
    "admin",
    "lawschool",
  ];
  if (common.some((word) => value.toLowerCase().includes(word))) {
    problems.push("Avoid common words and phrases.");
  }

  // 0-4 score for the strength meter; presentation only, not a security control.
  let score = 0;
  if (value.length >= PASSWORD_MIN_LENGTH) score += 1;
  if (value.length >= 14) score += 1;
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1;
  if (/[^A-Za-z0-9]/.test(value)) score += 1;

  return { score, problems, valid: problems.length === 0 };
}

export function validateRegistration({
  email,
  name,
  password,
  passwordConfirm,
}) {
  const errors = {};
  if (!name?.trim()) errors.name = "Please enter your full name.";
  if (!email?.trim()) errors.email = "Please enter your email address.";
  else if (!isEmail(email)) errors.email = "Enter a valid email address.";
  if (!password) errors.password = "Please choose a password.";
  else {
    const strength = passwordStrength(password);
    if (!strength.valid) errors.password = strength.problems[0];
  }
  if (password !== passwordConfirm) {
    errors.passwordConfirm = "Passwords do not match.";
  }
  return { valid: Object.keys(errors).length === 0, errors };
}

export function validateLogin({ email, password }) {
  const errors = {};
  if (!email?.trim()) errors.email = "Please enter your email address.";
  else if (!isEmail(email)) errors.email = "Enter a valid email address.";
  if (!password) errors.password = "Please enter your password.";
  return { valid: Object.keys(errors).length === 0, errors };
}

export function validateProfile({ name, phone }) {
  const errors = {};
  if (!name?.trim()) errors.name = "Name cannot be empty.";
  if (!isPhone(phone)) errors.phone = "Enter a valid phone number.";
  return { valid: Object.keys(errors).length === 0, errors };
}

/**
 * Flatten a backend `{error: {details}}` payload into per-field messages so a form
 * can render them next to the relevant input.
 */
export function fieldErrorsFrom(apiError) {
  const details = apiError?.details;
  if (!details || typeof details !== "object") return {};
  const mapped = {};
  for (const [field, messages] of Object.entries(details)) {
    const value = Array.isArray(messages) ? messages[0] : messages;
    mapped[field] = String(value);
  }
  return mapped;
}
