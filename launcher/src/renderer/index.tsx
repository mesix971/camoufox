import { createRoot } from "react-dom/client";
import { App } from "./App";
import {
  applyLayout, applyTheme, getStoredLayout, getStoredTheme,
} from "./themes";

// Apply persisted theme + layout before React mounts so there's no FOUC.
applyTheme(getStoredTheme());
applyLayout(getStoredLayout());

const container = document.getElementById("root");
if (!container) throw new Error("no #root element in document");
createRoot(container).render(<App />);
