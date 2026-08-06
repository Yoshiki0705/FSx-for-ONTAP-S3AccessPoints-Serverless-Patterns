import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Mock Amplify modules
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({
    queries: { listFiles: vi.fn(), getJobStatus: vi.fn() },
    mutations: { startProcessing: vi.fn() },
    models: {
      Favorite: { list: vi.fn().mockResolvedValue({ data: [] }) },
      FileTag: { list: vi.fn().mockResolvedValue({ data: [] }) },
    },
  }),
}));

vi.mock("@aws-amplify/ui-react", () => ({
  useAuthenticator: () => ({
    user: { signInDetails: { loginId: "test@example.com" } },
    signOut: vi.fn(),
    authStatus: "authenticated",
  }),
  Authenticator: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@aws-amplify/ui-react-storage/browser", () => ({
  createStorageBrowser: () => ({ StorageBrowser: () => null }),
}));

vi.mock("aws-amplify/auth", () => ({
  fetchAuthSession: vi.fn().mockResolvedValue({ credentials: {} }),
}));

vi.mock("../../amplify/data/resource", () => ({}));

import { QueryClientProvider } from "@tanstack/react-query";
import App from "../../src/App";
import { createPortalQueryClient } from "../../src/lib/queryClient";
import { I18nProvider } from "../../src/i18n";

/**
 * Mirrors main.tsx: the panels fetch through TanStack Query, so the client has
 * to be in scope. A fresh client per render keeps one test's cache out of the
 * next one.
 */
function renderApp() {
  return render(
    <QueryClientProvider client={createPortalQueryClient()}>
      <I18nProvider>
        <App />
      </I18nProvider>
    </QueryClientProvider>
  );
}

describe("App", () => {
  it("renders the portal title", () => {
    renderApp();
    // Scope to the h1: the welcome tour also renders an h2 that contains
    // "Welcome to File Portal", which would otherwise match ambiguously.
    expect(
      screen.getByRole("heading", { level: 1, name: /File Portal/i })
    ).toBeInTheDocument();
  });

  it("renders sidebar navigation with grouped sections", () => {
    renderApp();
    const nav = screen.getByRole("navigation", { name: /Main navigation/i });
    expect(nav).toBeInTheDocument();

    // Check sidebar items exist
    expect(screen.getByText("All Files")).toBeInTheDocument();
    expect(screen.getByText("Favorites")).toBeInTheDocument();
    expect(screen.getByText("Upload")).toBeInTheDocument();
    expect(screen.getByText("AI Processing")).toBeInTheDocument();
    expect(screen.getByText("Audit Trail")).toBeInTheDocument();
  });

  it("marks the active section with aria-current", () => {
    renderApp();
    const allFilesBtn = screen.getByText("All Files").closest("button");
    expect(allFilesBtn).toHaveAttribute("aria-current", "page");
  });

  it("switches sections on sidebar click", () => {
    renderApp();
    const favoritesBtn = screen.getByText("Favorites").closest("button");
    fireEvent.click(favoritesBtn!);
    expect(favoritesBtn).toHaveAttribute("aria-current", "page");
  });

  it("displays the user email", () => {
    renderApp();
    expect(screen.getByText("test@example.com")).toBeInTheDocument();
  });

  it("has a sign out button", () => {
    renderApp();
    const signOut = screen.getByRole("button", { name: /sign out/i });
    expect(signOut).toBeInTheDocument();
  });

  it("has a sidebar toggle button", () => {
    renderApp();
    const toggle = screen.getByRole("button", {
      name: /collapse navigation/i,
    });
    expect(toggle).toBeInTheDocument();
  });
});
