import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// Mount the React app into the single root element from index.html.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
