"use strict";

const GREETINGS = Object.freeze({
  morning: [
    "Good morning, Boss.",
    "Good morning, Boss. Ready to get started?",
    "Good morning, Boss. What are we working on today?",
  ],
  afternoon: [
    "Good afternoon, Boss.",
    "Good afternoon, Boss. How's the day going?",
    "Afternoon, Boss. Ready when you are.",
  ],
  evening: [
    "Good evening, Boss.",
    "Good evening, Boss. What are we building tonight?",
    "Evening, Boss. What's on the agenda?",
  ],
  night: [
    "You're up late, Boss.",
    "Late night, Boss. What are we working on?",
    "Hey, Boss. Still building?",
  ],
});

const GREETING_CONFIG = Object.freeze({
  morning_start: 5,
  morning_end: 11,
  afternoon_start: 12,
  afternoon_end: 16,
  evening_start: 17,
  evening_end: 20,
});

function bucketForHour(hour) {
  const c = GREETING_CONFIG;
  if (c.morning_start <= hour && hour <= c.morning_end) return "morning";
  if (c.afternoon_start <= hour && hour <= c.afternoon_end) return "afternoon";
  if (c.evening_start <= hour && hour <= c.evening_end) return "evening";
  return "night";
}

function pickGreeting(date = new Date(), { bucket } = {}) {
  const key = bucket || bucketForHour(date.getHours());
  const options = GREETINGS[key] || GREETINGS.night;
  const seed = Math.floor(date.getMinutes() / 5) % options.length;
  return options[seed];
}

function pickFullGreeting(date = new Date()) {
  const hour = date.getHours();
  const period = bucketForHour(hour);
  const options = GREETINGS[period] || GREETINGS.night;
  const variantIndex = Math.floor(date.getMinutes() / 5) % options.length;
  const baseGreeting = options[variantIndex];

  // Add follow-up based on time of day
  const followUps = {
    morning: [
      "Ready to build something?",
      "What are we working on today?",
      "How can I help?",
    ],
    afternoon: [
      "How's the day going?",
      "Ready when you are.",
      "What's next?",
    ],
    evening: [
      "What are we building tonight?",
      "What's on the agenda?",
      "How can I help?",
    ],
    night: [
      "What are we working on?",
      "Still building?",
      "How can I help?",
    ],
  };

  const followUpsList = followUps[period] || ["How can I help?"];
  const followUp = followUpsList[Math.floor(date.getMinutes() / 10) % followUpsList.length];

  return `${baseGreeting} ${followUp}`;
}

module.exports = { pickGreeting, bucketForHour, pickFullGreeting, GREETINGS, GREETING_CONFIG };