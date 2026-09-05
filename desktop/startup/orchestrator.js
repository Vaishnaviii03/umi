"use strict";

const { STATES, StartupStateMachine } = require("./state-machine");

class StartupOrchestrator {
  constructor({
    stateMachine,
    backend,
    frontend,
    greeting,
    player,
    emit = () => {},
    logger = console,
  }) {
    this.stateMachine = stateMachine || new StartupStateMachine();
    this.backend = backend;
    this.frontend = frontend;
    this.greeting = greeting;
    this.player = player;
    this.emit = emit;
    this.logger = logger;
    this._context = {};
  }

  async start() {
    this.logger.info("startup: beginning");
    this.stateMachine.transition(STATES.LAUNCHING);
    this._push(STATES.LAUNCHING);

    await this._step("frontend", STATES.INITIALIZING, async () => {
      await this.frontend.ensureRunning();
      return { spawned: true };
    });

    await this._step("backend", STATES.INITIALIZING, async () => {
      await this.backend.ensureRunning();
      return { spawned: true };
    });

    await this._step("context", STATES.LOADING_CONTEXT, async () => {
      this._context.timeOfDay = this.greeting.bucketForHour(new Date().getHours());
      this._context.startedAt = new Date().toISOString();
      return this._context;
    });

    this.stateMachine.transition(STATES.READY_TO_GREET);
    this._push(STATES.READY_TO_GREET, this._context);

    const greeting = this.greeting.pickGreeting(new Date(), this._context);
    this.stateMachine.transition(STATES.GREETING);
    this._push(STATES.GREETING, { ...this._context, greeting });

    this.stateMachine.transition(STATES.STARTUP_MEDIA);
    this._push(STATES.STARTUP_MEDIA, this._context);

    try {
      const result = await this.player.play();
      if (!result.started) {
        this.logger.info(`startup-media: skipped (${result.reason})`);
      }
    } catch (err) {
      this.logger.warn(`startup-media: failed (${err.message}) — continuing`);
      this.stateMachine.softError(STATES.MEDIA_ERROR, err);
      this.stateMachine.transition(STATES.MEDIA_ERROR);
    }

    try {
      await this.stateMachine.transition(STATES.READY);
      this._push(STATES.READY, this._context);
      this.logger.info("startup: ready");
    } catch (err) {
      this.stateMachine.softError(STATES.INITIALIZATION_ERROR, err);
      this.stateMachine.transition(STATES.INITIALIZATION_ERROR);
      this._push(STATES.INITIALIZATION_ERROR, this._context);
      throw err;
    }
  }

  async _step(name, nextState, fn) {
    try {
      this.stateMachine.transition(nextState);
      const data = await fn();
      this._push(this.stateMachine.current, data);
      return data;
    } catch (err) {
      this.logger.error(`startup: ${name} failed (${err.message})`);
      this.stateMachine.softError(this.stateMachine.current, err);
      try {
        this.stateMachine.transition(STATES.INITIALIZATION_ERROR);
      } catch {
        /* already in a terminal error state */
      }
      this._push(this.stateMachine.current, this._context);
      throw err;
    }
  }

  _push(state, data = {}) {
    this.emit({
      state,
      greeting: data.greeting || null,
      context: this._context,
      softErrors: this.stateMachine.softErrors,
    });
  }

  async stop() {
    this.player.stop();
    this.frontend.stop();
    this.backend.stop();
  }
}

module.exports = { StartupOrchestrator };