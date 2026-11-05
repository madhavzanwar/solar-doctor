# Image credits

All photos are self-hosted in `frontend/public/images/` (AVIF + WebP, max 2400 px wide, re-encoded from the
originals; the hero is 1920 px wide and under 200 KB; next/image serves AVIF or WebP by browser support). None are hotlinked. All are published under the
[Unsplash License](https://unsplash.com/license) (free to use, attribution appreciated). Titles, authors and licence
status were read from each photo's Unsplash page on 2026-11-05.

| File (`frontend/public/images/`) | Title | Author | Source page | Licence | Used |
|---|---|---|---|---|---|
| `hero-desert-array.{avif,webp}` | A large field of solar panels in the desert | Priamo Mendez (@elprimetimerd) | https://unsplash.com/photos/a-large-field-of-solar-panels-in-the-desert-E4XEBPEkgUs | Unsplash License | Landing hero |

## Update 2026-11-05 (sd-frontend, finish pass)

Attempted to source the four missing photos (Indian rooftop, dusty close-up, technician cleaning, drone over a farm)
from Pexels/Unsplash. The sandbox has no web search or page-fetch tool, and unsplash.com / pexels.com answer plain
curl with bot checks (HTTP 403/307); working around the check was not attempted. Without reading each photo page
(title, author, licence, not sponsored) nothing could be verified, so **no new image was added**. `array-aerial` and
`technician-panel` were unused ("Reserved"), so they were deleted from `frontend/public/images/` (they remain in git
history; their table rows are dropped). Only the hero is shipped; its licence is still as unverified from the sandbox
as stated above. A human with a browser should pick the four photos, check each page, and add them here.

## Not yet sourced (open issue)

DESIGN.md §9 also asks for an Indian rooftop array and a close-up of a dusty panel. The rooftop candidates found
were Unsplash+ (paid licence) and no clearly dusty close-up was verified, so neither is included. Do not substitute
Kaggle dataset images on public pages (licence "Unknown").

## Removed

`technician-cleaning` (Florida Solar Fix, "Cleaning solar panels with a long handled brush") was removed. A search results page showed it among sponsored images, while its own photo page says "Free to use under the Unsplash License" with no sponsored label and asks for the credit "floridasolarfix.com - Solar panel cleaning". Because it is brand-advertising imagery and unused, it was dropped rather than shipped on an unverified reading. If a cleaning photo is wanted, a human should confirm the licence on the live page first. The only clearly free alternative found (Markus Spiske, "A person working on a solar panel", https://unsplash.com/photos/rNn_TU8dvoY, Unsplash License) shows installation, not cleaning, so it was not added.

## Hero weight

`hero-desert-array.webp` was re-encoded from 2400 px / 580 KB to 1920 px / about 197 KB, `.avif` to about 111 KB. Served sizes are measured in docs/solardoctor/BUILD_LOG.md.
