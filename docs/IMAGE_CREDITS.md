# Image credits

All photos are self-hosted in `frontend/public/images/` (AVIF + WebP, max 2400 px wide, re-encoded from the
originals; the hero is 1920 px wide and under 200 KB; next/image serves AVIF or WebP by browser support). None are hotlinked. All are published under the
[Unsplash License](https://unsplash.com/license) (free to use, attribution appreciated). Titles, authors and licence
status were read from each photo's Unsplash page on 2026-11-05.

| File (`frontend/public/images/`) | Title | Author | Source page | Licence | Used |
|---|---|---|---|---|---|
| `hero-desert-array.{avif,webp}` | A large field of solar panels in the desert | Priamo Mendez (@elprimetimerd) | https://unsplash.com/photos/a-large-field-of-solar-panels-in-the-desert-E4XEBPEkgUs | Unsplash License | Landing hero |
| `array-aerial.{avif,webp}` | Solar panels are arranged in a vast array | Miguel Alcântara (@miguelalcantara) | https://unsplash.com/photos/solar-panels-are-arranged-in-a-vast-array-yz79CF7WMaE | Unsplash License | Reserved for later marketing sections |
| `technician-panel.{avif,webp}` | A man in a hardhat working on a solar panel | Siwawut Phoophinyo | https://unsplash.com/photos/a-man-in-a-hardhat-working-on-a-solar-panel-JlhvFEVMwng | Unsplash License | Reserved |

## Not yet sourced (open issue)

DESIGN.md §9 also asks for an Indian rooftop array and a close-up of a dusty panel. The rooftop candidates found
were Unsplash+ (paid licence) and no clearly dusty close-up was verified, so neither is included. Do not substitute
Kaggle dataset images on public pages (licence "Unknown").

## Removed

`technician-cleaning` (Florida Solar Fix, "Cleaning solar panels with a long handled brush") was removed. A search results page showed it among sponsored images, while its own photo page says "Free to use under the Unsplash License" with no sponsored label and asks for the credit "floridasolarfix.com - Solar panel cleaning". Because it is brand-advertising imagery and unused, it was dropped rather than shipped on an unverified reading. If a cleaning photo is wanted, a human should confirm the licence on the live page first. The only clearly free alternative found (Markus Spiske, "A person working on a solar panel", https://unsplash.com/photos/rNn_TU8dvoY, Unsplash License) shows installation, not cleaning, so it was not added.

## Hero weight

`hero-desert-array.webp` was re-encoded from 2400 px / 580 KB to 1920 px / about 197 KB, `.avif` to about 111 KB. Served sizes are measured in docs/solardoctor/BUILD_LOG.md.
