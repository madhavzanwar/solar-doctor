"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { ApiError, login } from "@/lib/api";
import { safeNextPath } from "@/lib/auth-guard";
import { PASSWORD_MAX, PASSWORD_MIN } from "@/lib/password";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function executeLogin(userEmail: string, userPass: string) {
    setPending(true);
    setMessage(null);
    setError(null);

    try {
      await login(userEmail, userPass);
      setMessage("Login successful! Redirecting…");
      const next = safeNextPath(new URLSearchParams(window.location.search).get("next"));
      setTimeout(() => {
        window.location.href = next;
      }, 500);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Invalid email or password."
          : err instanceof Error
            ? err.message
            : "Login failed. Please try again.",
      );
    } finally {
      setPending(false);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await executeLogin(email, password);
  }

  async function onDemoLogin(demoEmail: string, demoPass: string) {
    setEmail(demoEmail);
    setPassword(demoPass);
    await executeLogin(demoEmail, demoPass);
  }

  return (
    <div>
      <h1 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">
        Log in
      </h1>
      <p className="mt-2 text-[color:var(--muted)]">
        Access the SolarDoctor operations console with your account.
      </p>

      {/* Demo Credentials Quick-Access */}
      <div className="mt-6 rounded border border-[color:var(--line)] bg-[color:var(--panel)] p-4 shadow-xs">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-[color:var(--muted)]">
            Instant Demo Sign-In
          </span>
          <span className="text-[11px] font-semibold text-[color:var(--sun-ink,#9a6118)]">
            1-Click Log In
          </span>
        </div>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          <button
            type="button"
            disabled={pending}
            onClick={() => onDemoLogin("admin@solardoctor.local", "adminpassword123")}
            className="flex flex-col items-start rounded border border-[color:var(--line)] bg-[color:var(--paper)] p-2.5 text-left transition hover:border-[color:var(--field)] hover:shadow-sm cursor-pointer disabled:opacity-50"
          >
            <span className="text-xs font-bold text-[color:var(--ink)]">👑 Admin (Full Access)</span>
            <span className="mt-0.5 text-[11px] text-[color:var(--muted)]">admin@solardoctor.local</span>
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => onDemoLogin("demo@solardoctor.local", "demopassword123")}
            className="flex flex-col items-start rounded border border-[color:var(--line)] bg-[color:var(--paper)] p-2.5 text-left transition hover:border-[color:var(--field)] hover:shadow-sm cursor-pointer disabled:opacity-50"
          >
            <span className="text-xs font-bold text-[color:var(--ink)]">⚡ Operator</span>
            <span className="mt-0.5 text-[11px] text-[color:var(--muted)]">demo@solardoctor.local</span>
          </button>
        </div>
      </div>

      <div className="my-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-[color:var(--line)]" />
        <span className="text-xs text-[color:var(--muted)] uppercase font-semibold">Or enter credentials</span>
        <div className="h-px flex-1 bg-[color:var(--line)]" />
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold">Email</span>
          <input
            className="input-field"
            type="email"
            name="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold">Password</span>
          <input
            className="input-field"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            minLength={PASSWORD_MIN}
            maxLength={PASSWORD_MAX}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        {error ? (
          <p role="alert" className="text-sm font-medium text-[color:var(--danger)]">
            {error}
          </p>
        ) : null}

        {message ? (
          <p
            role="status"
            className="border border-[color:var(--line)] bg-[color:var(--panel)] px-3 py-2 text-sm leading-relaxed text-[color:var(--muted)]"
          >
            {message}
          </p>
        ) : null}

        <button type="submit" className="btn-primary w-full" disabled={pending}>
          {pending ? "Signing in…" : "Log in"}
        </button>
      </form>

      <p className="mt-6 text-sm text-[color:var(--muted)]">
        No account yet?{" "}
        <Link
          href="/register"
          className="font-semibold text-[color:var(--field)] underline-offset-2 hover:underline"
        >
          Register
        </Link>
      </p>
    </div>
  );
}
