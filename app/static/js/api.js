export async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || body.message || JSON.stringify(body);
      if (Array.isArray(msg)) msg = msg.map((d) => d.msg || d).join("; ");
    } catch {
      try {
        msg = await res.text();
      } catch {
        /* keep statusText */
      }
    }
    throw new Error(msg || `HTTP ${res.status}`);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

export function uploadWav(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/tracks");
    xhr.responseType = "json";
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable && onProgress) onProgress(ev.loaded / ev.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else {
        const d = xhr.response?.detail || xhr.statusText;
        reject(new Error(typeof d === "string" ? d : JSON.stringify(d)));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed"));
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}
