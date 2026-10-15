import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base 用相对路径，部署到 GitHub Pages 子路径（/<repo>/）也能正常加载
export default defineConfig({
  base: "./",
  plugins: [react()],
});
