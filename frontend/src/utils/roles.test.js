import { describe, expect, it } from "vitest";

import { homePathFor, isStaffUser, navLinksFor, teachingTabs } from "./roles";

const labels = (user) => navLinksFor(user).map((link) => link.label);

describe("navLinksFor", () => {
  it("shows visitors the public links", () => {
    expect(labels(null)).toEqual(["Courses", "Plans", "Leaderboard"]);
  });

  it("gives learners their navigation, including live classes", () => {
    expect(labels({ role: "student" })).toEqual([
      "Courses",
      "Dashboard",
      "Live classes",
      "Plans",
      "Leaderboard",
    ]);
  });

  it("hides Plans and Leaderboard from instructors and admins", () => {
    for (const role of ["instructor", "admin"]) {
      expect(labels({ role })).not.toContain("Plans");
      expect(labels({ role })).not.toContain("Leaderboard");
    }
  });

  it("gives staff exactly their own navigation", () => {
    expect(labels({ role: "instructor" })).toEqual(["Courses", "Dashboard", "Teaching"]);
    expect(labels({ role: "admin" })).toEqual(["Courses", "Dashboard", "Admin"]);
  });

  it("gives instructors Teaching but never Admin", () => {
    const links = labels({ role: "instructor" });
    expect(links).toContain("Teaching");
    expect(links).not.toContain("Admin");
  });

  it("gives admins Admin but not Teaching", () => {
    const links = labels({ role: "admin" });
    expect(links).toContain("Admin");
    expect(links).not.toContain("Teaching");
  });

  it("never shows learners a staff link", () => {
    const links = labels({ role: "student" });
    expect(links).not.toContain("Teaching");
    expect(links).not.toContain("Admin");
  });
});

describe("homePathFor / isStaffUser", () => {
  it("sends each role to its own workspace", () => {
    expect(homePathFor({ role: "student" })).toBe("/dashboard");
    expect(homePathFor({ role: "instructor" })).toBe("/instructor");
    expect(homePathFor({ role: "admin" })).toBe("/admin");
    expect(homePathFor(null)).toBe("/dashboard");
  });

  it("treats instructors and admins as staff", () => {
    expect(isStaffUser({ role: "student" })).toBe(false);
    expect(isStaffUser({ role: "instructor" })).toBe(true);
    expect(isStaffUser({ role: "admin" })).toBe(true);
  });
});

describe("teachingTabs", () => {
  it("lists the five workspace sections plus the overview", () => {
    expect(teachingTabs.map((tab) => tab.label)).toEqual([
      "Overview",
      "My Courses",
      "Manage Courses",
      "Videos",
      "Quizzes",
      "Live Classes",
    ]);
  });
});
