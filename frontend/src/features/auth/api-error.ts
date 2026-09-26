export function safeApiMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Protected workspace data is temporarily unavailable.";
}
