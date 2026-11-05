import Link from "next/link";
import { Logo } from "@/components/Logo";

export function SiteFooter() {
  return (
    <footer className="border-t border-[color:var(--line)] bg-[color:var(--field)] text-[#e8efe8]">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-5 py-12 sm:flex-row sm:items-end sm:justify-between sm:px-8">
        <div>
          <p className="font-[family-name:var(--font-display)] text-2xl font-bold tracking-tight">
            <Logo onDark />
          </p>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-[#c5d2c5]">
            Solar O&amp;M that closes the loop: detect silent yield loss, diagnose
            it from a photo, explain the evidence, and act with a work order
            whose fix is verified by recovered yield.
          </p>
        </div>
        <div className="flex gap-4 text-sm font-semibold">
          <Link href="/login" className="hover:underline">
            Log in
          </Link>
          <Link href="/register" className="hover:underline">
            Register
          </Link>
          <a href="#features" className="hover:underline">
            Features
          </a>
        </div>
      </div>
    </footer>
  );
}
