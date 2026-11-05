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

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setError(null);

    try {
      await login(email, password);
      setMessage("Login successful! Redirecting…");
      const next = safeNextPath(new URLSearchParams(window.location.search).get("next"));
      setTimeout(() => {
        window.location.href = next;
      }, 600);
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

  return (
    <div>
      <h1 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">
        Log in
      </h1>
      <p className="mt-2 text-[color:var(--muted)]">
        Access the SolarDoctor operations console with your account.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4">
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
