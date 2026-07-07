import { api } from "./api";

export async function uploadImages(files) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const { data } = await api.post("/api/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });

  return data;
}
