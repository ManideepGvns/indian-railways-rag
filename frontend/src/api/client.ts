import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL ?? "";

const api = axios.create({ baseURL: `${BASE_URL}/api` });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ir_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("ir_token");
      localStorage.removeItem("ir_user");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

export const BASE = BASE_URL;
