import axios from "axios";

export const apiClient = axios.create({ baseURL: "/api", timeout: 10000 });

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) console.warn("Unauthorized");
    if (err.response?.status >= 500) console.error("Server error", err.response.status);
    return Promise.reject(err);
  }
);
