// Talks to the FastAPI backend only. Served from /ui by the API itself, so
// requests are same-origin and the base URL is empty.

const API = "";

const $ = (id) => document.getElementById(id);

const LABELS = {
    beach: "beach",
    mountain: "mountain",
    national_park: "national park",
    historical_site: "historical site",
};

// which extra fields to show per category
const FIELDS = {
    beach: [["activity_type", "Activities"], ["water_quality", "Water"]],
    mountain: [["height_m", "Height"], ["trekking_difficulty", "Trek"]],
    national_park: [["area_sq_km", "Area"], ["notable_wildlife", "Wildlife"]],
    historical_site: [["historical_period", "Period"], ["unesco_status", "UNESCO"]],
};

function esc(v) {
    return String(v ?? "").replace(/[&<>"]/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function opts() {
    return {
        category: null,
        district: null,
        accessibility: null,
        limit: 6,
        generate: true,
    };
}

function busy(on) {
    $("loading").hidden = !on;
    document.querySelectorAll("button[data-run]").forEach((b) => (b.disabled = on));
}

async function post(path, body) {
    const r = await fetch(API + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error("API returned " + r.status + ": " + (await r.text()));
    return r.json();
}

// --- rendering ---

function showAnswer(text, source) {
    if (!text) {
        $("answer").innerHTML = "";
        return;
    }
    const label = source === "gemini" ? "Generated answer" : "Answer (retrieval only)";
    const body = text.trim().split(/\n\n+/)
        .map((p) => "<p>" + esc(p).replace(/\n/g, "<br>") + "</p>").join("");
    $("answer").innerHTML =
        '<div class="answer"><div class="label">' + label + "</div>" + body + "</div>";
}

// Just what ran. The router's own query_type is not shown: on this endpoint
// semantic and full-text run whatever it decides, so printing its classification
// next to the retriever list only made the two look like they disagreed. Its
// reasoning was the model's raw sentence about "the user", which read oddly on
// the page.
function showRoute(data) {
    const used = data.retrievers_used || [];
    $("route").textContent = used.length ? "Retrievers: " + used.join(", ") : "";
}

function factLine(row) {
    const parts = [];
    if (row.entrance_fee) parts.push("Entry " + esc(row.entrance_fee));
    if (row.best_season) parts.push("Season " + esc(row.best_season));

    for (const [key, label] of FIELDS[row.category] || []) {
        let v = row[key];
        if (v == null || v === "") continue;
        if (key === "height_m") v = Math.round(v) + " m";
        if (key === "area_sq_km") v = Math.round(v) + " km2";
        parts.push(label + " " + esc(v));
    }
    if (row.similarity != null) parts.push("similarity " + row.similarity.toFixed(3));
    if (row.retrievers) parts.push("matched by " + esc(row.retrievers.join(" + ")));

    return parts.join(" &middot; ");
}

function showCards(rows) {
    $("cards").innerHTML = rows.map((row) => {
        const img = (row.images || [])[0];
        const thumb = img
            ? '<img src="' + API + "/images/" + img.file_path.replace("data/images/", "") +
              '" alt="">'
            : "";
        const place = [row.location, row.district].filter(Boolean).join(", ");
        return "<li>" + thumb +
            "<h3>" + esc(row.name) + "</h3>" +
            ' <span class="meta">(' + (LABELS[row.category] || row.category) +
            (place ? ", " + esc(place) : "") + ")</span>" +
            '<div class="facts">' + factLine(row) + "</div></li>";
    }).join("");
}

function show(data) {
    $("error").hidden = true;
    $("results").hidden = false;

    showAnswer(data.answer, data.answer_source);
    showRoute(data);

    const rows = data.results || [];
    $("count").textContent = rows.length + (rows.length === 1 ? " result" : " results");

    showCards(rows);
    $("context").textContent = data.context || "";

    // Results sit below the form, so on a short window nothing appears to happen
    // when you press Search unless the page is moved down to them.
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

// --- searching ---

async function run(kind) {
    const o = opts();
    busy(true);

    try {
        let data;

        if (kind === "structured") {
            data = await post("/query/structured", {
                query: $("q-structured").value,
                category: o.category,
                district: o.district,
                accessibility: o.accessibility,
                free_entry: $("free").checked,
                unesco_only: $("unesco").checked,
                limit: o.limit,
                generate: o.generate,
            });

        } else if (kind === "semantic") {
            const q = $("q-semantic").value.trim();
            if (!q) throw new Error("Type a query first.");
            data = await post("/query/semantic", {
                query: q, category: o.category, district: o.district,
                limit: o.limit, generate: o.generate,
            });

        } else if (kind === "image") {
            const q = $("q-image").value.trim();
            if (!q) throw new Error("Describe what you are looking for first.");
            data = await post("/query/image", {
                query: q, category: o.category, limit: o.limit, generate: o.generate,
            });

        } else if (kind === "image-upload") {
            const file = $("file").files[0];
            if (!file) throw new Error("Choose an image first.");
            const form = new FormData();
            form.append("file", file);
            form.append("limit", o.limit);
            form.append("category", o.category || "");
            form.append("generate", o.generate);
            const r = await fetch(API + "/query/image/upload", { method: "POST", body: form });
            if (!r.ok) throw new Error("API returned " + r.status);
            data = await r.json();

        } else {
            const q = $("q-hybrid").value.trim();
            if (!q) throw new Error("Type a question first.");
            data = await post("/query/hybrid", {
                query: q, category: o.category, district: o.district,
                accessibility: o.accessibility, limit: o.limit, generate: o.generate,
            });
        }

        show(data);

    } catch (e) {
        // A TypeError here means fetch could not reach the server at all.
        $("results").hidden = true;
        $("error").hidden = false;
        $("error").textContent = e instanceof TypeError
            ? "Cannot reach the API. Start it with: uvicorn api.main:app --port 8000"
            : e.message;
        $("error").scrollIntoView({ behavior: "smooth", block: "center" });
    } finally {
        busy(false);
    }
}

// --- setup ---

// Only says anything when something is actually wrong. Without this a missing
// database or an empty collection just looks like a search that found nothing.
async function checkHealth() {
    let health;
    try {
        health = await (await fetch(API + "/health")).json();
    } catch {
        return warn("Cannot reach the API on port 8000.");
    }
    if (!health.database) return warn("Database unavailable. Is Docker running?");
    if (!health.text_collection) return warn("No text embeddings. Run: python -m embeddings.text_embed");
    if (!health.image_collection) return warn("No image embeddings. Run: python -m embeddings.image_embed");
}

function warn(message) {
    $("error").hidden = false;
    $("error").textContent = message;
}

document.querySelectorAll(".tab").forEach((tab) => {
    tab.onclick = () => {
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        document.querySelectorAll(".tabbody").forEach((b) => b.classList.remove("active"));
        tab.classList.add("active");
        $("tab-" + tab.dataset.tab).classList.add("active");
    };
});

document.querySelectorAll("button[data-run]").forEach((b) => {
    b.onclick = () => run(b.dataset.run);
});

for (const [id, kind] of [["q-structured", "structured"], ["q-semantic", "semantic"],
                          ["q-image", "image"], ["q-hybrid", "hybrid"]]) {
    $(id).onkeydown = (e) => { if (e.key === "Enter") run(kind); };
}

$("file").onchange = (e) => {
    const f = e.target.files[0];
    if (!f) { $("preview").hidden = true; return; }
    $("preview").src = URL.createObjectURL(f);
    $("preview").hidden = false;
};

checkHealth();
