import React from "react";
import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import LoginPage from "../LoginPage";
import api from "../../services/api";

const authMocks = vi.hoisted(() => ({
  authenticateWithTokens: vi.fn(),
  clearError: vi.fn(),
}));

vi.mock("../../services/api", () => ({
  default: {
    post: vi.fn(),
  },
}));

vi.mock("../../store/authStore", () => ({
  default: () => ({
    authenticateWithTokens:
      authMocks.authenticateWithTokens,
    isLoading: false,
    error: null,
    clearError: authMocks.clearError,
  }),
}));

const mockedPost = vi.mocked(api.post);

const customerUser = {
  id: "customer-101",
  email: "customer@example.com",
  first_name: "Customer",
  last_name: "User",
  role: "customer",
  tenant_id: "customer-tenant-101",
  organization_name: null,
};

const renderLoginPage = () =>
  render(
    <LoginPage
      onCreateOrganization={vi.fn()}
    />,
  );

const fillLoginForm = (
  email = "customer@example.com",
  password = "CustomerPassword123!",
) => {
  fireEvent.change(
    screen.getByPlaceholderText(
      "you@company.com",
    ),
    {
      target: {
        value: email,
      },
    },
  );

  fireEvent.change(
    screen.getByPlaceholderText(
      "Enter your password",
    ),
    {
      target: {
        value: password,
      },
    },
  );
};

const clickNormalLogin = () => {
  fireEvent.click(
    screen.getByRole("button", {
      name: "Sign In",
    }),
  );
};

describe("LoginPage - customer authentication", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("sends normalized credentials and passes the backend customer identity to auth state", async () => {
    mockedPost.mockResolvedValueOnce({
      data: {
        access_token:
          "customer-access-token",
        refresh_token:
          "customer-refresh-token",
        user: customerUser,
      },
    } as any);

    renderLoginPage();

    fillLoginForm(
      "  CUSTOMER@EXAMPLE.COM  ",
    );

    clickNormalLogin();

    await waitFor(() => {
      expect(
        mockedPost,
      ).toHaveBeenCalledWith(
        "/auth/login",
        {
          email:
            "customer@example.com",
          password:
            "CustomerPassword123!",
          trusted_device_token:
            undefined,
        },
      );
    });

    expect(
      authMocks.authenticateWithTokens,
    ).toHaveBeenCalledTimes(1);

    expect(
      authMocks.authenticateWithTokens,
    ).toHaveBeenCalledWith(
      "customer-access-token",
      "customer-refresh-token",
      expect.objectContaining({
        id: "customer-101",
        role: "customer",
        tenant_id:
          "customer-tenant-101",
      }),
    );
  });

  it("prevents duplicate submission and shows the loading state while login is pending", async () => {
    let resolveLogin:
      | ((value: unknown) => void)
      | undefined;

    mockedPost.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveLogin = resolve;
        }),
    );

    renderLoginPage();

    fillLoginForm();

    clickNormalLogin();

    await waitFor(() => {
      expect(
        mockedPost,
      ).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByText(
        /signing in/i,
      ),
    ).toBeTruthy();

    const loadingButton =
      screen.getByRole("button", {
        name: /signing in/i,
      });

    expect(
      loadingButton.hasAttribute(
        "disabled",
      ),
    ).toBe(true);

    fireEvent.click(
      loadingButton,
    );

    expect(
      mockedPost,
    ).toHaveBeenCalledTimes(1);

    expect(
      authMocks.authenticateWithTokens,
    ).not.toHaveBeenCalled();

    resolveLogin?.({
      data: {
        access_token:
          "customer-access-token",
        refresh_token:
          "customer-refresh-token",
        user: customerUser,
      },
    });
  });

  it("shows a safe authentication error and does not authenticate after a 401", async () => {
    mockedPost.mockRejectedValueOnce({
      response: {
        status: 401,
        data: {
          detail:
            "Invalid email or password",
        },
      },
    });

    renderLoginPage();

    fillLoginForm(
      "customer@example.com",
      "wrong-password",
    );

    clickNormalLogin();

    expect(
      await screen.findByText(
        "Invalid email or password",
      ),
    ).toBeTruthy();

    expect(
      authMocks.authenticateWithTokens,
    ).not.toHaveBeenCalled();

    expect(
      localStorage.getItem(
        "access_token",
      ),
    ).toBeNull();

    expect(
      localStorage.getItem(
        "tenant_id",
      ),
    ).toBeNull();
  });

  it("surfaces a backend permission denial without creating a client-side tenant or customer scope", async () => {
    mockedPost.mockRejectedValueOnce({
      response: {
        status: 403,
        data: {
          detail:
            "Customer access denied",
        },
      },
    });

    renderLoginPage();

    fillLoginForm();

    clickNormalLogin();

    expect(
      await screen.findByText(
        "Customer access denied",
      ),
    ).toBeTruthy();

    expect(
      authMocks.authenticateWithTokens,
    ).not.toHaveBeenCalled();

    expect(
      localStorage.getItem(
        "tenant_id",
      ),
    ).toBeNull();

    expect(
      localStorage.getItem(
        "user",
      ),
    ).toBeNull();
  });

  it("shows the MFA challenge when the backend requires MFA and does not authenticate prematurely", async () => {
    mockedPost.mockResolvedValueOnce({
      data: {
        status: "MFA_REQUIRED",
        challenge:
          "customer-mfa-challenge",
      },
    } as any);

    renderLoginPage();

    fillLoginForm();

    clickNormalLogin();

    expect(
      await screen.findByText(
        "Multi-Factor Authentication",
      ),
    ).toBeTruthy();

    expect(
      authMocks.authenticateWithTokens,
    ).not.toHaveBeenCalled();

    expect(
      localStorage.getItem(
        "access_token",
      ),
    ).toBeNull();
  });
});