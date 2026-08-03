/* Sri Lanka Tourism Explorer - frontend logic.
 *
 * Plain JavaScript, no framework and no external libraries. Like the Streamlit
 * client, this only ever talks to the FastAPI backend over HTTP; it holds no
 * query logic of its own and never reaches the database or ChromaDB.
 *
 * The page is served by the API itself at /ui, so requests are same-origin and
 * API_BASE is empty. Set it to e.g. "http://localhost:8000" if you instead open
 * index.html straight from disk - CORS on the API is permissive enough to allow
 * that during development. */

const API_BASE = "";

const $ = (selector) => document.querySelector(selector);

const CATEGORY_LABELS = {
    beach: "Beach",
    mountain: "Mountain",
    national_park: "National Park",
    historical_site: "Historical Site",
};

const CATEGORY_COLOURS = {
    beach: "#14A0A0",
    mountain: "#073B3A",
    national_park: "#4C8C4A",
    historical_site: "#C75B39",
};

/* Which detail fields to show per category, and how to label them. Anything not
 * listed stays off the card so it remains readable. */
const CARD_FIELDS = {
    beach: [["activity_type", "Activities"], ["water_quality", "Water"]],
    mountain: [["height_m", "Height"], ["trekking_difficulty", "Trek"]],
    national_park: [["area_sq_km", "Area"], ["notable_wildlife", "Wildlife"]],
    historical_site: [["historical_period", "Period"], ["unesco_status", "UNESCO"]],
};

/* ------------------------------------------------------------------ helpers */

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
}

function imageUrl(filePath) {
    // Stored as data/images/<category>/<file>; the API serves it from /images.
    const relative = filePath.replace("data/images/", "").replace(/\\/g, "/");
    return `${API_BASE}/images/${relative}`;
}

function filters() {
    return {
        category: $("#f-category").value || null,
        district: $("#f-district").value || null,
        accessibility: $("#f-accessibility").value || null,
        limit: Number($("#f-limit").value),
        generate: $("#f-generate").checked,
    };
}

function setLoading(isLoading, message) {
    $("#loading").hidden = !isLoading;
    $("#loading-text").textContent = message || "Searching…";
    document.querySelectorAll(".btn").forEach((button) => {
        button.disabled = isLoading;
    });
}

function showError(message) {
    $("#error").hidden = false;
    $("#error").textContent = message;
    $("#results").hidden = true;
}

async function callApi(path, body) {
    const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!response.ok) {
        throw new Error(`API returned ${response.status}: ${await response.text()}`);
    }
    return response.json();
}

/* -------------------------------------------------------------- rendering */

function renderAnswer(answer, source) {
    if (!answer) { $("#answer").innerHTML = ""; return; }
    const label = source === "gemini" ? "Generated answer" : "Answer (retrieval only)";
    const paragraphs = answer.trim().split(/\n\n+/)
        .map((p) => `<p>${escapeHtml(p).replace(/\n/g, "<br>")}</p>`).join("");
    $("#answer").innerHTML =
        `<div class="answer"><div class="label">${label}</div>${paragraphs}</div>`;
}

function renderRoute(payload) {
    const parts = [];
    const route = payload.route;
    if (route) {
        parts.push(`Router classified this as <strong>${escapeHtml(route.query_type)}</strong>`
                   + ` (via ${escapeHtml(route.source)})`);
        if (route.reasoning) parts.push(escapeHtml(route.reasoning));
    }
    const used = payload.retrievers_used || [];
    if (used.length) {
        parts.push(`Retrievers run: <strong>${escapeHtml(used.join(", "))}</strong>`);
    }
    $("#route").innerHTML = parts.join(" &middot; ");
}

function chips(row) {
    const out = [`<span class="chip">${CATEGORY_LABELS[row.category] || row.category}</span>`];
    if (row.district) out.push(`<span class="chip">${escapeHtml(row.district)}</span>`);
    if (row.accessibility) out.push(`<span class="chip">${escapeHtml(row.accessibility)}</span>`);
    if (row.similarity != null) {
        out.push(`<span class="chip accent">similarity ${row.similarity.toFixed(3)}</span>`);
    }
    if (row.retrievers && row.retrievers.length) {
        out.push(`<span class="chip accent">matched by ${escapeHtml(row.retrievers.join(" + "))}</span>`);
    }
    return out.join("");
}

function facts(row) {
    const parts = [];
    if (row.entrance_fee) parts.push(`<b>Entry</b> ${escapeHtml(row.entrance_fee)}`);
    if (row.best_season) parts.push(`<b>Season</b> ${escapeHtml(row.best_season)}`);

    for (const [field, label] of CARD_FIELDS[row.category] || []) {
        let value = row[field];
        if (value == null || value === "") continue;
        if (field === "height_m") value = `${Math.round(value).toLocaleString()} m`;
        if (field === "area_sq_km") value = `${Math.round(value).toLocaleString()} km²`;
        parts.push(`<b>${label}</b> ${escapeHtml(value)}`);
    }
    return parts.join(" &nbsp;·&nbsp; ");
}

function renderCards(rows) {
    $("#cards").innerHTML = rows.map((row) => {
        const image = (row.images || [])[0];
        const thumbnail = image
            ? `<img src="${imageUrl(image.file_path)}" alt="${escapeHtml(row.name)}" loading="lazy">`
            : "";
        return `
        <article class="card${image ? "" : " no-image"}">
            ${thumbnail}
            <div>
                <h3>${escapeHtml(row.name)}</h3>
                <div class="sub">${escapeHtml(row.location || "")}</div>
                <div>${chips(row)}</div>
                <div class="facts">${facts(row)}</div>
            </div>
        </article>`;
    }).join("");
}

function renderGallery(rows, show) {
    const gallery = $("#gallery");
    if (!show) { gallery.hidden = true; return; }

    const tiles = rows.flatMap((row) =>
        (row.images || []).map((image) => ({ row, image })));

    if (!tiles.length) { gallery.hidden = true; return; }

    gallery.hidden = false;
    gallery.innerHTML = tiles.map(({ row, image }) => {
        const score = row.similarity != null ? ` · ${row.similarity.toFixed(3)}` : "";
        return `<figure>
            <img src="${imageUrl(image.file_path)}" alt="${escapeHtml(row.name)}" loading="lazy">
            <figcaption>${escapeHtml(row.name)}${score}</figcaption>
        </figure>`;
    }).join("");
}

/* ------------------------------------------------------------------- map */

/* Simplified coastline as [latitude, longitude] pairs. Schematic rather than
 * survey-accurate - it exists to give the plotted points a recognisable frame,
 * which is all a result map needs. Drawn with the same projection as the pins so
 * the two always line up. */
const COASTLINE = [
    [9.82, 80.20], [9.70, 80.05], [9.35, 79.85], [8.95, 79.70], [8.55, 79.72],
    [8.20, 79.72], [7.70, 79.80], [7.20, 79.83], [6.70, 79.88], [6.30, 80.00],
    [6.05, 80.15], [5.95, 80.45], [5.92, 80.75], [6.05, 81.10], [6.25, 81.35],
    [6.60, 81.65], [7.00, 81.80], [7.50, 81.85], [8.00, 81.35], [8.35, 81.30],
    [8.60, 81.20], [9.00, 80.95], [9.35, 80.70], [9.60, 80.45],
];

const BOUNDS = { minLat: 5.85, maxLat: 9.90, minLon: 79.60, maxLon: 82.00 };
const MAP_SIZE = { width: 260, height: 420 };

function project(latitude, longitude) {
    // Equirectangular. Over an area this small the distortion is not visible.
    const x = (longitude - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon) * MAP_SIZE.width;
    const y = (BOUNDS.maxLat - latitude) / (BOUNDS.maxLat - BOUNDS.minLat) * MAP_SIZE.height;
    return [x, y];
}

function renderMap(rows) {
    const outline = COASTLINE
        .map(([lat, lon]) => project(lat, lon).map((n) => n.toFixed(1)).join(","))
        .join(" ");

    const pins = rows
        .filter((row) => row.latitude != null && row.longitude != null)
        .map((row) => {
            const [x, y] = project(row.latitude, row.longitude);
            const colour = CATEGORY_COLOURS[row.category] || "#777";
            return `<circle class="pin" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5"
                        fill="${colour}"><title>${escapeHtml(row.name)}</title></circle>`;
        }).join("");

    $("#map").innerHTML =
        `<polygon class="island" points="${outline}"></polygon>${pins}`;
}

/* --------------------------------------------------------------- results */

function renderResults(payload, options = {}) {
    $("#error").hidden = true;
    $("#results").hidden = false;

    renderAnswer(payload.answer, payload.answer_source);
    renderRoute(payload);

    const rows = payload.results || [];
    $("#result-count").textContent =
        `${rows.length} result${rows.length === 1 ? "" : "s"}`;

    if (!rows.length) {
        $("#cards").innerHTML =
            `<p class="empty">Nothing matched. Try relaxing the filters or rephrasing.</p>`;
        $("#gallery").hidden = true;
        $("#map").innerHTML = "";
    } else {
        renderGallery(rows, options.gallery);
        renderCards(rows);
        renderMap(rows);
    }

    $("#context").textContent = payload.context || "";
    $("#results").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* --------------------------------------------------------------- searches */

async function runSearch(kind) {
    const state = filters();
    setLoading(true, {
        structured: "Querying the database…",
        semantic: "Embedding the query and searching…",
        image: "Matching against image embeddings…",
        "image-upload": "Encoding the image with CLIP…",
        hybrid: "Routing, retrieving and fusing results…",
    }[kind]);

    try {
        let payload;

        if (kind === "structured") {
            payload = await callApi("/query/structured", {
                query: $("#q-structured").value,
                category: state.category,
                district: state.district,
                accessibility: state.accessibility,
                free_entry: $("#f-free").checked,
                unesco_only: $("#f-unesco").checked,
                limit: state.limit,
                generate: state.generate,
            });

        } else if (kind === "semantic") {
            const query = $("#q-semantic").value.trim();
            if (!query) throw new Error("Enter a query first.");
            payload = await callApi("/query/semantic", {
                query,
                category: state.category,
                district: state.district,
                limit: state.limit,
                generate: state.generate,
            });

        } else if (kind === "image") {
            const query = $("#q-image").value.trim();
            if (!query) throw new Error("Describe what you are looking for first.");
            payload = await callApi("/query/image", {
                query,
                category: state.category,
                limit: state.limit,
                generate: state.generate,
            });

        } else if (kind === "image-upload") {
            const file = $("#q-file").files[0];
            if (!file) throw new Error("Choose an image first.");
            // Multipart rather than JSON, since this one carries a file.
            const form = new FormData();
            form.append("file", file);
            form.append("limit", String(state.limit));
            form.append("category", state.category || "");
            form.append("generate", String(state.generate));

            const response = await fetch(`${API_BASE}/query/image/upload`, {
                method: "POST", body: form,
            });
            if (!response.ok) {
                throw new Error(`API returned ${response.status}: ${await response.text()}`);
            }
            payload = await response.json();

        } else if (kind === "hybrid") {
            const query = $("#q-hybrid").value.trim();
            if (!query) throw new Error("Enter a question first.");
            payload = await callApi("/query/hybrid", {
                query,
                category: state.category,
                district: state.district,
                accessibility: state.accessibility,
                limit: state.limit,
                generate: state.generate,
            });
        }

        renderResults(payload, { gallery: kind.startsWith("image") });

    } catch (error) {
        const message = error instanceof TypeError
            ? `Cannot reach the API. Start it with: uvicorn api.main:app --reload --port 8000`
            : error.message;
        showError(message);
    } finally {
        setLoading(false);
    }
}

/* ----------------------------------------------------------------- startup */

async function loadFilters() {
    try {
        const options = await (await fetch(`${API_BASE}/filters`)).json();
        const add = (selectId, values, labeller) => {
            const select = $(selectId);
            for (const value of values) {
                const option = document.createElement("option");
                option.value = value;
                option.textContent = labeller ? labeller(value) : value;
                select.appendChild(option);
            }
        };
        add("#f-category", options.categories, (v) => CATEGORY_LABELS[v] || v);
        add("#f-district", options.districts);
        add("#f-accessibility", options.accessibility,
            (v) => v.charAt(0).toUpperCase() + v.slice(1));
    } catch {
        // Health check below surfaces the underlying problem to the user.
    }
}

async function loadHealth() {
    const list = $("#status");
    try {
        const health = await (await fetch(`${API_BASE}/health`)).json();
        list.innerHTML = `
            <dt>Database</dt><dd class="${health.database ? "" : "bad"}">
                ${health.database ? "connected" : "unavailable"}</dd>
            <dt>Text embeddings</dt><dd>${health.text_collection} vectors</dd>
            <dt>Image embeddings</dt><dd>${health.image_collection} vectors</dd>
            <dt>Gemini</dt><dd class="${health.gemini_configured ? "" : "bad"}">
                ${health.gemini_configured ? "configured" : "not configured"}</dd>`;
    } catch {
        list.innerHTML = `<dt>Status</dt><dd class="bad">API unreachable</dd>`;
    }
}

function initTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tab").forEach((t) => t.classList.remove("is-active"));
            document.querySelectorAll(".panel").forEach((p) => p.classList.remove("is-active"));
            tab.classList.add("is-active");
            $(`.panel[data-panel="${tab.dataset.tab}"]`).classList.add("is-active");
        });
    });
}

function initInputs() {
    document.querySelectorAll("[data-search]").forEach((button) => {
        button.addEventListener("click", () => runSearch(button.dataset.search));
    });

    // Enter submits the text box it was pressed in.
    const enterTargets = {
        "#q-structured": "structured", "#q-semantic": "semantic",
        "#q-image": "image", "#q-hybrid": "hybrid",
    };
    for (const [selector, kind] of Object.entries(enterTargets)) {
        $(selector).addEventListener("keydown", (event) => {
            if (event.key === "Enter") runSearch(kind);
        });
    }

    $("#f-limit").addEventListener("input", (event) => {
        $("#limit-value").textContent = event.target.value;
    });

    $("#q-file").addEventListener("change", (event) => {
        const file = event.target.files[0];
        const preview = $("#preview");
        if (!file) { preview.hidden = true; return; }
        preview.src = URL.createObjectURL(file);
        preview.hidden = false;
    });
}

initTabs();
initInputs();
loadFilters();
loadHealth();
