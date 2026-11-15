const DEFAULT_API_URL = 'http://localhost:8000';

/** Base URL of the backend API, without a trailing slash. */
export const API_URL: string = (import.meta.env.VITE_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, '');
