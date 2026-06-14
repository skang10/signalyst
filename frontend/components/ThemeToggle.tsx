"use client";

import { useState } from "react";

type Theme = "gold" | "green";
const STORAGE_KEY = "signalyst-theme";

function applyTheme(theme: Theme) {
  if (theme === "gold") {
    document.documentElement.setAttribute("data-theme", "gold");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "green";
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "gold" ? "gold" : "green";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  const toggle = () => {
    const next: Theme = theme === "gold" ? "green" : "gold";
    setTheme(next);
    applyTheme(next);
    localStorage.setItem(STORAGE_KEY, next);
  };

  return (
    <button
      onClick={toggle}
      className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-500 hover:text-brand hover:border-brand transition-colors"
      aria-label="Toggle accent theme"
      title={`Switch to ${theme === "gold" ? "green" : "gold"} theme`}
    >
      {theme === "gold" ? "Gold" : "Green"}
    </button>
  );
}
