const steps = [
  {
    title: "Ingest telemetry and weather",
    body: "Inverter and string readings land alongside irradiance from NASA POWER or site sensors. Simulated and demo data is always labelled.",
  },
  {
    title: "Compute the physics baseline",
    body: "pvlib derives clear-sky irradiance, plane-of-array and cell temperature to give the expected power the plant should be producing.",
  },
  {
    title: "Flag the deficit",
    body: "Sustained shortfalls against the baseline on clear-sky periods raise an alert, quantified in kW, kWh and rupees.",
  },
  {
    title: "Diagnose and explain from a photo",
    body: "Upload a panel photo. The classifier names the cause, and LIME and Grad-CAM overlays show which regions drove the call.",
  },
  {
    title: "Act and verify",
    body: "Pick clean now, wait, field check or replace, dispatch a work order, and confirm the fix by the yield that recovers.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="bg-[color:var(--panel)]">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
        <div className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[color:var(--muted)]">
            How it works
          </p>
          <h2 className="mt-3 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight sm:text-4xl">
            From raw signals to a verified fix
          </h2>
          <p className="mt-4 text-lg leading-relaxed text-[color:var(--muted)]">
            A five-step pipeline keeps telemetry, physics, vision and field work in
            the same loop, so the number on screen is the number you recover.
          </p>
        </div>

        <div className="mt-14 border-l border-[color:var(--line)] pl-6 sm:pl-8">
          {steps.map((step, index) => (
            <article key={step.title} className="relative pb-10 last:pb-0">
              <span className="absolute -left-[1.9rem] top-1 flex h-7 w-7 items-center justify-center border border-[color:var(--field)] bg-[color:var(--panel)] font-[family-name:var(--font-display)] text-xs font-bold text-[color:var(--field)] sm:-left-[2.15rem]">
                {index + 1}
              </span>
              <h3 className="font-[family-name:var(--font-display)] text-xl font-bold tracking-tight">
                {step.title}
              </h3>
              <p className="mt-2 max-w-2xl text-base leading-relaxed text-[color:var(--muted)]">
                {step.body}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
