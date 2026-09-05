"use strict";

const GREETINGS = Object.freeze({
  morning: [
    "Good morning. I'm online.",
    "Good morning. What are we working on today?",
    "Good morning. Systems are online — how can I help?",
  ],
  afternoon: [
    "Good afternoon. I'm ready.",
    "Good afternoon. What can I do for you?",
    "Good afternoon. Systems are online.",
  ],
  evening: [
    "Good evening. I'm online.",
    "Good evening. How was your day?",
    "Good evening. What should we take care of?",
  ],
  night: [
    "It's late — I'm here if you need me.",
    "Good night shift. Systems are online.",
    "I'm online whenever you need me.",
  ],
});

function bucketForHour(hour) {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 21) return "evening";
  return "night";
}

function pickGreeting(date = new Date(), { bucket } = {}) {
  const key = bucket || bucketForHour(date.getHours());
  const options = GREETINGS[key] || GREETINGS.night;
  const seed = Math.floor(date.getMinutes() / 5) % options.length;
  return options[seed];
}

module.exports = { pickGreeting, bucketForHour, GREETINGS };