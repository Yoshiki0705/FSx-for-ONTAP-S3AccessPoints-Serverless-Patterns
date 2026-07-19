import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Mock Amplify modules
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({
    queries: { listFiles: vi.fn(), getJobStatus: vi.fn() },
    mutations: { startProcessing: vi.fn() },
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

vi.mock("../../amplify/data/resource", () => ({}));

import App from "../../src/App";

describe("App", () => {
  it("renders the portal header", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /FSx for ONTAP File Portal/i })).toBeInTheDocument();
  });

  it("renders navigation with correct ARIA roles", () => {
    render(<App />);
    const tablist = screen.getByRole("tablist");
    expect(tablist).toBeInTheDocument();
    expect(tablist).toHaveAttribute("aria-label", "Portal navigation");

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(6);
    expect(tabs[0]).toHaveTextContent("Files");
    expect(tabs[1]).toHaveTextContent("Upload");
    expect(tabs[2]).toHaveTextContent("Process");
    expect(tabs[3]).toHaveTextContent("Results");
    expect(tabs[4]).toHaveTextContent("History");
    expect(tabs[5]).toHaveTextContent("Analytics");
  });

  it("marks the active tab with aria-selected", () => {
    render(<App />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");
    expect(tabs[2]).toHaveAttribute("aria-selected", "false");
  });

  it("switches tabs on click", async () => {
    render(<App />);
    const processTab = screen.getByRole("tab", { name: "Process" });

    fireEvent.click(processTab);

    expect(processTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Files" })).toHaveAttribute("aria-selected", "false");
  });

  it("displays the user email", () => {
    render(<App />);
    expect(screen.getByText("test@example.com")).toBeInTheDocument();
  });

  it("has a sign out button with aria-label", () => {
    render(<App />);
    const signOut = screen.getByRole("button", { name: /sign out/i });
    expect(signOut).toBeInTheDocument();
  });
});
