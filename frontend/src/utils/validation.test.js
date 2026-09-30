import { describe, expect, it } from "vitest";

import {
  fieldErrorsFrom,
  isEmail,
  isPhone,
  passwordStrength,
  validateLogin,
  validateProfile,
  validateRegistration,
} from "./validation";

/**
 * Validation tests.
 *
 * These mirror the *client-side* rules only. The authoritative policy lives in
 * Django's password validators; these tests exist so the UI gives fast, sensible
 * feedback rather than round-tripping every typo.
 */
describe("isEmail", () => {
  it("accepts normal addresses", () => {
    expect(isEmail("student@lawschool.test")).toBe(true);
    expect(isEmail("first.last+tag@sub.domain.co.in")).toBe(true);
  });

  it("rejects malformed addresses", () => {
    expect(isEmail("no-at-sign")).toBe(false);
    expect(isEmail("missing@tld")).toBe(false);
    expect(isEmail("@nolocal.com")).toBe(false);
    expect(isEmail("")).toBe(false);
    expect(isEmail(null)).toBe(false);
  });
});

describe("isPhone", () => {
  it("allows an empty value because the field is optional", () => {
    expect(isPhone("")).toBe(true);
    expect(isPhone(null)).toBe(true);
  });

  it("accepts common phone formats", () => {
    expect(isPhone("+91 98765 43210")).toBe(true);
    expect(isPhone("9876543210")).toBe(true);
    expect(isPhone("+1-555-123-4567")).toBe(true);
  });

  it("rejects letters and too-short values", () => {
    expect(isPhone("not-a-phone")).toBe(false);
    expect(isPhone("123")).toBe(false);
  });
});

describe("passwordStrength", () => {
  it("rejects short passwords", () => {
    const result = passwordStrength("Ab1!");
    expect(result.valid).toBe(false);
    expect(result.problems.join(" ")).toMatch(/at least 10/i);
  });

  it("requires a letter and a number", () => {
    expect(passwordStrength("1234567890123").valid).toBe(false);
    expect(passwordStrength("abcdefghijklm").valid).toBe(false);
  });

  it("rejects common words even when long enough", () => {
    const result = passwordStrength("lawschool2024");
    expect(result.valid).toBe(false);
    expect(result.problems.join(" ")).toMatch(/common/i);
  });

  it("accepts a reasonable password", () => {
    const result = passwordStrength("Kanoon2024Xyz");
    expect(result.valid).toBe(true);
    expect(result.score).toBeGreaterThan(1);
  });
});

describe("validateRegistration", () => {
  it("accepts a complete valid payload", () => {
    const { valid, errors } = validateRegistration({
      name: "Rahul Sharma",
      email: "rahul@lawschool.test",
      password: "Kanoon2024Xyz",
      passwordConfirm: "Kanoon2024Xyz",
    });
    expect(valid).toBe(true);
    expect(errors).toEqual({});
  });

  it("flags every missing field at once", () => {
    const { valid, errors } = validateRegistration({
      name: "",
      email: "",
      password: "",
      passwordConfirm: "",
    });
    expect(valid).toBe(false);
    expect(Object.keys(errors).sort()).toEqual(["email", "name", "password"]);
  });

  it("catches mismatched passwords", () => {
    const { valid, errors } = validateRegistration({
      name: "Rahul",
      email: "rahul@lawschool.test",
      password: "Kanoon2024Xyz",
      passwordConfirm: "Different2024Xyz",
    });
    expect(valid).toBe(false);
    expect(errors.passwordConfirm).toBeTruthy();
  });

  it("catches a malformed email", () => {
    const { errors } = validateRegistration({
      name: "Rahul",
      email: "not-an-email",
      password: "Kanoon2024Xyz",
      passwordConfirm: "Kanoon2024Xyz",
    });
    expect(errors.email).toBeTruthy();
  });
});

describe("validateLogin", () => {
  it("requires both fields", () => {
    expect(validateLogin({ email: "", password: "" }).valid).toBe(false);
    expect(validateLogin({ email: "a@b.co", password: "" }).valid).toBe(false);
    expect(validateLogin({ email: "a@b.co", password: "secret" }).valid).toBe(
      true,
    );
  });
});

describe("validateProfile", () => {
  it("requires a name", () => {
    expect(validateProfile({ name: "  ", phone: "" }).valid).toBe(false);
  });

  it("accepts a valid phone or an empty one", () => {
    expect(validateProfile({ name: "Rahul", phone: "" }).valid).toBe(true);
    expect(
      validateProfile({ name: "Rahul", phone: "+91 98765 43210" }).valid,
    ).toBe(true);
  });
});

describe("fieldErrorsFrom", () => {
  it("maps a backend error envelope onto form fields", () => {
    const mapped = fieldErrorsFrom({
      code: "validation_error",
      details: {
        email: ["This address is already registered."],
        name: ["Required."],
      },
    });
    expect(mapped.email).toBe("This address is already registered.");
    expect(mapped.name).toBe("Required.");
  });

  it("returns an empty object when there are no field details", () => {
    expect(fieldErrorsFrom({ code: "permission_denied" })).toEqual({});
    expect(fieldErrorsFrom(null)).toEqual({});
    expect(fieldErrorsFrom({ details: "a string" })).toEqual({});
  });
});
