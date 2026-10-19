import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = path.resolve(__dirname, "../..");

function parse(policy) {
  return Object.fromEntries(
    policy
      .split(";")
      .map((d) => d.trim())
      .filter(Boolean)
      .map((d) => {
        const [name, ...values] = d.split(/\s+/);
        return [name, values];
      }),
  );
}

const vercel = JSON.parse(fs.readFileSync(path.join(root, "vercel.json"), "utf8"));
const headers = Object.fromEntries(
  vercel.headers.find((h) => h.source === "/(.*)").headers.map((h) => [h.key, h.value]),
);
const vercelCsp = parse(headers["Content-Security-Policy"]);
const nginxText = fs.readFileSync(path.join(root, "csp.conf"), "utf8");
const nginxCsp = parse(/Content-Security-Policy "([^"]+)"/.exec(nginxText)[1]);

describe("Vercel security headers", () => {
  it("apply to every route, including the SPA rewrite", () => {
    expect(vercel.headers.some((h) => h.source === "/(.*)")).toBe(true);
    expect(vercel.rewrites[0].destination).toBe("/index.html");
  });

  it("ship the baseline hardening headers", () => {
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["Strict-Transport-Security"]).toMatch(/max-age=\d{7,}/);
    expect(headers["Referrer-Policy"]).toBeTruthy();
  });
});

describe("Content-Security-Policy", () => {
  it.each([
    ["vercel", vercelCsp],
    ["nginx", nginxCsp],
  ])("%s policy never weakens script execution", (_name, csp) => {
    expect(csp["script-src"]).toEqual(["'self'", "https://checkout.razorpay.com"]);
    expect(JSON.stringify(csp)).not.toMatch(/unsafe-eval/);
    expect(csp["script-src"]).not.toContain("'unsafe-inline'");
    expect(csp["script-src"].every((v) => v !== "*" && v !== "https:")).toBe(true);
    expect(csp["object-src"]).toEqual(["'none'"]);
    expect(csp["frame-ancestors"]).toEqual(["'none'"]);
    expect(csp["base-uri"]).toEqual(["'self'"]);
    expect(csp["default-src"]).toEqual(["'self'"]);
  });

  it("permits what the app needs: Razorpay, Cloudflare Stream, Google Fonts, the API", () => {
    expect(vercelCsp["frame-src"]).toEqual(
      expect.arrayContaining(["https://checkout.razorpay.com", "https://api.razorpay.com"]),
    );
    expect(vercelCsp["media-src"]).toEqual(
      expect.arrayContaining(["blob:", "https://*.cloudflarestream.com"]),
    );
    expect(vercelCsp["connect-src"]).toEqual(
      expect.arrayContaining(["'self'", "https://*.cloudflarestream.com", "https://api.razorpay.com"]),
    );
    expect(vercelCsp["style-src"]).toContain("https://fonts.googleapis.com");
    expect(vercelCsp["font-src"]).toContain("https://fonts.gstatic.com");
  });

  it("only the API origin differs between Vercel (cross-origin) and nginx (same-origin proxy)", () => {
    const strip = (csp) => ({ ...csp, "connect-src": csp["connect-src"].filter((v) => !v.includes("railway.app")) });
    expect(strip(vercelCsp)).toEqual(strip(nginxCsp));
    expect(nginxCsp["connect-src"].some((v) => v.includes("railway.app"))).toBe(false);
  });

  it("the document the SPA ships has no inline script the policy would block", () => {
    const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
    const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].filter(
      (m) => m[1].trim(),
    );
    expect(inline).toHaveLength(0);
    for (const m of html.matchAll(/<script[^>]*\bsrc="(https?:[^"]+)"/g)) {
      expect(m[1].startsWith("https://checkout.razorpay.com/")).toBe(true);
    }
  });
});

describe("nginx security headers stay intact", () => {
  it("keeps nosniff, frame deny and HSTS", () => {
    const text = fs.readFileSync(path.join(root, "security-headers.conf"), "utf8");
    expect(text).toMatch(/X-Content-Type-Options "nosniff"/);
    expect(text).toMatch(/X-Frame-Options\s+"DENY"/);
    expect(text).toMatch(/Strict-Transport-Security/);
  });
});
