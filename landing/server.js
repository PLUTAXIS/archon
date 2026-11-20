import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";

const app = express();
const currentDir = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 10000;

app.use(express.static(currentDir));

app.get("*", (req, res) => {
  res.sendFile(path.join(currentDir, "index.html"));
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`ARCHON landing page running on port ${PORT}`);
});
