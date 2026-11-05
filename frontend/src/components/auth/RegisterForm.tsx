"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { register } from "@/lib/api";

export function RegisterForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    setError(null);

    if (password !== confirm) {
      setError("Passwords do not match.");
      setPending(false);
      return;
    }

    try {
      const signedIn = await register({ email, password, full_name: name.trim() || undefined });
      if (signedIn) {
        setMessage("Account created! Signing you in…");
        setTimeout(() => {
          window.location.href = "/dashboard";
        }, 600);
      } else {
        setMessage("Account created! Please log in.");
        setTimeout(() => {
          window.location.href = "/login";
        }, 1200);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <h1 className="font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">
        Create account
      </h1>
      <p className="mt-2 text-[color:var(--muted)]">
        Create an account to start finding and fixing solar yield loss.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold">Full name</span>
          <input
            className="input-field"
            type="text"
            name="name"
            autoComplete="name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>

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
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold">
            Confirm password
          </span>
          <input
            className="input-field"
            type="password"
            name="confirm"
            autoComplete="new-password"
            required
            minLength={8}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
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
          {pending ? "Creating account…" : "Register"}
        </button>
      </form>

      <p className="mt-6 text-sm text-[color:var(--muted)]">
        Already registered?{" "}
        <Link
          href="/login"
          className="font-semibold text-[color:var(--field)] underline-offset-2 hover:underline"
        >
          Log in
        </Link>
      </p>
    </div>
  );
}
