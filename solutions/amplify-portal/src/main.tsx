import React from "react";
import ReactDOM from "react-dom/client";
import { Amplify } from "aws-amplify";
import { Authenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import App from "./App";
import "./index.css";
import { I18nProvider } from "./i18n";

// Configure Amplify with generated outputs
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore - amplify_outputs.json may not exist before first sandbox deploy
import outputs from "../amplify_outputs.json";
Amplify.configure(outputs);

/**
 * Wrapper that shows loading skeleton until auth state is resolved.
 * The Authenticator component handles the loading → signIn → authenticated flow.
 * We wrap App inside it, so the blank flash is handled by Authenticator's built-in UI.
 * I18nProvider detects browser language or localStorage preference for 8-language support.
 */
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <Authenticator>
        <App />
      </Authenticator>
    </I18nProvider>
  </React.StrictMode>
);
