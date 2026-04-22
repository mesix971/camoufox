import { createRoot } from "react-dom/client";
import { App } from "./App";

const container = document.getElementById("root");
if (!container) throw new Error("no #root element in document");
createRoot(container).render(<App />);
