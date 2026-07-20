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

import App from "../../src/App";

describe("App", () => {
  it("renders the portal title", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: /File Portal/i })
    ).toBeInTheDocument();
  });

  it("renders sidebar navigation with grouped sections", () => {
    render(<App />);
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
    render(<App />);
    const allFilesBtn = screen.getByText("All Files").closest("button");
    expect(allFilesBtn).toHaveAttribute("aria-current", "page");
  });

  it("switches sections on sidebar click", () => {
    render(<App />);
    const favoritesBtn = screen.getByText("Favorites").closest("button");
    fireEvent.click(favoritesBtn!);
    expect(favoritesBtn).toHaveAttribute("aria-current", "page");
  });

  it("displays the user email", () => {
    render(<App />);
    expect(screen.getByText("test@example.com")).toBeInTheDocument();
  });

  it("has a sign out button", () => {
    render(<App />);
    const signOut = screen.getByRole("button", { name: /sign out/i });
    expect(signOut).toBeInTheDocument();
  });

  it("has a sidebar toggle button", () => {
    render(<App />);
    const toggle = screen.getByRole("button", {
      name: /collapse navigation/i,
    });
    expect(toggle).toBeInTheDocument();
  });
});
