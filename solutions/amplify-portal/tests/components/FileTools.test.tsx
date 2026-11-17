import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { toolsQuery, toolsMutation, toolsUseCaseMutation } = vi.hoisted(() => ({
  toolsQuery: vi.fn(),
  toolsMutation: vi.fn(),
  toolsUseCaseMutation: vi.fn(),
}));
vi.mock("aws-amplify/data", () => ({
  generateClient: () => ({ queries: { toolsQuery }, mutations: { toolsMutation, toolsUseCaseMutation } }),
}));

import { FileTools } from "../../src/components/FileTools";
import { I18nProvider } from "../../src/i18n";

const minutesConfig = { languages: ["ja-JP", "en-US"], extensions: ["mp3", "mp4"], maxMegabytes: 200, minSpeakers: 2, maxSpeakers: 10 };
const videoConfig = {
  data: JSON.stringify({
    success: true,
    tools: { webExtract: true, image: false, useCases: true, video: true },
    video: { extensions: ["mp4", "mov"], maxMegabytes: 20, seconds: 25 },
  }),
};
const genConfig = {
  data: JSON.stringify({
    success: true,
    tools: { webExtract: true, image: false, useCases: true, videoGeneration: true },
    videoGeneration: { region: "us-west-2", modelId: "luma.ray-v2:0", crossRegion: true, aspectRatios: ["16:9", "9:16"], resolutions: ["540p", "720p"], maxPromptChars: 2000 },
  }),
};
const config = (image: boolean, code = false, minutes = false) => ({
  data: JSON.stringify({
    success: true,
    tools: { webExtract: true, image, useCases: true, code, minutes },
    minutes: minutes ? minutesConfig : null,
    code: code ? { maxRuns: 2, runSeconds: 12, totalSeconds: 25 } : null,
    image: image ? { region: "us-west-2", modelId: "stability.stable-image-core-v1:1", crossRegion: true } : null,
  }),
});

function renderTools(props: Partial<Parameters<typeof FileTools>[0]> = {}) {
  return render(
    <I18nProvider>
      <FileTools selectedFileKey="team-a/policy.md" selectedFolder="team-a/" canWrite={false} canSaveUseCases={false} {...props} />
    </I18nProvider>,
  );
}

beforeEach(() => {
  toolsQuery.mockReset();
  toolsMutation.mockReset();
  toolsUseCaseMutation.mockReset();
  localStorage.setItem("portal-locale", "en");
});

describe("FileTools", () => {
  it("hides image generation while it is disabled", async () => {
    toolsQuery.mockResolvedValue(config(false));
    renderTools();
    await waitFor(() => expect(toolsQuery).toHaveBeenCalled());
    expect(screen.getByRole("tab", { name: /Translate/ })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: /Image generation/ })).toBeNull();
  });

  it("states that image generation runs outside Japan when it is cross-Region", async () => {
    toolsQuery.mockResolvedValue(config(true));
    renderTools({ canWrite: true, initialTab: "image" });
    await screen.findByRole("note");
    expect(screen.getByRole("note").textContent).toContain("us-west-2");
    expect(screen.getByRole("note").textContent).toContain("outside Japan");
  });

  it("fills the prompt from the suggestion, and starts from the selected image with a strength", async () => {
    const i2i = { modelId: "stability.sd3-5-large-v1:0", extensions: ["png", "jpg"], maxMegabytes: 5, strength: 0.35 };
    toolsQuery.mockImplementation(async ({ action }: { action: string }) => {
      if (action === "config") {
        return { data: JSON.stringify({ success: true, tools: { webExtract: true, image: true, useCases: true }, image: { region: "us-west-2", modelId: "stability.stable-image-core-v1:1", crossRegion: true, imageToImage: i2i } }) };
      }
      return { data: JSON.stringify({ success: true, prompt: "server racks, blue light", negativePrompt: "text", comment: "dark" }) };
    });
    toolsMutation.mockResolvedValue({ data: JSON.stringify({ success: true, key: "team-a/x.png", imageBase64: "" }) });
    renderTools({ canWrite: true, initialTab: "image", selectedFileKey: "team-a/photo.png" });
    fireEvent.change(await screen.findByLabelText(/What you want to draw/), { target: { value: "night data center" } });
    fireEvent.click(screen.getByRole("button", { name: /Suggest a prompt/ }));
    await waitFor(() => expect((screen.getByLabelText("Describe the image") as HTMLTextAreaElement).value).toBe("server racks, blue light"));
    fireEvent.click(screen.getByLabelText("Start from the selected image"));
    expect(screen.queryByLabelText(/Aspect ratio/)).toBeNull();
    expect(screen.getByRole("note").textContent).toContain("sd3-5-large");
    fireEvent.click(screen.getByRole("button", { name: /Generate image/ }));
    await waitFor(() => expect(toolsMutation).toHaveBeenCalled());
    expect(JSON.parse(toolsMutation.mock.calls[0][0].params)).toMatchObject({ sourceKey: "team-a/photo.png", strength: 0.35, prompt: "server racks, blue light" });
  });

  it("sends only the file key, through the query, when translating the selected file", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? config(false) : { data: JSON.stringify({ success: true, result: "translated text" }) },
    );
    renderTools();
    fireEvent.click(await screen.findByRole("button", { name: /^Translate$/ }));
    await screen.findByText("translated text");
    const call = toolsQuery.mock.calls.find((c) => c[0].action === "translate")![0];
    expect(JSON.parse(call.params)).toMatchObject({ key: "team-a/policy.md", target: "en" });
    expect(JSON.parse(call.params).text).toBeUndefined();
    expect(toolsMutation).not.toHaveBeenCalled();
  });

  it("offers no folder writes without write permission", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? config(false) : { data: JSON.stringify({ success: true, result: "translated text" }) },
    );
    renderTools({ canWrite: false });
    fireEvent.click(await screen.findByRole("button", { name: /^Translate$/ }));
    await screen.findByText("translated text");
    expect(screen.queryByRole("button", { name: /Save to the folder/ })).toBeNull();
  });

  it("lets a viewer save a use case, through the use-case mutation only", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? config(false) : { data: JSON.stringify({ success: true, useCases: [] }) },
    );
    toolsUseCaseMutation.mockResolvedValue({ data: JSON.stringify({ success: true, useCase: {} }) });
    renderTools({ canWrite: false, canSaveUseCases: true, initialTab: "useCases" });
    fireEvent.click(await screen.findByRole("button", { name: /New use case/ }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Brief" } });
    fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() => expect(toolsUseCaseMutation).toHaveBeenCalled());
    expect(toolsUseCaseMutation.mock.calls[0][0].action).toBe("saveUseCase");
    expect(toolsMutation).not.toHaveBeenCalled();
  });

  it("says a portal role is needed when the account cannot save use cases", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? config(false) : { data: JSON.stringify({ success: true, useCases: [] }) },
    );
    renderTools({ canWrite: false, canSaveUseCases: false, initialTab: "useCases" });
    expect(await screen.findByText(/needs a portal role/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /New use case/ })).toBeNull();
  });

  it("hides code execution unless the server enables it", async () => {
    toolsQuery.mockResolvedValue(config(false));
    renderTools();
    await waitFor(() => expect(toolsQuery).toHaveBeenCalled());
    expect(screen.queryByRole("tab", { name: /Run code/ })).toBeNull();
  });
  it("states the limits, and sends only the file key and the task through the query", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config"
        ? config(false, true)
        : { data: JSON.stringify({ success: true, completed: true, reason: "", result: "March is highest", code: "print(1)", runs: [{ ok: true, timedOut: false, seconds: 1.2, stdout: "3\n", stderr: "" }] }) },
    );
    renderTools({ initialTab: "code" });
    const note = await screen.findByRole("note");
    expect(note.textContent).toContain("Up to 2 runs per request, 12 seconds each");
    expect(note.textContent).toContain("no network");
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "find the top month" } });
    fireEvent.click(screen.getByRole("button", { name: /^Run$/ }));
    await screen.findByText("March is highest");
    const sent = toolsQuery.mock.calls.find((c) => c[0].action === "code")![0];
    expect(JSON.parse(sent.params)).toEqual({ key: "team-a/policy.md", task: "find the top month" });
    expect(toolsMutation).not.toHaveBeenCalled();
  });
  it("says so when the program could not be fixed in time", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config"
        ? config(false, true)
        : { data: JSON.stringify({ success: true, completed: false, reason: "timeout", result: "", code: "while True: pass", runs: [{ ok: false, timedOut: true, seconds: 12, stdout: "", stderr: "" }] }) },
    );
    renderTools({ initialTab: "code" });
    await screen.findByRole("note");
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /^Run$/ }));
    expect((await screen.findByRole("alert")).textContent).toContain("did not finish within its time limit");
  });

  it("hides minutes unless the server enables them", async () => {
    toolsQuery.mockResolvedValue(config(false));
    renderTools();
    await waitFor(() => expect(toolsQuery).toHaveBeenCalled());
    expect(screen.queryByRole("tab", { name: /Minutes/ })).toBeNull();
  });
  it("starts a minutes job with only the file key, then polls until the minutes arrive", async () => {
    let polls = 0;
    toolsQuery.mockImplementation(async ({ action }: { action: string }) => {
      if (action === "config") return config(false, false, true);
      if (action === "minutes-start") return { data: JSON.stringify({ success: true, jobName: "portal-minutes-x", status: "IN_PROGRESS" }) };
      polls += 1;
      return { data: JSON.stringify(polls < 2 ? { success: true, status: "IN_PROGRESS" } : { success: true, status: "COMPLETED", result: "## Decisions", truncated: false }) };
    });
    renderTools({ initialTab: "minutes", selectedFileKey: "team-a/meeting.mp3" });
    await screen.findByRole("note");
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      fireEvent.click(screen.getByRole("button", { name: /Make minutes/ }));
      await screen.findByRole("status");
      await vi.advanceTimersByTimeAsync(5000);
      expect(screen.queryByText("## Decisions")).toBeNull();
      await vi.advanceTimersByTimeAsync(5000);
    } finally {
      vi.useRealTimers();
    }
    await screen.findByText("## Decisions");
    const start = toolsQuery.mock.calls.find((c) => c[0].action === "minutes-start")![0];
    expect(JSON.parse(start.params)).toEqual({ key: "team-a/meeting.mp3", language: "ja-JP", speakers: 2 });
    const status = toolsQuery.mock.calls.find((c) => c[0].action === "minutes-status")![0];
    expect(JSON.parse(status.params)).toEqual({ jobName: "portal-minutes-x", style: "minutes" });
    expect(toolsMutation).not.toHaveBeenCalled();
  });
  it("sends the chosen style, and redoes a finished job in another style without a new transcription", async () => {
    const styled = { ...minutesConfig, styles: ["minutes", "transcript", "article", "faq"] };
    toolsQuery.mockImplementation(async ({ action, params }: { action: string; params: string }) => {
      if (action === "config") return { data: JSON.stringify({ success: true, tools: { webExtract: true, image: false, useCases: true, minutes: true }, minutes: styled }) };
      if (action === "minutes-start") return { data: JSON.stringify({ success: true, jobName: "portal-minutes-x", status: "IN_PROGRESS" }) };
      const style = JSON.parse(params).style;
      return { data: JSON.stringify({ success: true, status: "COMPLETED", result: `result in ${style}`, style, truncated: false }) };
    });
    renderTools({ initialTab: "minutes", selectedFileKey: "team-a/meeting.mp3" });
    await screen.findByRole("note");
    fireEvent.change(await screen.findByLabelText("Output style"), { target: { value: "faq" } });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      fireEvent.click(screen.getByRole("button", { name: /Make minutes/ }));
      await screen.findByRole("status");
      await vi.advanceTimersByTimeAsync(5000);
      await screen.findByText("result in faq");
      expect(screen.queryByRole("button", { name: /Redo in this style/ })).toBeNull();
      fireEvent.change(screen.getByLabelText("Output style"), { target: { value: "article" } });
      fireEvent.click(screen.getByRole("button", { name: /Redo in this style/ }));
      await vi.advanceTimersByTimeAsync(5000);
    } finally {
      vi.useRealTimers();
    }
    await screen.findByText("result in article");
    const starts = toolsQuery.mock.calls.filter((c) => c[0].action === "minutes-start");
    expect(starts).toHaveLength(1);
    const statuses = toolsQuery.mock.calls.filter((c) => c[0].action === "minutes-status").map((c) => JSON.parse(c[0].params));
    expect(statuses).toEqual([{ jobName: "portal-minutes-x", style: "faq" }, { jobName: "portal-minutes-x", style: "article" }]);
  });
  it("shows the reason when the transcription fails", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) => {
      if (action === "config") return config(false, false, true);
      if (action === "minutes-start") return { data: JSON.stringify({ success: true, jobName: "portal-minutes-x" }) };
      return { data: JSON.stringify({ success: true, status: "FAILED", reason: "bad audio" }) };
    });
    renderTools({ initialTab: "minutes", selectedFileKey: "team-a/meeting.mp3" });
    await screen.findByRole("note");
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      fireEvent.click(screen.getByRole("button", { name: /Make minutes/ }));
      await screen.findByRole("status");
      await vi.advanceTimersByTimeAsync(5000);
    } finally {
      vi.useRealTimers();
    }
    expect((await screen.findByRole("alert")).textContent).toContain("bad audio");
  });

  it("hides video analysis unless the server enables it", async () => {
    toolsQuery.mockResolvedValue(config(false));
    renderTools();
    await waitFor(() => expect(toolsQuery).toHaveBeenCalled());
    expect(screen.queryByRole("tab", { name: /Video analysis/ })).toBeNull();
  });
  it("states the size and time limits and the on-screen text caveat, and sends one call", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config" ? videoConfig : { data: JSON.stringify({ success: true, result: "A test pattern." }) },
    );
    renderTools({ initialTab: "video", selectedFileKey: "team-a/clip.mp4" });
    const note = await screen.findByRole("note");
    expect(note.textContent).toContain("Up to 20 MB");
    expect(note.textContent).toContain("25 seconds");
    expect(note.textContent).toContain("last character");
    expect(note.textContent).toContain("audio is not analyzed");
    fireEvent.click(screen.getByRole("button", { name: /Analyze the video/ }));
    await screen.findByText("A test pattern.");
    const sent = toolsQuery.mock.calls.find((c) => c[0].action === "video")![0];
    expect(JSON.parse(sent.params).key).toBe("team-a/clip.mp4");
    expect(toolsQuery.mock.calls.some((c) => /video-(start|status)/.test(c[0].action))).toBe(false);
  });
  it("shows the refusal when the video is over the limit", async () => {
    toolsQuery.mockImplementation(async ({ action }: { action: string }) =>
      action === "config"
        ? videoConfig
        : { data: JSON.stringify({ success: false, error: "file too large for synchronous analysis (limit 20 MB)" }) },
    );
    renderTools({ initialTab: "video", selectedFileKey: "team-a/big.mp4" });
    await screen.findByRole("note");
    fireEvent.click(screen.getByRole("button", { name: /Analyze the video/ }));
    expect((await screen.findByRole("alert")).textContent).toContain("limit 20 MB");
  });

  it("hides video generation unless the server enables it", async () => {
    toolsQuery.mockResolvedValue(config(false));
    renderTools();
    await waitFor(() => expect(toolsQuery).toHaveBeenCalled());
    expect(screen.queryByRole("tab", { name: /Video generation/ })).toBeNull();
  });
  it("says before anything is sent that video generation runs outside Japan, then polls and plays the video", async () => {
    let polls = 0;
    toolsQuery.mockImplementation(async ({ action }: { action: string }) => {
      if (action === "config") return genConfig;
      if (action === "video-generate-start") return { data: JSON.stringify({ success: true, invocationArn: "arn:aws:bedrock:us-west-2:123456789012:async-invoke/abc", status: "IN_PROGRESS" }) };
      polls += 1;
      return { data: JSON.stringify(polls < 2 ? { success: true, status: "IN_PROGRESS" } : { success: true, status: "COMPLETED", url: "https://signed.example/output.mp4" }) };
    });
    renderTools({ initialTab: "videoGen" });
    const note = await screen.findByRole("note");
    expect(note.textContent).toContain("us-west-2");
    expect(note.textContent).toContain("outside Japan");
    expect(toolsQuery.mock.calls.some((c) => c[0].action === "video-generate-start")).toBe(false);
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "a data center" } });
    fireEvent.change(screen.getByLabelText("Resolution"), { target: { value: "720p" } });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      fireEvent.click(screen.getByRole("button", { name: /Generate the video/ }));
      await screen.findByRole("status");
      await vi.advanceTimersByTimeAsync(10000);
    } finally {
      vi.useRealTimers();
    }
    await waitFor(() => expect(document.querySelector("video")?.getAttribute("src")).toBe("https://signed.example/output.mp4"));
    const start = toolsQuery.mock.calls.find((c) => c[0].action === "video-generate-start")![0];
    expect(JSON.parse(start.params)).toEqual({ prompt: "a data center", aspectRatio: "16:9", resolution: "720p" });
    expect(toolsMutation).not.toHaveBeenCalled();
  });
});
