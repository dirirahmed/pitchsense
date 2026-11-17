const DEFAULT_API_URL = 'http://localhost:8000';

/** Base URL of the backend REST API, without a trailing slash. */
export const API_URL: string = (import.meta.env.VITE_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, '');

/** WebSocket base URL derived from the API URL by swapping the http scheme. */
export const WS_URL: string = API_URL.replace(/^http/, 'ws');
