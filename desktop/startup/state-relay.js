"use strict";

/**
 * Bridges startup updates from the orchestrator to the renderer.
 *
 * The renderer cannot receive `umi:startup-state` events until Next.js has
 * hydrated and registered its listener, but the desktop may send the GREETING
 * payload before that happens. The relay keeps the latest event buffered so it
 * can be replayed once the renderer signals it is ready — and exposes it to a
 * pull-based fallback (`getStartupState`).
 */
class StartupStateRelay {
  constructor({ send, logger = console }) {
    this.send = send;
    this.logger = logger;
    this._last = null;
  }

  emit(event) {
    this._last = event;
    this.send(event);
  }

  /** Re-send the most recent event (used after the renderer ACKs readiness). */
  replay() {
    if (!this._last) return null;
    this.logger.info("startup: replays relay to renderer");
    this.send(this._last);
    return this._last;
  }

  /** Current buffered event (pull-based fallback). */
  current() {
    return this._last;
  }
}

module.exports = { StartupStateRelay };