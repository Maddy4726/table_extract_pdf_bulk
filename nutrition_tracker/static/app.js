const state = {
  selectedFood: null,
  searchTimeout: null,
  activeResultIndex: -1,
};

const MACRO_FIELDS = [
  { key: "calories_kcal", label: "Calories", unit: "kcal", cls: "calories" },
  { key: "protein_g", label: "Protein", unit: "g", cls: "protein" },
  { key: "carbs_g", label: "Carbs", unit: "g", cls: "carbs" },
  { key: "fat_g", label: "Fat", unit: "g", cls: "fat" },
];

const MICRO_FIELDS = [
  { key: "fiber_g", label: "Fiber", unit: "g" },
  { key: "sugar_g", label: "Sugar", unit: "g" },
  { key: "sodium_mg", label: "Sodium", unit: "mg" },
  { key: "potassium_mg", label: "Potassium", unit: "mg" },
  { key: "calcium_mg", label: "Calcium", unit: "mg" },
  { key: "iron_mg", label: "Iron", unit: "mg" },
  { key: "magnesium_mg", label: "Magnesium", unit: "mg" },
  { key: "zinc_mg", label: "Zinc", unit: "mg" },
  { key: "vitamin_a_mcg", label: "Vitamin A", unit: "mcg" },
  { key: "vitamin_c_mg", label: "Vitamin C", unit: "mg" },
  { key: "vitamin_d_mcg", label: "Vitamin D", unit: "mcg" },
  { key: "vitamin_e_mg", label: "Vitamin E", unit: "mg" },
  { key: "vitamin_k_mcg", label: "Vitamin K", unit: "mcg" },
  { key: "vitamin_b6_mg", label: "Vitamin B6", unit: "mg" },
  { key: "vitamin_b12_mcg", label: "Vitamin B12", unit: "mcg" },
  { key: "folate_mcg", label: "Folate", unit: "mcg" },
];

const $ = (id) => document.getElementById(id);

function formatNum(value, decimals = 1) {
  if (value >= 100) return Math.round(value).toString();
  return Number(value).toFixed(decimals);
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2200);
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

function renderMacroGrid(container, nutrients, cardClass = "macro-card") {
  container.innerHTML = MACRO_FIELDS.map(({ key, label, unit, cls }) => `
    <div class="${cardClass} ${cls}">
      <div class="value">${formatNum(nutrients[key] || 0)}</div>
      <div class="label">${label} (${unit})</div>
    </div>
  `).join("");
}

function renderMicroGrid(container, nutrients) {
  container.innerHTML = MICRO_FIELDS.map(({ key, label, unit }) => {
    const val = nutrients[key] || 0;
    if (val < 0.05) return "";
    return `
      <div class="micro-item">
        <span>${label}</span>
        <span>${formatNum(val)} ${unit}</span>
      </div>
    `;
  }).join("");
}

function setSelectedFood(food) {
  state.selectedFood = food;
  const el = $("selected-food");
  if (!food) {
    el.classList.add("hidden");
    $("log-btn").disabled = true;
    $("preview-panel").classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = `Selected: <strong>${food.name}</strong> <span style="color:var(--muted)">(${food.category})</span>`;
  $("log-btn").disabled = false;
  updatePreview();
}

async function searchFoods(query) {
  const results = await api(`/api/foods/search?q=${encodeURIComponent(query)}`);
  const container = $("search-results");
  if (!results.length) {
    container.classList.remove("visible");
    container.innerHTML = "";
    return;
  }
  container.innerHTML = results.map((f, i) => `
    <div class="search-item" data-id="${f.id}" data-index="${i}">
      <span>${f.name}</span>
      <span class="category">${f.category}</span>
    </div>
  `).join("");
  container.classList.add("visible");
  state.activeResultIndex = -1;

  container.querySelectorAll(".search-item").forEach((item) => {
    item.addEventListener("click", () => selectFoodById(Number(item.dataset.id), item.textContent.trim()));
  });
}

async function selectFoodById(id, nameHint) {
  $("search-results").classList.remove("visible");
  $("food-search").value = nameHint || "";
  const food = await api(`/api/foods/${id}`);
  setSelectedFood(food);
}

async function updatePreview() {
  if (!state.selectedFood) return;
  const weight = Number($("weight").value);
  if (!weight || weight <= 0) return;
  const nutrients = await api(`/api/foods/${state.selectedFood.id}/preview?weight_g=${weight}`);
  $("preview-panel").classList.remove("hidden");
  renderMacroGrid($("preview-macros"), nutrients);
  renderMicroGrid($("preview-micros"), nutrients);
}

async function logFood() {
  if (!state.selectedFood) return;
  const weight = Number($("weight").value);
  const meal = $("meal").value || null;
  const logged_date = $("log-date").value;

  await api("/api/log", {
    method: "POST",
    body: JSON.stringify({
      food_id: state.selectedFood.id,
      weight_g: weight,
      meal,
      logged_date,
    }),
  });

  showToast("Food logged!");
  setSelectedFood(null);
  $("food-search").value = "";
  $("preview-panel").classList.add("hidden");
  loadDailySummary();
}

async function deleteEntry(id) {
  await api(`/api/log/${id}`, { method: "DELETE" });
  showToast("Entry removed");
  loadDailySummary();
}

function renderDailyTotals(totals) {
  const banner = $("daily-totals");
  banner.innerHTML = MACRO_FIELDS.map(({ key, label, unit }) => `
    <div class="total-stat">
      <div class="num">${formatNum(totals[key] || 0, 0)}</div>
      <div class="name">${label} (${unit})</div>
    </div>
  `).join("");
  renderMicroGrid($("daily-micros"), totals);
}

function renderEntries(entries) {
  const list = $("entries-list");
  const empty = $("empty-state");

  if (!entries.length) {
    list.innerHTML = "";
    list.appendChild(empty);
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");
  list.innerHTML = entries.map((e) => {
    const n = e.nutrients;
    const meal = e.meal ? ` · ${e.meal}` : "";
    return `
      <div class="entry-row" data-id="${e.id}">
        <div class="entry-info">
          <div class="name">${e.food_name}</div>
          <div class="meta">${formatNum(e.weight_g, 0)} g${meal}</div>
        </div>
        <div class="entry-macros">
          <strong>${formatNum(n.calories_kcal, 0)}</strong> kcal<br />
          P ${formatNum(n.protein_g)} · C ${formatNum(n.carbs_g)} · F ${formatNum(n.fat_g)}
        </div>
        <button class="btn btn-ghost delete-btn" data-id="${e.id}" title="Remove">✕</button>
      </div>
    `;
  }).join("");

  list.querySelectorAll(".delete-btn").forEach((btn) => {
    btn.addEventListener("click", () => deleteEntry(Number(btn.dataset.id)));
  });
}

async function loadDailySummary() {
  const day = $("log-date").value;
  const summary = await api(`/api/daily?day=${day}`);
  $("entry-count").textContent = `${summary.entry_count} entr${summary.entry_count === 1 ? "y" : "ies"}`;
  renderDailyTotals(summary.totals);
  renderEntries(summary.entries);
}

function shiftDate(days) {
  const d = new Date($("log-date").value + "T12:00:00");
  d.setDate(d.getDate() + days);
  $("log-date").value = d.toISOString().slice(0, 10);
  loadDailySummary();
}

function init() {
  $("log-date").value = todayISO();
  $("log-date").max = todayISO();

  $("food-search").addEventListener("input", (e) => {
    clearTimeout(state.searchTimeout);
    const q = e.target.value.trim();
    if (!q) {
      $("search-results").classList.remove("visible");
      return;
    }
    state.searchTimeout = setTimeout(() => searchFoods(q), 200);
  });

  $("food-search").addEventListener("keydown", (e) => {
    const items = [...$("search-results").querySelectorAll(".search-item")];
    if (!items.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      state.activeResultIndex = Math.min(state.activeResultIndex + 1, items.length - 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      state.activeResultIndex = Math.max(state.activeResultIndex - 1, 0);
    } else if (e.key === "Enter" && state.activeResultIndex >= 0) {
      e.preventDefault();
      items[state.activeResultIndex].click();
      return;
    } else {
      return;
    }

    items.forEach((el, i) => el.classList.toggle("active", i === state.activeResultIndex));
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#food-search") && !e.target.closest("#search-results")) {
      $("search-results").classList.remove("visible");
    }
  });

  $("weight").addEventListener("input", updatePreview);
  $("log-btn").addEventListener("click", logFood);
  $("log-date").addEventListener("change", loadDailySummary);
  $("prev-day").addEventListener("click", () => shiftDate(-1));
  $("next-day").addEventListener("click", () => shiftDate(1));

  loadDailySummary();
}

init();
