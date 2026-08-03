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

const COLOURS = {
    beach: "#14a0a0",
    mountain: "#073b3a",
    national_park: "#4c8c4a",
    historical_site: "#c75b39",
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
        category: $("category").value || null,
        district: $("district").value || null,
        accessibility: $("accessibility").value || null,
        limit: Number($("limit").value) || 6,
        generate: $("generate").checked,
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

function showRoute(data) {
    const bits = [];
    if (data.route) {
        bits.push("Routed as " + esc(data.route.query_type) + " (" + esc(data.route.source) + ")");
        if (data.route.reasoning) bits.push(esc(data.route.reasoning));
    }
    if (data.retrievers_used && data.retrievers_used.length) {
        bits.push("Retrievers: " + esc(data.retrievers_used.join(", ")));
    }
    $("route").innerHTML = bits.join(" &middot; ");
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

// Simplified coastline, as [lat, lon]. Drawn with the same projection as the
// pins so they line up.
const COAST = [
    [9.82, 80.20], [9.70, 80.05], [9.35, 79.85], [8.95, 79.70], [8.55, 79.72],
    [8.20, 79.72], [7.70, 79.80], [7.20, 79.83], [6.70, 79.88], [6.30, 80.00],
    [6.05, 80.15], [5.95, 80.45], [5.92, 80.75], [6.05, 81.10], [6.25, 81.35],
    [6.60, 81.65], [7.00, 81.80], [7.50, 81.85], [8.00, 81.35], [8.35, 81.30],
    [8.60, 81.20], [9.00, 80.95], [9.35, 80.70], [9.60, 80.45],
];

function project(lat, lon) {
    return [
        (lon - 79.6) / 2.4 * 240,
        (9.9 - lat) / 4.05 * 390,
    ];
}

function showMap(rows) {
    const outline = COAST.map(([la, lo]) =>
        project(la, lo).map((n) => n.toFixed(1)).join(",")).join(" ");

    const pins = rows.filter((r) => r.latitude != null && r.longitude != null)
        .map((r) => {
            const [x, y] = project(r.latitude, r.longitude);
            return '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) +
                '" r="4" fill="' + (COLOURS[r.category] || "#777") +
                '" stroke="#fff"><title>' + esc(r.name) + "</title></circle>";
        }).join("");

    $("map").innerHTML = '<polygon class="island" points="' + outline + '"/>' + pins;
}

function show(data) {
    $("error").hidden = true;
    $("results").hidden = false;

    showAnswer(data.answer, data.answer_source);
    showRoute(data);

    const rows = data.results || [];
    $("count").textContent = rows.length + (rows.length === 1 ? " result" : " results");

    showCards(rows);
    showMap(rows);
    $("context").textContent = data.context || "";
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
    } finally {
        busy(false);
    }
}

// --- setup ---

async function loadFilters() {
    try {
        const o = await (await fetch(API + "/filters")).json();
        const fill = (id, values, label) => {
            for (const v of values) {
                const el = document.createElement("option");
                el.value = v;
                el.textContent = label ? label(v) : v;
                $(id).appendChild(el);
            }
        };
        fill("category", o.categories, (v) => LABELS[v] || v);
        fill("district", o.districts);
        fill("accessibility", o.accessibility);
    } catch {
        // the status line below reports the real problem
    }
}

async function loadStatus() {
    try {
        const h = await (await fetch(API + "/health")).json();
        $("status").textContent =
            "Database " + (h.database ? "connected" : "unavailable") +
            " | " + h.text_collection + " text vectors" +
            " | " + h.image_collection + " image vectors" +
            " | Gemini " + (h.gemini_configured ? "configured" : "not configured");
    } catch {
        $("status").textContent = "API unreachable on port 8000.";
    }
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

loadFilters();
loadStatus();
