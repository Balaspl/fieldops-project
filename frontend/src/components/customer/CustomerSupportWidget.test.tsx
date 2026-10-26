import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import CustomerSupportWidget from "./CustomerSupportWidget";

const chat = vi.hoisted(() => ({
  listCustomerChatConversations: vi.fn(),
  getCustomerChatConversation: vi.fn(),
  createCustomerChatConversation: vi.fn(),
  sendCustomerChatMessage: vi.fn(),
  deleteCustomerChatConversation: vi.fn(),
}));

vi.mock("../../services/customerChatService", () => chat);

describe("CustomerSupportWidget", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    chat.listCustomerChatConversations.mockResolvedValue([]);
    chat.createCustomerChatConversation.mockResolvedValue({ id: "conversation-id" });
    chat.sendCustomerChatMessage.mockResolvedValue({ conversation_id: "conversation-id", answer: "Your service request is being reviewed.", intent: "job_status", escalation: false });
  });

  it("opens accessibly, submits a message, and renders the response", async () => {
    render(<CustomerSupportWidget customerId="customer-1" />);
    expect(screen.getByRole("img", { name: "FieldOps support robot mascot" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open FieldOps Support Chat" }));
    expect(screen.getByRole("dialog", { name: "FieldOps Support" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Message FieldOps Support" }), { target: { value: "Check my latest request" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(Boolean(screen.queryByText("Your service request is being reviewed."))).toBe(true));
    expect(chat.sendCustomerChatMessage).toHaveBeenCalledWith("conversation-id", "Check my latest request", expect.any(String));
  });

  it("minimizes and reopens the panel", () => {
    render(<CustomerSupportWidget customerId="customer-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Open FieldOps Support Chat" }));
    fireEvent.click(screen.getByRole("button", { name: "Minimize chat" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reopen support chat" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("keeps all default suggestions after multiple answers and submits each one", async () => {
    render(<CustomerSupportWidget customerId="customer-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Open FieldOps Support Chat" }));
    const suggestions = screen.getByRole("region", { name: "Suggested questions" });
    expect(suggestions.querySelectorAll("button")).toHaveLength(10);
    fireEvent.click(screen.getByRole("button", { name: "What services does FieldOps offer?" }));
    await waitFor(() => expect(chat.sendCustomerChatMessage).toHaveBeenCalledWith(
      "conversation-id", "What services does FieldOps offer?", expect.any(String),
    ));
    expect(screen.getByRole("region", { name: "Suggested questions" }).querySelectorAll("button")).toHaveLength(10);
    fireEvent.click(screen.getByRole("button", { name: "How do I create a service request?" }));
    await waitFor(() => expect(chat.sendCustomerChatMessage).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("region", { name: "Suggested questions" }).querySelectorAll("button")).toHaveLength(10);
  });

  it("keeps suggestions visible when sending fails", async () => {
    chat.sendCustomerChatMessage.mockRejectedValueOnce(new Error("offline"));
    render(<CustomerSupportWidget customerId="customer-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Open FieldOps Support Chat" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Message FieldOps Support" }), { target: { value: "Some custom question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("region", { name: "Suggested questions" }).querySelectorAll("button")).toHaveLength(10);
  });

  it("deletes the chat session when closed and starts fresh when reopened", async () => {
    render(<CustomerSupportWidget customerId="customer-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Open FieldOps Support Chat" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Message FieldOps Support" }), { target: { value: "Check my latest request" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText("Your service request is being reviewed.");
    expect(localStorage.getItem("fieldops-chat:customer-1")).toBe("conversation-id");

    fireEvent.click(screen.getByRole("button", { name: "Close chat" }));
    await waitFor(() => expect(chat.deleteCustomerChatConversation).toHaveBeenCalledWith("conversation-id"));
    expect(localStorage.getItem("fieldops-chat:customer-1")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open FieldOps Support Chat" }));

    expect(screen.queryByText("Your service request is being reviewed.")).toBeNull();
    expect(screen.getByText("Hi, how can we help?")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Suggested questions" })).toBeTruthy();
    expect(chat.getCustomerChatConversation).not.toHaveBeenCalled();
    expect(chat.listCustomerChatConversations).not.toHaveBeenCalled();
  });

  it("restores history and default suggestions after a browser refresh", async () => {
    localStorage.setItem("fieldops-chat:customer-1", "conversation-id");
    chat.getCustomerChatConversation.mockResolvedValue({
      id: "conversation-id", title: null, status: "OPEN",
      messages: [{ id: 1, sender: "assistant", content: "Restored answer", created_at: new Date().toISOString() }],
    });
    const firstRender = render(<CustomerSupportWidget customerId="customer-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Open FieldOps Support Chat" }));
    await waitFor(() => expect(screen.getByText("Restored answer")).toBeTruthy());
    expect(screen.getByRole("region", { name: "Suggested questions" })).toBeTruthy();
    firstRender.unmount();

    render(<CustomerSupportWidget customerId="customer-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Open FieldOps Support Chat" }));
    await waitFor(() => expect(screen.getByText("Restored answer")).toBeTruthy());
    expect(screen.getByRole("region", { name: "Suggested questions" })).toBeTruthy();
  });
});
