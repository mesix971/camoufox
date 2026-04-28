import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyTheme, getStoredTheme } from "./themes";

// Apply the persisted theme before React mounts so there's no FOUC.
applyTheme(getStoredTheme());

const container = document.getElementById("root");
if (!container) throw new Error("no #root element in document");
createRoot(container).render(<App />);
