# AskData decorative canvas resource policy (F10)

Correction retained: the previous AskData canvas really animated thousands of
particles. Its mobile cost was not measured; source alone did not prove OOM.
This patch adds conservative controls, NOT a measured mobile speedup claim.

- Desktop animated particle ceiling2400, narrow canvas below720CSSpx ceiling900;
  each includes clusters/stars/dust/streams. Cadence requests at most24paints/s
  desktop or18narrow; actual browser cadence is not guaranteed. rAF callbacks can
  run faster while paint is skipped. No throughput benchmark is asserted.
- Save-Data, reported <=2logical CPUs or <=2GiB device-memory hint choose a static
  240particle scene with no continuing rAF. Hints are optional/coarse, not reliable
  device classification; absent hints use the regular bounded policy.
- Reduced-motion preference disables the decorative canvas entirely, including
  when changed while mounted. It does not disable questions/results/controls.
- At most1.5million backing pixels (6MB raw RGBA),0.5million in static mode,
  dimensions <=4096px and DPR <=1.5, additionally scaled down for large viewports.
  Invalid/absurd logical dimensions disable decoration. These are canvas pixel
  bounds, NOT whole-process/GPU/browser RSS guarantees.
- Hidden document or offscreen canvas (IntersectionObserver where supported)
  cancels rAF and releases bitmap/particles; becoming visible regenerates them.
  Resize is coalesced; observers/listeners/timers/rAF are detached/cancelled and
  bitmap/particle references released on unmount. Missing/failed canvas context
  leaves the functional UI usable. Theme changes redraw bounded/static scenes.

Deterministic policy/mounted tests cover count/pixel ceilings, paint skipping,
low-resource static mode, live reduced motion, hidden/offscreen transitions,
resize/unmount cleanup and unavailable context. Fake frame timestamps and mock
canvas operations are NOT measured browser FPS/CPU/RAM.

Remaining release validation: real browser responsive/theme appearance and frame
traces/long tasks/background CPU on representative mobile/low-resource devices,
including high DPR, visibility, navigation and preference changes. Oracle/ARM,
browser/GPU and production load remain unmeasured. Do not close this measured-risk
finding as a proven mobile-performance fix merely because these controls pass.
