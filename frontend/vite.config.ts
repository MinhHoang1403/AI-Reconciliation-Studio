import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Khi chạy `npm run dev`, chuyển tiếp /api về backend trong Docker (qua Nginx ở cổng 18180).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:18180" } },
});
