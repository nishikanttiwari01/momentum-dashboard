/// <reference types="vite/client" />
import axios, { AxiosError, AxiosResponse } from 'axios';

export function configureApi() {
  // No baseURL here — we’ll pass it per request to the generated hooks.
  axios.defaults.headers.common['Accept'] = 'application/json';

  axios.interceptors.response.use(
    (r: AxiosResponse) => r,
    (err: AxiosError) => {
      // helps surface real backend errors
      console.error('[API]', err.response?.status, err.response?.data ?? err.message);
      return Promise.reject(err);
    }
  );
}
