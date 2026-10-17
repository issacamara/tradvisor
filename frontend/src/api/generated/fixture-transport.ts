import type { paths } from "./schema";

type HttpMethod = "get" | "patch" | "post";
type Path = keyof paths;
type MethodFor<P extends Path> = Extract<keyof paths[P], HttpMethod>;
type Operation<P extends Path, M extends MethodFor<P>> = paths[P][M];
type JsonContent<T> = T extends { content: { "application/json": infer Body } }
  ? Body
  : never;
type ResponseAt<O, Status extends number> = O extends {
  responses: infer Responses;
}
  ? Status extends keyof Responses
    ? JsonContent<Responses[Status]>
    : never
  : never;
type SuccessResponse<O> = ResponseAt<O, 200> | ResponseAt<O, 201>;
type ParametersOf<O> = O extends { parameters: infer Parameters }
  ? Parameters
  : never;
type RequestBodyOf<O> = O extends { requestBody: { content: { "application/json": infer Body } } }
  ? Body
  : never;
type FixtureMapUnion = {
  [P in Path]: {
    [M in MethodFor<P> as `${Uppercase<M & string>} ${P & string}`]: FixtureResponse<P, M>;
  };
}[Path];
type UnionToIntersection<U> = (
  U extends unknown ? (value: U) => void : never
) extends (value: infer I) => void
  ? I
  : never;
type FixtureMap = UnionToIntersection<FixtureMapUnion>;

export type FixtureRequest<P extends Path, M extends MethodFor<P>> = {
  path: P;
  method: M;
  parameters?: ParametersOf<Operation<P, M>>;
} & (RequestBodyOf<Operation<P, M>> extends never
  ? { body?: never }
  : { body: RequestBodyOf<Operation<P, M>> });

export type FixtureResponse<P extends Path, M extends MethodFor<P>> =
  SuccessResponse<Operation<P, M>>;

export interface FixtureTransport {
  request<P extends Path, M extends MethodFor<P>>(
    request: FixtureRequest<P, M>,
  ): Promise<FixtureResponse<P, M>>;
}

export function createFixtureTransport(
  fixtures: Partial<FixtureMap>,
): FixtureTransport {
  return {
    async request(request) {
      const key = `${request.method.toUpperCase()} ${request.path}`;
      if (!Object.hasOwn(fixtures, key)) {
        throw new Error(`No fixture registered for ${key}`);
      }
      return (fixtures as Readonly<Record<string, unknown>>)[key] as FixtureResponse<
        typeof request.path,
        typeof request.method
      >;
    },
  };
}
