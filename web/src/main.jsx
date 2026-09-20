import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { adoptCode } from "./agent.js";
import "./styles.css";

// A code in the link is taken off the address bar before anything renders.
adoptCode();

createRoot(document.getElementById("root")).render(
  <StrictMode><App /></StrictMode>,
);
