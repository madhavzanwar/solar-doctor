/**
 * Module-level scroll singleton.
 * Updated by window.scroll event outside R3F.
 * Read inside R3F useFrame — zero React re-renders.
 */
export const scrollStore = {
  progress: 0,    // 0 → 1 (scrollY / maxScroll)
  raw: 0,         // raw scrollY pixels
}
