import Image from "next/image";
import Link from "next/link";
import { Logo } from "@/components/Logo";

export function Hero() {
  return (
    <section className="relative min-h-[100svh] overflow-hidden text-white">
      <Image
        src="/images/hero-desert-array.webp"
        alt="Rows of solar panels across a desert plain"
        fill
        priority
        className="object-cover object-center"
        sizes="100vw"
        quality={40}
      />
      <div className="absolute inset-0 bg-[rgba(10,22,16,0.72)]" />

      <div className="relative z-10 mx-auto flex min-h-[100svh] max-w-6xl flex-col justify-end px-5 pb-16 pt-28 sm:px-8 sm:pb-20">
        <div className="max-w-3xl">
          <p className="animate-rise mb-4 flex items-center gap-2 font-[family-name:var(--font-display)] text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--sun)]">
            <span className="animate-dot inline-block h-2 w-2 rounded-[1px] bg-[color:var(--sun)]" />
            Operational prototype
          </p>
          <h1 className="animate-rise-delay-1 font-[family-name:var(--font-display)] text-5xl font-extrabold leading-[0.95] tracking-tight sm:text-6xl md:text-7xl">
            <Logo onDark />
          </h1>
          <div className="animate-line mt-5 h-px w-28 bg-[color:var(--sun)]" />
          <p className="animate-rise-delay-2 mt-6 max-w-xl text-lg leading-relaxed text-white/88 sm:text-xl">
            Find the silent loss. Telemetry against a physics baseline shows a
            plant is under-delivering; a panel photo shows why; the fix is
            dispatched and verified in recovered kWh and rupees.
          </p>
          <div className="animate-rise-delay-3 mt-9 flex flex-wrap gap-3">
            <Link href="/register" className="btn-primary">
              Create account
            </Link>
            <a href="#how-it-works" className="btn-ghost border-white/70 text-white">
              See how it works
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
