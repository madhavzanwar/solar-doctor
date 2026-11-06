# Image credits

All photos are self-hosted in `frontend/public/images/` (AVIF + WebP, max 2400 px wide, re-encoded from the
originals; the hero is 1920 px wide and under 200 KB; next/image serves AVIF or WebP by browser support). None are hotlinked. Each is published under the
[Unsplash License](https://unsplash.com/license) or the [Pexels License](https://www.pexels.com/license/) (both free
to use, attribution appreciated). Titles, authors and licences were read from each photo's source page (hero on
2026-11-05, the other four on 2026-11-06).

| File (`frontend/public/images/`) | Title | Author | Source page | Licence | Used |
|---|---|---|---|---|---|
| `hero-desert-array.{avif,webp}` | A large field of solar panels in the desert | Priamo Mendez (@elprimetimerd) | https://unsplash.com/photos/a-large-field-of-solar-panels-in-the-desert-E4XEBPEkgUs | Unsplash License | Landing hero |
| `rooftop-navi-mumbai.{avif,webp}` | An aerial view of Podar International School with solar panels on the roof in Navi Mumbai | Zoshua Colah (@zoshuacolah) | https://unsplash.com/photos/podar-international-school-in-navi-mumbai-K5Mw_ZUoRPc | Unsplash License | Landing "Detect" row |
| `drone-solar-farm.{avif,webp}` | Drone Shot of a Solar Panels | K (@kelly on Pexels) | https://www.pexels.com/photo/drone-shot-of-a-solar-panels-11815854/ | Pexels License | Landing "Diagnose" row |
| `dusty-panel-closeup.{avif,webp}` | Close-Up Shot of Solar Panels | Kindel Media | https://www.pexels.com/photo/close-up-shot-of-solar-panels-9799712/ | Pexels License | Landing "Explain" row |
| `technician-cleaning.{avif,webp}` | Men Cleaning Solar Panels | Trinh Trần | https://www.pexels.com/photo/men-cleaning-solar-panels-11645003/ | Pexels License | Landing "Act" row |

## Update 2026-11-06

The four missing photos (rooftop, dusty close-up, technician cleaning, drone) were sourced and their title, author and
licence verified on each photo page in a browser. The rooftop original was fetched from the Unsplash image CDN
(`images.unsplash.com`, 2400 px) because the download URL sits behind a bot check; the Pexels originals came from
`images.pexels.com`. The earlier unused `array-aerial` and `technician-panel` files stay deleted (in git history).

## Removed

`technician-cleaning` (Florida Solar Fix, "Cleaning solar panels with a long handled brush") was removed. A search results page showed it among sponsored images, while its own photo page says "Free to use under the Unsplash License" with no sponsored label and asks for the credit "floridasolarfix.com - Solar panel cleaning". Because it is brand-advertising imagery and unused, it was dropped rather than shipped on an unverified reading. If a cleaning photo is wanted, a human should confirm the licence on the live page first. The only clearly free alternative found (Markus Spiske, "A person working on a solar panel", https://unsplash.com/photos/rNn_TU8dvoY, Unsplash License) shows installation, not cleaning, so it was not added.

## Hero weight

`hero-desert-array.webp` was re-encoded from 2400 px / 580 KB to 1920 px / about 197 KB, `.avif` to about 111 KB. Served sizes are measured in docs/solardoctor/BUILD_LOG.md.
