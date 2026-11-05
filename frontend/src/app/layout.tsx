import type { Metadata } from "next";
import {
  Bricolage_Grotesque,
  Geist,
  Geist_Mono,
  Instrument_Serif,
  Source_Sans_3,
  Syne,
} from "next/font/google";
import "./globals.css";
import "./dashboard/dashboard.css";
import "./solardoctor.css";

/*
 * Font modes (DESIGN.md §3):
 *   default                      Bricolage Grotesque / Geist / Geist Mono / Instrument Serif
 *   NEXT_PUBLIC_FONT_MODE=clone  Syne / Source Sans 3 (exact SolarPulseAI look, used by the visual harness)
 * next/font needs statically analysable calls, so every family is declared; the mode only decides which
 * faces the shared --font-display / --font-sans / --font-mono variables point at (see solardoctor.css).
 */
const bricolage = Bricolage_Grotesque({
  variable: "--f-bricolage",
  subsets: ["latin"],
  axes: ["opsz"],
  display: "swap",
});
const geist = Geist({ variable: "--f-geist", subsets: ["latin"], display: "swap" });
const geistMono = Geist_Mono({ variable: "--f-geist-mono", subsets: ["latin"], display: "swap" });
const instrument = Instrument_Serif({
  variable: "--f-instrument",
  subsets: ["latin"],
  weight: "400",
  style: "italic",
  display: "swap",
});
const syne = Syne({
  variable: "--f-syne",
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  preload: false,
});
const sourceSans = Source_Sans_3({
  variable: "--f-source-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  preload: false,
});

const cloneMode = process.env.NEXT_PUBLIC_FONT_MODE === "clone";

export const metadata: Metadata = {
  title: "SolarDoctor — Find the silent loss in solar yield",
  description:
    "SolarDoctor detects silent solar yield loss against a physics baseline, diagnoses the cause from a panel photo, explains the evidence, and turns it into a verified work order.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const fontVars = [
    bricolage.variable,
    geist.variable,
    geistMono.variable,
    instrument.variable,
    syne.variable,
    sourceSans.variable,
  ].join(" ");
  return (
    <html lang="en">
      <body
        className={`${fontVars} ${cloneMode ? "font-mode-clone" : "font-mode-upgrade"} antialiased`}
      >
        <a href="#main" className="sd-skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
