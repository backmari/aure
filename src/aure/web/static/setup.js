/* ================================================================
   AuRE – setup.js
   Client-side logic for the interactive setup page:
     • Server-side file / folder browser (modal)
     • Analysis launch + status polling
   ================================================================ */

/* ---- state --------------------------------------------------- */
let browserMode = "file";        // "file" | "dir"
let browserCurrentPath = null;
let browserParentPath = null;
let browserModalInstance = null;
let pollTimer = null;

const KNOWN_NODES = ["intake", "analysis", "modeling", "fitting", "evaluation"];

/* ---- LLM badge helper ---------------------------------------- */

function _llmBadges(calls) {
  if (!calls || calls.length === 0) return '<span class="text-muted">—</span>';
  return calls.map(function(c) {
    if (!c.success)
      return '<span class="badge bg-danger" title="' + (c.error || '').replace(/"/g, '&quot;') + '">✗ failed</span>';
    if (c.used_fallback)
      return '<span class="badge bg-warning text-dark" title="' + (c.fallback_reason || '').replace(/"/g, '&quot;') + '">⚠ fallback</span>';
    return '<span class="badge bg-success">✓ ok</span>';
  }).join(" ");
}

/* ---- file / folder browser ----------------------------------- */

function openBrowser(mode) {
  browserMode = mode;
  document.getElementById("browser-title").textContent =
    mode === "file" ? "Select Data File" : "Select Output Folder";

  // Show or hide "Select this folder" button
  document.getElementById("btn-select").style.display =
    mode === "dir" ? "inline-block" : "none";

  // Start at a sensible path
  const startPath = mode === "file" ? "" : "";   // default handled by server
  _fetchBrowserListing(startPath);

  browserModalInstance =
    browserModalInstance ||
    new bootstrap.Modal(document.getElementById("browserModal"));
  browserModalInstance.show();
}

function _fetchBrowserListing(path) {
  const endpoint = browserMode === "file" ? "/api/browse-files" : "/api/browse-dirs";
  const params = new URLSearchParams();
  if (path) params.set("path", path);
  if (browserMode === "file") params.set("ext", ".txt");

  fetch(`${endpoint}?${params}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        alert(data.error);
        return;
      }
      browserCurrentPath = data.current;
      browserParentPath = data.parent;
      document.getElementById("browser-path").textContent = data.current;
      document.getElementById("btn-parent").disabled = !data.parent;

      const list = document.getElementById("browser-list");
      list.innerHTML = "";

      data.entries.forEach((entry) => {
        const a = document.createElement("a");
        a.className = "list-group-item list-group-item-action d-flex align-items-center";
        a.href = "#";

        const icon = document.createElement("i");
        icon.className = entry.is_dir
          ? "bi bi-folder-fill text-warning me-2"
          : "bi bi-file-earmark-text me-2";
        a.appendChild(icon);

        const name = document.createElement("span");
        name.textContent = entry.name;
        a.appendChild(name);

        a.addEventListener("click", (e) => {
          e.preventDefault();
          if (entry.is_dir || entry.is_dir === undefined) {
            // Navigate into directory
            _fetchBrowserListing(entry.path);
          } else {
            // File selected
            document.getElementById("data-file").value = entry.path;
            browserModalInstance.hide();
          }
        });

        list.appendChild(a);
      });

      if (data.entries.length === 0) {
        const empty = document.createElement("div");
        empty.className = "list-group-item text-muted text-center";
        empty.textContent = browserMode === "file"
          ? "No matching files in this directory"
          : "No sub-folders";
        list.appendChild(empty);
      }
    })
    .catch((err) => console.error("Browse error:", err));
}

function browserUp() {
  if (browserParentPath) {
    _fetchBrowserListing(browserParentPath);
  }
}

function browserSelect() {
  // Folder mode – select the current directory
  if (browserMode === "dir" && browserCurrentPath) {
    document.getElementById("output-dir").value = browserCurrentPath;
    browserModalInstance.hide();
  }
}

/* ---- analysis launch ----------------------------------------- */

function startAnalysis() {
  const dataFile = document.getElementById("data-file").value.trim();
  const sampleDesc = document.getElementById("sample-desc").value.trim();
  const hypothesis = document.getElementById("hypothesis").value.trim();
  const outputDir = document.getElementById("output-dir").value.trim();

  if (!dataFile) { alert("Please select a data file."); return; }
  if (!sampleDesc) { alert("Please enter a sample description."); return; }
  if (!outputDir) { alert("Please select an output directory."); return; }

  const btn = document.getElementById("btn-start");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Starting…';

  fetch("/api/start-analysis", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      data_file: dataFile,
      sample_description: sampleDesc,
      hypothesis: hypothesis || null,
      output_dir: outputDir,
    }),
  })
    .then((r) => r.json().then((d) => ({ ok: r.ok, data: d })))
    .then(({ ok, data }) => {
      if (!ok) {
        const msg = data.errors ? data.errors.join("\n") : data.error || "Unknown error";
        alert("Could not start analysis:\n" + msg);
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-play-fill"></i> Start Analysis';
        return;
      }
      // Switch to progress view
      document.getElementById("setup-section").style.display = "none";
      document.getElementById("progress-section").style.display = "";
      document.getElementById("checkpoint-table").querySelector("tbody").innerHTML = "";
      pollStatus();
    })
    .catch((err) => {
      alert("Network error: " + err);
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-play-fill"></i> Start Analysis';
    });
}

/* ---- status polling ------------------------------------------ */

function pollStatus() {
  if (pollTimer) clearTimeout(pollTimer);

  fetch("/api/analysis-status")
    .then((r) => r.json())
    .then((st) => {
      const nodeLabel = st.current_node
        ? st.current_node.charAt(0).toUpperCase() + st.current_node.slice(1)
        : "Starting…";
      document.getElementById("progress-node").textContent =
        st.status === "complete"
          ? "Analysis complete!"
          : st.status === "error"
          ? "Error: " + (st.error || "unknown")
          : `Step: ${nodeLabel}  (iteration ${st.iteration})`;

      // Progress bar
      const nSteps = st.checkpoints ? st.checkpoints.length : 0;
      const pct = st.status === "complete" ? 100 : Math.min(95, (nSteps / 8) * 100);
      const bar = document.getElementById("progress-bar");
      bar.style.width = pct + "%";

      if (st.status === "complete") {
        bar.classList.remove("progress-bar-animated", "progress-bar-striped");
        bar.classList.add("bg-success");
      } else if (st.status === "error") {
        bar.classList.remove("progress-bar-animated", "progress-bar-striped");
        bar.classList.add("bg-danger");
      }

      // Status badge
      const badge = document.getElementById("progress-status");
      badge.textContent = st.status;
      badge.className =
        "badge " +
        (st.status === "complete"
          ? "bg-success"
          : st.status === "error"
          ? "bg-danger"
          : "bg-primary");

      // Checkpoint table
      if (st.checkpoints && st.checkpoints.length) {
        const tbody = document.getElementById("checkpoint-table").querySelector("tbody");
        tbody.innerHTML = "";
        st.checkpoints.forEach((cp, i) => {
          const tr = document.createElement("tr");
          tr.innerHTML =
            `<td>${i + 1}</td>` +
            `<td>${cp.node}</td>` +
            `<td>${cp.chi2 != null ? cp.chi2.toFixed(2) : "—"}</td>` +
            `<td>${_llmBadges(cp.llm_calls)}</td>`;
          tbody.appendChild(tr);
        });
      }

      // Footer buttons
      if (st.status === "complete" || st.status === "error") {
        document.getElementById("progress-footer").style.display = "";
        return; // stop polling
      }

      pollTimer = setTimeout(pollStatus, 2000);
    })
    .catch(() => {
      pollTimer = setTimeout(pollStatus, 3000);
    });
}

/* ---- reset --------------------------------------------------- */

function resetSetup() {
  document.getElementById("setup-section").style.display = "";
  document.getElementById("progress-section").style.display = "none";

  // Re-enable start button
  const btn = document.getElementById("btn-start");
  btn.disabled = false;
  btn.innerHTML = '<i class="bi bi-play-fill"></i> Start Analysis';

  // Clear progress
  document.getElementById("progress-bar").style.width = "5%";
  document.getElementById("progress-bar").className =
    "progress-bar progress-bar-striped progress-bar-animated";
  document.getElementById("progress-footer").style.display = "none";
  document.getElementById("checkpoint-table").querySelector("tbody").innerHTML = "";
}
