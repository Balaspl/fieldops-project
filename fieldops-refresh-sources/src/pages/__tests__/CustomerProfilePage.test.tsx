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

import CustomerProfilePage from "../customer/CustomerProfilePage";
import {
  getCustomerProfile,
  createCustomerProfile,
  updateCustomerProfile,
  reverseLocation,
} from "../../services/customerPortalService";

const authMocks = vi.hoisted(() => ({
  user: {
    id: "customer-101",
    email: "customer@gmail.com",
    first_name: "Customer",
    last_name: "User",
    role: "customer",
    tenant_id: "tenant-101",
    organization_name: null,
  },
}));

vi.mock("../../store/authStore", () => ({
  default: () => ({
    user: authMocks.user,
  }),
}));

vi.mock("../../services/customerPortalService", () => ({
  getCustomerProfile: vi.fn(),
  createCustomerProfile: vi.fn(),
  updateCustomerProfile: vi.fn(),
  reverseLocation: vi.fn(),
}));

const mockedGetProfile =
  vi.mocked(getCustomerProfile);

const mockedCreateProfile =
  vi.mocked(createCustomerProfile);

const mockedUpdateProfile =
  vi.mocked(updateCustomerProfile);

const mockedReverseLocation =
  vi.mocked(reverseLocation);

const existingProfile = {
  id: "profile-101",
  user_id: "customer-101",
  tenant_id: "tenant-101",
  full_name: "Customer User",
  mobile_number: "9876543210",
  address: "12 Main Street",
  city: "Chennai",
  state: "Tamil Nadu",
  pincode: "600001",
  company_name: "FieldOps Customer",
  profile_completed: true,
  email: "customer@gmail.com",
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
};

const incompleteProfile = {
  ...existingProfile,
  id: "",
  full_name: "Customer User",
  mobile_number: "",
  address: null,
  city: null,
  state: null,
  pincode: null,
  company_name: null,
  profile_completed: false,
};

const renderPage = () =>
  render(<CustomerProfilePage />);

describe("CustomerProfilePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads and maps the backend-authoritative customer profile", async () => {
    mockedGetProfile.mockResolvedValueOnce({
      data: existingProfile,
    } as any);

    renderPage();

    expect(
      screen.getByRole("status"),
    ).toBeTruthy();

    expect(
      await screen.findByText(
        "Edit Profile",
      ),
    ).toBeTruthy();

    expect(
      screen.getByPlaceholderText(
        "Enter your full name",
      ),
    ).toHaveProperty(
      "value",
      "Customer User",
    );

    expect(
      screen.getByPlaceholderText(
        "10 digit mobile number",
      ),
    ).toHaveProperty(
      "value",
      "9876543210",
    );

    expect(
      screen.getByDisplayValue(
        "12 Main Street",
      ),
    ).toBeTruthy();

    expect(
      mockedGetProfile,
    ).toHaveBeenCalledTimes(1);
  });

  it("shows the create-profile state when the backend reports an incomplete profile", async () => {
    mockedGetProfile.mockResolvedValueOnce({
      data: incompleteProfile,
    } as any);

    renderPage();

    expect(
      await screen.findByText(
        "Complete Your Profile",
      ),
    ).toBeTruthy();

    expect(
      screen.getByPlaceholderText(
        "Enter your full name",
      ),
    ).toHaveProperty(
      "value",
      "Customer User",
    );
  });

  it("shows the loading state while the backend profile request is pending", async () => {
    let resolveProfile:
      | ((value: unknown) => void)
      | undefined;

    mockedGetProfile.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveProfile = resolve;
        }) as any,
    );

    renderPage();

    expect(
      screen.getByRole("status").textContent,
    ).toContain(
      "Loading customer profile...",
    );

    resolveProfile?.({
      data: existingProfile,
    });

    await waitFor(() => {
      expect(
        screen.getByText(
          "Edit Profile",
        ),
      ).toBeTruthy();
    });
  });

  it("shows a safe error and retry control when profile loading fails", async () => {
    mockedGetProfile.mockRejectedValueOnce({
      response: {
        status: 403,
      },
    });

    renderPage();

    expect(
      (await screen.findByRole("alert"))
        .textContent,
    ).toContain(
      "You do not have permission to access your customer profile.",
    );

    expect(
      screen.getByRole("button", {
        name: "Retry",
      }),
    ).toBeTruthy();
  });

  it("rejects invalid customer input before sending a profile mutation", async () => {
    mockedGetProfile.mockResolvedValueOnce({
      data: existingProfile,
    } as any);

    renderPage();

    await screen.findByText(
      "Edit Profile",
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        "Enter your full name",
      ),
      {
        target: {
          value: "Customer123",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Save Changes",
      }),
    );

    expect(
      (await screen.findByRole("alert"))
        .textContent,
    ).toContain(
      "Full name must contain letters and spaces only",
    );

    expect(
      mockedUpdateProfile,
    ).not.toHaveBeenCalled();
  });

  it("creates a profile and reloads the saved backend representation", async () => {
    mockedGetProfile
      .mockResolvedValueOnce({
        data: incompleteProfile,
      } as any)
      .mockResolvedValueOnce({
        data: {
          ...existingProfile,
          company_name: "New Company",
        },
      } as any);

    mockedCreateProfile.mockResolvedValueOnce(
      {} as any,
    );

    renderPage();

    await screen.findByText(
      "Complete Your Profile",
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        "10 digit mobile number",
      ),
      {
        target: {
          value: "9876543210",
        },
      },
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        "Enter your address",
      ),
      {
        target: {
          value: "12 Main Street",
        },
      },
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        "Enter your city",
      ),
      {
        target: {
          value: "Chennai",
        },
      },
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        "Enter your state",
      ),
      {
        target: {
          value: "Tamil Nadu",
        },
      },
    );

    fireEvent.change(
      screen.getByPlaceholderText(
        "6 digit pincode",
      ),
      {
        target: {
          value: "600001",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Complete Profile",
      }),
    );

    await waitFor(() => {
      expect(
        mockedCreateProfile,
      ).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name:
            "Customer User",
          mobile_number:
            "9876543210",
          address:
            "12 Main Street",
          city: "Chennai",
          state: "Tamil Nadu",
          pincode: "600001",
        }),
      );
    });

    expect(
      mockedGetProfile,
    ).toHaveBeenCalledTimes(2);
  });


  it("fills the address from the browser current location", async () => {
    mockedGetProfile.mockResolvedValueOnce({
      data: existingProfile,
    } as any);

    mockedReverseLocation.mockResolvedValueOnce({
      data: {
        verified: true,
        address: "Detected Current Address",
        latitude: 13.0827,
        longitude: 80.2707,
      },
    } as any);

    const getCurrentPosition = vi.fn((
      success: (position: GeolocationPosition) => void,
    ) => {
      success({
        coords: {
          latitude: 13.0827,
          longitude: 80.2707,
          accuracy: 10,
          altitude: null,
          altitudeAccuracy: null,
          heading: null,
          speed: null,
        },
        timestamp: Date.now(),
      } as GeolocationPosition);
    });

    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition },
    });

    renderPage();

    await screen.findByText("Edit Profile");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Use Current Location",
      }),
    );

    await waitFor(() => {
      expect(
        mockedReverseLocation,
      ).toHaveBeenCalledWith(13.0827, 80.2707);
    });

    expect(
      screen.getByDisplayValue("Detected Current Address"),
    ).toBeTruthy();
  });

  it("maps a backend save failure to a customer-safe error", async () => {
    mockedGetProfile.mockResolvedValueOnce({
      data: existingProfile,
    } as any);

    mockedUpdateProfile.mockRejectedValueOnce({
      response: {
        status: 403,
      },
    });

    renderPage();

    await screen.findByText(
      "Edit Profile",
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Save Changes",
      }),
    );

    await waitFor(() => {
      expect(
        mockedUpdateProfile,
      ).toHaveBeenCalledTimes(1);
    });

    expect(
      (await screen.findByRole("alert"))
        .textContent,
    ).toContain(
      "You do not have permission to access your customer profile.",
    );
  });
});
