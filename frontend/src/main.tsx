import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./styles/tokens.css";
import "./styles.css";

createRoot(document.getElementById("root")!).render(<App />);
