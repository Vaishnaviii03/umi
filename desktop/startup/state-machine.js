"use strict";

const STATES = Object.freeze({
  OFF: "OFF",
  LAUNCHING: "LAUNCHING",
  INITIALIZING: "INITIALIZING",
  LOADING_CONTEXT: "LOADING_CONTEXT",
  READY_TO_GREET: "READY_TO_GREET",
  GREETING: "GREETING",
  STARTUP_MEDIA: "STARTUP_MEDIA",
  READY: "READY",
  INITIALIZATION_ERROR: "INITIALIZATION_ERROR",
  MEDIA_ERROR: "MEDIA_ERROR",
  DATABASE_ERROR: "DATABASE_ERROR",
  LLM_ERROR: "LLM_ERROR",
  VOICE_ERROR: "VOICE_ERROR",
  PERMISSION_ERROR: "PERMISSION_ERROR",
});

const NORMAL_FLOW = [
  STATES.OFF,
  STATES.LAUNCHING,
  STATES.INITIALIZING,
  STATES.LOADING_CONTEXT,
  STATES.READY_TO_GREET,
  STATES.GREETING,
  STATES.STARTUP_MEDIA,
  STATES.READY,
];

const TERMINAL = new Set([STATES.READY]);

const ALLOWED_TRANSITIONS = Object.freeze({
  [STATES.OFF]: [STATES.LAUNCHING],
  [STATES.LAUNCHING]: [STATES.INITIALIZING, STATES.INITIALIZATION_ERROR, STATES.PERMISSION_ERROR],
  [STATES.INITIALIZING]: [STATES.LOADING_CONTEXT, STATES.INITIALIZATION_ERROR, STATES.LLM_ERROR, STATES.DATABASE_ERROR],
  [STATES.LOADING_CONTEXT]: [STATES.READY_TO_GREET, STATES.DATABASE_ERROR, STATES.LLM_ERROR],
  [STATES.READY_TO_GREET]: [STATES.GREETING],
  [STATES.GREETING]: [STATES.STARTUP_MEDIA, STATES.VOICE_ERROR],
  [STATES.STARTUP_MEDIA]: [STATES.READY, STATES.MEDIA_ERROR],
  [STATES.MEDIA_ERROR]: [STATES.READY],
  [STATES.VOICE_ERROR]: [STATES.STARTUP_MEDIA, STATES.READY],
  [STATES.INITIALIZATION_ERROR]: [],
  [STATES.DATABASE_ERROR]: [],
  [STATES.LLM_ERROR]: [],
  [STATES.PERMISSION_ERROR]: [],
});

class StartupStateMachine extends (require("events").EventEmitter) {
  constructor({ initialState = STATES.OFF } = {}) {
    super();
    this.state = initialState;
    this._softErrors = [];
  }

  get current() {
    return this.state;
  }

  get isTerminal() {
    return TERMINAL.has(this.state);
  }

  get softErrors() {
    return [...this._softErrors];
  }

  transition(next) {
    if (this.state === next) return;
    if (!STATES[next]) {
      throw new Error(`Unknown state: ${next}`);
    }
    const allowed = ALLOWED_TRANSITIONS[this.state] || [];
    if (!allowed.includes(next)) {
      throw new Error(`Invalid transition: ${this.state} -> ${next}`);
    }
    const previous = this.state;
    this.state = next;
    this.emit("change", { from: previous, to: next });
  }

  softError(state, error) {
    this._softErrors.push({ state, message: error instanceof Error ? error.message : String(error) });
    if (STATES[state]) {
      this.emit("soft-error", { state, message: this._softErrors[this._softErrors.length - 1].message });
    }
  }

  index() {
    return NORMAL_FLOW.indexOf(this.state);
  }
}

module.exports = { STATES, StartupStateMachine, NORMAL_FLOW };