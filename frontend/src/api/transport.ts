"use client";

import type { paths } from "./generated/schema";

type HttpMethod = "get" | "patch" | "post";
type Path = keyof paths;
type MethodFor<P extends Path> = Extract<keyof paths[P], HttpMethod>;
type Operation<P extends Path, M extends MethodFor<P>> = paths[P][M];
type Json<T> = T extends { content: { "application/json": infer Body } } ? Body : never;
type Success<O> = O extends { responses: infer Responses }
  ? Json<Responses extends Record<200 | 201, infer Body> ? Body : never>
  : never;

export type ApiRequest<P extends Path, M extends MethodFor<P>> = {
  path: P;
  method: M;
  parameters?: Operation<P, M> extends { parameters: infer Parameters } ? Parameters : never;
  body?: Operation<P, M> extends { requestBody: { content: { "application/json": infer Body } } } ? Body : never;
};

export type ApiResponse<P extends Path, M extends MethodFor<P>> = Success<Operation<P, M>>;

export interface ApiTransport {
  request<P extends Path, M extends MethodFor<P>>(
    request: ApiRequest<P, M>,
  ): Promise<ApiResponse<P, M>>;
}

export function createApiTransport(request: (path: string, init?: RequestInit) => Promise<Response>): ApiTransport {
  return {
    async request(input) {
      const parameters = input.parameters as { query?: Record<string, string | number | undefined>; path?: Record<string, string> } | undefined;
      let path = input.path as string;
      for (const [key, value] of Object.entries(parameters?.path ?? {})) path = path.replace(`{${key}}`, encodeURIComponent(value));
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(parameters?.query ?? {})) if (value !== undefined) query.set(key, String(value));
      if (query.size) path += `?${query.toString()}`;
      const response = await request(path, {
        method: input.method.toUpperCase(),
        headers: input.body ? { "Content-Type": "application/json" } : undefined,
        body: input.body ? JSON.stringify(input.body) : undefined,
      });
      if (!response.ok) throw new Error(`Protected API request failed (${response.status}).`);
      return await response.json() as ApiResponse<typeof input.path, typeof input.method>;
    },
  };
}
