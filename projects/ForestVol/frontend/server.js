const fs = require("fs");
const http = require("http");
const path = require("path");

const port = Number(process.env.FRONTEND_PORT || 3000);
const indexPath = path.join(__dirname, "index.html");

http
  .createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(fs.readFileSync(indexPath, "utf8"));
  })
  .listen(port, "0.0.0.0", () => {
    console.log(`ForestVol frontend placeholder listening on ${port}`);
  });
