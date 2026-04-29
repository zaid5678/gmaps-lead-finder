#!/usr/bin/env python3
"""
Local leads dashboard — run with:  python dashboard.py
Then open http://localhost:5000 in your browser.
"""

import csv
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

README_PATH = Path("README.md")
_LEADS_HEADER = "## Leads\n"
_LEGAL_MARKER = "## Legal Note"

CSV_PATH = Path("output/roofers_leads.csv")
FIELDNAMES = [
    "fingerprint", "name", "city", "address", "phone", "email",
    "rating", "review_count", "maps_url", "scraped_at",
    "contacted", "contacted_date", "is_priority", "pain_keywords_found",
]

app = Flask(__name__)


def load_leads() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("name", "").strip()]


def save_leads(leads: list[dict]):
    extra = sorted(set().union(*[r.keys() for r in leads]) - set(FIELDNAMES))
    fieldnames = FIELDNAMES + extra
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in leads:
            w.writerow({k: row.get(k, "") for k in fieldnames})


HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Leads Dashboard</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           background: #f0f2f5; color: #1a1a2e; min-height: 100vh; }

    header { background: #1a1a2e; color: #fff; padding: 18px 32px;
             display: flex; align-items: center; justify-content: space-between; }
    header h1 { font-size: 18px; font-weight: 600; letter-spacing: .3px; }
    header span { font-size: 13px; color: #a0aec0; }
    .sync-btn { background: #4f46e5; color: #fff; border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer;
                transition: background .15s; }
    .sync-btn:hover { background: #4338ca; }
    .sync-btn:disabled { background: #6b7280; cursor: not-allowed; }

    .toolbar { padding: 16px 32px; display: flex; gap: 12px; align-items: center;
               flex-wrap: wrap; }
    .toolbar input, .toolbar select {
      padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px;
      font-size: 13px; background: #fff; outline: none; }
    .toolbar input:focus, .toolbar select:focus { border-color: #4f46e5; }
    .toolbar input[type=search] { width: 220px; }

    .stats { display: flex; gap: 16px; padding: 0 32px 16px; flex-wrap: wrap; }
    .stat { background: #fff; border-radius: 8px; padding: 14px 20px;
            border: 1px solid #e5e7eb; min-width: 130px; }
    .stat .val { font-size: 26px; font-weight: 700; color: #1a1a2e; }
    .stat .lbl { font-size: 11px; color: #6b7280; margin-top: 2px; text-transform: uppercase;
                 letter-spacing: .5px; }

    .table-wrap { margin: 0 32px 32px; background: #fff; border-radius: 10px;
                  border: 1px solid #e5e7eb; overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    thead tr { background: #f8f9fa; }
    th { padding: 11px 14px; text-align: left; font-weight: 600; font-size: 11px;
         text-transform: uppercase; letter-spacing: .5px; color: #6b7280;
         border-bottom: 1px solid #e5e7eb; white-space: nowrap; cursor: pointer;
         user-select: none; }
    th:hover { color: #1a1a2e; }
    th .sort-arrow { margin-left: 4px; opacity: .4; }
    th.sorted .sort-arrow { opacity: 1; }
    td { padding: 10px 14px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #fafafa; }
    tr.priority td { background: #fffbeb; }
    tr.priority:hover td { background: #fef3c7; }
    tr.contacted td { background: #f0fdf4; color: #6b7280; }
    tr.contacted td strong { text-decoration: line-through; font-weight: 400; }
    tr.contacted .cb-wrap input { opacity: 1; }

    .badge-priority { display: inline-block; background: #fef3c7; color: #92400e;
                      border: 1px solid #fcd34d; border-radius: 4px; padding: 2px 7px;
                      font-size: 10px; font-weight: 700; letter-spacing: .5px; }
    .pain-kw { font-size: 11px; color: #b91c1c; max-width: 180px; line-height: 1.4; }

    a { color: #4f46e5; text-decoration: none; }
    a:hover { text-decoration: underline; }

    .phone { white-space: nowrap; }

    /* Checkbox toggle */
    .cb-wrap { display: flex; align-items: center; justify-content: center; }
    input[type=checkbox] { width: 17px; height: 17px; accent-color: #4f46e5; cursor: pointer; }

    .saving { position: fixed; bottom: 20px; right: 24px; background: #1a1a2e; color: #fff;
              padding: 10px 18px; border-radius: 8px; font-size: 13px;
              opacity: 0; transition: opacity .2s; pointer-events: none; }
    .saving.show { opacity: 1; }

    @media (max-width: 700px) {
      .toolbar, .stats, .table-wrap { margin-left: 12px; margin-right: 12px; }
    }
  </style>
</head>
<body>

<header>
  <h1>Leads Dashboard</h1>
  <div style="display:flex;align-items:center;gap:16px;">
    <span id="live-count"></span>
    <button class="sync-btn" id="sync-btn" onclick="syncToGitHub()">Push to GitHub</button>
  </div>
</header>

<div class="stats">
  <div class="stat"><div class="val" id="s-total">—</div><div class="lbl">Total leads</div></div>
  <div class="stat"><div class="val" id="s-priority">—</div><div class="lbl">Priority</div></div>
  <div class="stat"><div class="val" id="s-contacted">—</div><div class="lbl">Contacted</div></div>
  <div class="stat"><div class="val" id="s-remaining">—</div><div class="lbl">Remaining</div></div>
</div>

<div class="toolbar">
  <input type="search" id="search" placeholder="Search name, city, phone…">
  <select id="filter-city">
    <option value="">All cities</option>
  </select>
  <select id="filter-status">
    <option value="">All statuses</option>
    <option value="no">Not contacted</option>
    <option value="yes">Contacted</option>
    <option value="priority">Priority only</option>
  </select>
</div>

<div class="table-wrap">
  <table id="leads-table">
    <thead>
      <tr>
        <th data-col="contacted" style="width:60px;text-align:center;">Done</th>
        <th data-col="name">Business</th>
        <th data-col="city">City</th>
        <th data-col="phone">Phone</th>
        <th data-col="review_count" class="sorted" style="text-align:right;">Reviews</th>
        <th data-col="rating" style="text-align:right;">Rating</th>
        <th data-col="is_priority" style="width:90px;">Priority</th>
        <th data-col="pain_keywords_found">Pain signals</th>
        <th style="width:60px;">Maps</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<div class="saving" id="saving-toast">Saving…</div>

<script>
let allLeads = [];
let sortCol = "review_count";
let sortDir = -1; // -1 = desc

async function fetchLeads() {
  const res = await fetch("/api/leads");
  allLeads = await res.json();
  populateCityFilter();
  render();
  updateStats();
}

function populateCityFilter() {
  const cities = [...new Set(allLeads.map(l => l.city).filter(Boolean))].sort();
  const sel = document.getElementById("filter-city");
  cities.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c; opt.textContent = c;
    sel.appendChild(opt);
  });
}

function getFiltered() {
  const q = document.getElementById("search").value.toLowerCase();
  const city = document.getElementById("filter-city").value;
  const status = document.getElementById("filter-status").value;

  return allLeads.filter(l => {
    if (q && !`${l.name} ${l.city} ${l.phone}`.toLowerCase().includes(q)) return false;
    if (city && l.city !== city) return false;
    if (status === "no"  && l.contacted === "yes") return false;
    if (status === "yes" && l.contacted !== "yes") return false;
    if (status === "priority" && l.is_priority !== "yes") return false;
    return true;
  });
}

function sorted(leads) {
  return [...leads].sort((a, b) => {
    let va = a[sortCol] ?? "", vb = b[sortCol] ?? "";
    if (sortCol === "review_count" || sortCol === "rating") {
      va = parseFloat(va) || 0; vb = parseFloat(vb) || 0;
    } else {
      va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
    }
    // Priority rows always float to top within the sorted order
    if (a.is_priority === "yes" && b.is_priority !== "yes") return -1;
    if (b.is_priority === "yes" && a.is_priority !== "yes") return  1;
    if (va < vb) return sortDir;
    if (va > vb) return -sortDir;
    return 0;
  });
}

function render() {
  const rows = sorted(getFiltered());
  document.getElementById("live-count").textContent = `${rows.length} lead${rows.length !== 1 ? "s" : ""} shown`;
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = "";

  rows.forEach(lead => {
    const tr = document.createElement("tr");
    if (lead.is_priority === "yes") tr.classList.add("priority");
    if (lead.contacted === "yes") tr.classList.add("contacted");

    const mapLink = lead.maps_url
      ? `<a href="${lead.maps_url}" target="_blank" rel="noopener">View</a>` : "";
    const priorityBadge = lead.is_priority === "yes"
      ? `<span class="badge-priority">PRIORITY</span>` : "";
    const painKw = lead.pain_keywords_found
      ? `<span class="pain-kw">${lead.pain_keywords_found}</span>` : "";
    const reviewCount = lead.review_count !== "" ? Number(lead.review_count).toLocaleString() : "";
    const rating = lead.rating !== "" ? parseFloat(lead.rating).toFixed(1) : "";

    tr.innerHTML = `
      <td class="cb-wrap">
        <input type="checkbox" data-fp="${lead.fingerprint}" ${lead.contacted === "yes" ? "checked" : ""}>
      </td>
      <td><strong>${esc(lead.name)}</strong></td>
      <td>${esc(lead.city)}</td>
      <td class="phone">${esc(lead.phone)}</td>
      <td style="text-align:right;">${reviewCount}</td>
      <td style="text-align:right;">${rating}</td>
      <td>${priorityBadge}</td>
      <td>${painKw}</td>
      <td>${mapLink}</td>
    `;
    tbody.appendChild(tr);
  });

  // Attach checkbox listeners
  tbody.querySelectorAll("input[type=checkbox]").forEach(cb => {
    cb.addEventListener("change", onToggle);
  });
}

function updateStats() {
  const total     = allLeads.length;
  const priority  = allLeads.filter(l => l.is_priority === "yes").length;
  const contacted = allLeads.filter(l => l.contacted === "yes").length;
  document.getElementById("s-total").textContent     = total;
  document.getElementById("s-priority").textContent  = priority;
  document.getElementById("s-contacted").textContent = contacted;
  document.getElementById("s-remaining").textContent = total - contacted;
}

async function onToggle(e) {
  const fp = e.target.dataset.fp;
  const contacted = e.target.checked;
  const lead = allLeads.find(l => l.fingerprint === fp);
  if (!lead) return;

  lead.contacted = contacted ? "yes" : "";
  lead.contacted_date = contacted ? new Date().toISOString().slice(0, 16).replace("T", " ") : "";

  // Update UI immediately — don't wait for the save
  updateStats();
  render();

  showToast("Saving…");
  try {
    await fetch("/api/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fingerprint: fp, contacted }),
    });
    showToast("Saved");
  } catch {
    showToast("Save failed — check server");
  }
  setTimeout(hideToast, 1200);
}

// Sorting
document.querySelectorAll("th[data-col]").forEach(th => {
  th.innerHTML += '<span class="sort-arrow">↕</span>';
  th.addEventListener("click", () => {
    const col = th.dataset.col;
    if (sortCol === col) { sortDir *= -1; }
    else { sortCol = col; sortDir = -1; }
    document.querySelectorAll("th").forEach(t => t.classList.remove("sorted"));
    th.classList.add("sorted");
    th.querySelector(".sort-arrow").textContent = sortDir === -1 ? "↓" : "↑";
    render();
  });
});

// Filters
["search","filter-city","filter-status"].forEach(id => {
  document.getElementById(id).addEventListener("input", render);
});

// Toast
let toastTimer;
function showToast(msg = "Saving…") {
  clearTimeout(toastTimer);
  const el = document.getElementById("saving-toast");
  el.textContent = msg;
  el.classList.add("show");
}
function hideToast() {
  document.getElementById("saving-toast").classList.remove("show");
}

function esc(str) {
  return String(str || "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function syncToGitHub() {
  const btn = document.getElementById("sync-btn");
  btn.disabled = true;
  btn.textContent = "Pushing…";
  showToast("Rebuilding README and pushing…");
  try {
    const res = await fetch("/api/sync", { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      showToast("Pushed to GitHub");
    } else {
      showToast("Push failed: " + (data.error || "unknown error"));
    }
  } catch {
    showToast("Push failed — check server");
  }
  setTimeout(() => {
    hideToast();
    btn.disabled = false;
    btn.textContent = "Push to GitHub";
  }, 3000);
}

fetchLeads();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/leads")
def api_leads():
    return jsonify(load_leads())


@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    data = request.get_json()
    fp = data.get("fingerprint")
    contacted = data.get("contacted", False)

    leads = load_leads()
    for lead in leads:
        if lead.get("fingerprint") == fp:
            lead["contacted"] = "yes" if contacted else ""
            lead["contacted_date"] = (
                datetime.now().strftime("%Y-%m-%d %H:%M") if contacted else ""
            )
            break

    save_leads(leads)
    return jsonify({"ok": True})


@app.route("/api/sync", methods=["POST"])
def api_sync():
    """Rebuild README leads table from CSV and push to GitHub."""
    try:
        leads = load_leads()
        leads.sort(key=lambda r: (r.get("is_priority", "") != "yes", -int(r.get("review_count") or 0)))

        header = (
            "| Business | City | Phone | Reviews | Rating | Contacted | Priority | Maps |\n"
            "|----------|------|-------|---------|--------|-----------|----------|------|\n"
        )
        table_rows = ""
        for r in leads:
            name     = r.get("name", "").replace("|", "\\|").strip()
            city     = r.get("city", "").strip()
            phone    = r.get("phone", "").replace("|", "\\|").strip()
            reviews  = r.get("review_count", "")
            rating   = r.get("rating", "")
            contacted = "Yes" if r.get("contacted") == "yes" else ""
            priority  = "YES" if r.get("is_priority") == "yes" else ""
            maps_url  = r.get("maps_url", "")
            link      = f"[Maps]({maps_url})" if maps_url else ""
            table_rows += f"| {name} | {city} | {phone} | {reviews} | {rating} | {contacted} | {priority} | {link} |\n"

        contacted_count = sum(1 for r in leads if r.get("contacted") == "yes")
        new_section = (
            "## Leads\n\n"
            f"**{len(leads)} total leads — {contacted_count} contacted, {len(leads) - contacted_count} remaining.**\n\n"
            + header + table_rows + "\n"
        )

        content = README_PATH.read_text(encoding="utf-8")
        leads_start = content.find("## Leads\n")
        legal_start = content.find(_LEGAL_MARKER)
        if leads_start == -1 or legal_start == -1:
            return jsonify({"ok": False, "error": "Could not find README section markers"})

        content = content[:leads_start] + new_section + "\n---\n\n" + content[legal_start:]
        README_PATH.write_text(content, encoding="utf-8")

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "add", "output/roofers_leads.csv", "README.md"], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Update contacted leads — {now}"],
            check=True,
        )
        subprocess.run(["git", "push", "origin", "main"], check=True)

        return jsonify({"ok": True})

    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "error": str(e)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    webbrowser.open("http://localhost:5000")
    app.run(port=5000, debug=False)
