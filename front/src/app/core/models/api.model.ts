/** Every backend endpoint returns this envelope — see api/app/core/responses.py. */
export interface SuccessResponse<T> {
    status: string;
    data: T;
    meta?: Record<string, unknown> | null;
}

/** Errors are rendered by the handlers registered in api/app/main.py. */
export interface ErrorResponse {
    status: string;
    error_code: string;
    message: string;
    details?: unknown;
}
