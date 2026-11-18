import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { DesktopSession } from "./DesktopSession";
import "./system-neutral.css";
import {
  applyTheme,
  readThemePreference,
  resolveTheme,
  syncWindowTheme,
  systemPrefersDark,
} from "./theme";

// Apply the stored theme before the first React paint so a light-theme user
// never sees a dark flash on launch.
const initialTheme = resolveTheme(readThemePreference(), systemPrefersDark());
applyTheme(initialTheme);
void syncWindowTheme(initialTheme);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DesktopSession><App /></DesktopSession>
  </React.StrictMode>,
);
