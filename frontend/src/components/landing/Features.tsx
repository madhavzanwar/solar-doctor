const features = [
  {
    title: "Detect",
    body: "Inverter and string telemetry is compared with a physics expected-power baseline built from pvlib clear-sky and PVWatts models. Sustained deficits on quality-checked clear-sky periods are flagged before they show up as lost revenue.",
  },
  {
    title: "Diagnose",
    body: "A drone or phone photo of the panel is classified as Clean, Dusty, Bird-drop, Snow-covered, Electrical damage or Physical damage, with a confidence score and an explicit “needs field check” state when the model is unsure.",
  },
  {
    title: "Explain",
    body: "Every diagnosis shows its evidence: LIME superpixels and Grad-CAM heatmaps over the photo, cross-checked against the telemetry deficit for the same string, so a recommendation is never a black box.",
  },
  {
    title: "Act",
    body: "The deficit becomes recoverable kWh and rupees, and a decision: clean now, wait, field check or replace. Dispatch a work order and verify the fix by the yield that comes back.",
  },
];

export function Features() {
  return (
    <section id="features" className="site-grid border-y border-[color:var(--line)]">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
        <div className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[color:var(--muted)]">
            Detect, diagnose, explain, act
          </p>
          <h2 className="mt-3 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight text-[color:var(--ink)] sm:text-4xl">
            One loop from silent loss to verified fix
          </h2>
          <p className="mt-4 text-lg leading-relaxed text-[color:var(--muted)]">
            Monitoring tools tell you output is low. Inspection tools tell you a
            panel is dirty. SolarDoctor connects the two and puts a rupee value
            on the decision.
          </p>
        </div>

        <ol className="mt-14 divide-y divide-[color:var(--line)] border-y border-[color:var(--line)]">
          {features.map((feature, index) => (
            <li
              key={feature.title}
              className="grid gap-4 py-8 sm:grid-cols-[5rem_1fr] sm:gap-10"
            >
              <span className="font-[family-name:var(--font-display)] text-2xl font-bold text-[color:var(--field)]">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <h3 className="font-[family-name:var(--font-display)] text-xl font-bold tracking-tight">
                  {feature.title}
                </h3>
                <p className="mt-2 max-w-2xl text-base leading-relaxed text-[color:var(--muted)]">
                  {feature.body}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
