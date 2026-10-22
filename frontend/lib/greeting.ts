export type Greeting = "Good Morning" | "Good Afternoon" | "Good Evening" | "Good Night";

export function greetingForHour(hour: number): Greeting {
  if (hour >= 5 && hour < 12) return "Good Morning";
  if (hour >= 12 && hour < 17) return "Good Afternoon";
  if (hour >= 17 && hour < 21) return "Good Evening";
  return "Good Night";
}

export function millisecondsUntilNextGreeting(now: Date): number {
  const boundaries = [5, 12, 17, 21];
  const next = new Date(now);
  next.setMinutes(0, 0, 0);
  const hour = boundaries.find(value => value > now.getHours());
  if (hour === undefined) {
    next.setDate(next.getDate() + 1);
    next.setHours(5);
  } else {
    next.setHours(hour);
  }
  return Math.max(1000, next.getTime() - now.getTime());
}
