import { ApiRequestError } from "@/api/transport";

export type RuntimeDataState = "ready" | "analysis_not_ready" | "setup_required" | "auth_error" | "transport_error";

export function apiState(error: unknown): RuntimeDataState {
  if (!(error instanceof ApiRequestError)) return "transport_error";
  if (error.code === "analysis_not_ready") return "analysis_not_ready";
  if (error.code === "setup_required") return "setup_required";
  if (error.status === 401 || error.status === 403) return "auth_error";
  return "transport_error";
}

export function safeApiMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.code === "analysis_not_ready") return "The latest analytical publication is not ready yet.";
    if (error.status === 401 || error.status === 403) return "Your workspace access is no longer available. Sign in again.";
    return error.message;
  }
  return error instanceof Error ? error.message : "Protected workspace data is temporarily unavailable.";
}
