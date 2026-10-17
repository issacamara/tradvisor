"use client";

import type { paths } from "./generated/schema";

type HttpMethod = "get" | "patch" | "post";
type Path = keyof paths;
type MethodFor<P extends Path> = Extract<keyof paths[P], HttpMethod>;
type Operation<P extends Path, M extends MethodFor<P>> = paths[P][M];
type Json<T> = T extends { content: { "application/json": infer Body } } ? Body : never;
type Success<O> = O extends { responses: infer Responses }
  ? Json<Responses extends { 200: infer Body } ? Body : never>
    | Json<Responses extends { 201: infer Body } ? Body : never>
  : never;

export type ApiRequest<P extends Path, M extends MethodFor<P>> = {
  path: P;
  method: M;
  parameters?: Operation<P, M> extends { parameters: infer Parameters } ? Parameters : never;
  body?: Operation<P, M> extends { requestBody: { content: { "application/json": infer Body } } } ? Body : never;
};

export type ApiResponse<P extends Path, M extends MethodFor<P>> = Success<Operation<P, M>>;

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly retryable: boolean | null;

  constructor(status: number, code: string | null, message: string, retryable: boolean | null) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

export interface ApiTransport {
  request<P extends Path, M extends MethodFor<P>>(
    request: ApiRequest<P, M>,
  ): Promise<ApiResponse<P, M>>;
}

export function createApiTransport(request: (path: string, init?: RequestInit) => Promise<Response>): ApiTransport {
  return {
    async request(input) {
      const parameters = input.parameters as { query?: Record<string, string | number | readonly (string | number)[] | null | undefined>; path?: Record<string, string> } | undefined;
      let path = input.path as string;
      for (const [key, value] of Object.entries(parameters?.path ?? {})) path = path.replace(`{${key}}`, encodeURIComponent(value));
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(parameters?.query ?? {})) {
        if (value === undefined || value === null) continue;
        if (Array.isArray(value)) value.forEach((item) => query.append(key, String(item)));
        else query.set(key, String(value));
      }
      if (query.size) path += `?${query.toString()}`;
      const response = await request(path, {
        method: input.method.toUpperCase(),
        headers: input.body ? { "Content-Type": "application/json" } : undefined,
        body: input.body ? JSON.stringify(input.body) : undefined,
      });
      if (!response.ok) {
        let payload: { error?: { code?: string; message?: string; retryable?: boolean } } = {};
        try { payload = await response.json() as typeof payload; } catch { /* Preserve a transport-safe fallback. */ }
        throw new ApiRequestError(
          response.status,
          payload.error?.code ?? null,
          payload.error?.message ?? `Protected API request failed (${response.status}).`,
          payload.error?.retryable ?? null,
        );
      }
      return await response.json() as ApiResponse<typeof input.path, typeof input.method>;
    },
  };
}
