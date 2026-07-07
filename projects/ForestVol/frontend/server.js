import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.FRONTEND_PORT || 3000);
const apiBaseUrl = process.env.API_BASE_URL || process.env.VITE_API_URL || "http://localhost:8000";
const distDir = path.join(__dirname, "dist");
const indexPath = path.join(distDir, "index.html");

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ico": "image/x-icon",
};

function send(response, status, body, contentType = "text/plain; charset=utf-8") {
  response.writeHead(status, { "Content-Type": contentType });
  response.end(body);
}

http
  .createServer((request, response) => {
    const urlPath = decodeURIComponent(new URL(request.url, `http://localhost:${port}`).pathname);

    if (urlPath === "/config.js") {
      send(
        response,
        200,
        `window.__FORESTVOL_CONFIG__ = { API_BASE_URL: ${JSON.stringify(apiBaseUrl)} };\n`,
        "text/javascript; charset=utf-8",
      );
      return;
    }

    const requestedPath = path.normalize(path.join(distDir, urlPath));
    const filePath = requestedPath.startsWith(distDir) && fs.existsSync(requestedPath) && fs.statSync(requestedPath).isFile()
      ? requestedPath
      : indexPath;

    if (!fs.existsSync(filePath)) {
      send(response, 500, "Frontend build not found. Run npm run build first.");
      return;
    }

    send(response, 200, fs.readFileSync(filePath), mimeTypes[path.extname(filePath)] || "application/octet-stream");
  })
  .listen(port, "0.0.0.0", () => {
    console.log(`ForestVol frontend listening on ${port}`);
  });
