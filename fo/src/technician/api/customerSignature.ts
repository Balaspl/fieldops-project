import { apiClient } from "./client";
import { getApiErrorMessage } from "./apiError";
import {
  logError,
  logEvent
} from "../observability/logger";

const MAX_SIGNATURE_LENGTH = 2_000_000;

export interface CustomerSignatureResponse {
  id: number;
  job_id: number;
  job_closure_id: number;
  signature_data: string;
  signed_at: string;
  created_at: string;
  updated_at: string;
}

export async function uploadCustomerSignature(
  jobId: string | number,
  signatureData: string
): Promise<CustomerSignatureResponse> {
  const numericJobId = Number(String(jobId).trim());

  if (
    !Number.isSafeInteger(numericJobId) ||
    numericJobId <= 0
  ) {
    throw new Error("A valid job ID is required.");
  }

  if (
    typeof signatureData !== "string" ||
    !signatureData.trim()
  ) {
    throw new Error("Please capture the customer's signature.");
  }

  const canonicalSignature = signatureData.trim();

  if (canonicalSignature.length > MAX_SIGNATURE_LENGTH) {
    throw new Error(
      "The signature is too large. Clear it and capture a simpler signature."
    );
  }

  if (
    !/^data:image\/(?:png|jpeg);base64,[A-Za-z0-9+/=]+$/.test(
      canonicalSignature
    )
  ) {
    throw new Error(
      "The signature must be a valid PNG or JPEG image."
    );
  }

  try {
    logEvent("customer_signature.upload_started", {});

    const response =
      await apiClient.post<CustomerSignatureResponse>(
        `/jobs/${numericJobId}/customer-signature`,
        {
          signature_data: canonicalSignature
        }
      );

    logEvent("customer_signature.upload_succeeded", {});

    return response.data;
  } catch (error: unknown) {
    logError("customer_signature.upload_failed", error);

    throw new Error(
      getApiErrorMessage(
        error,
        "Unable to save the customer's signature. Please try again."
      )
    );
  }
}