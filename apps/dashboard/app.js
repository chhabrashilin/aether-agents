(() => {
  const statusEl = document.getElementById("status");
  const apiBaseEl = document.getElementById("api-base");
  const loadBtn = document.getElementById("load-demo");
  const pipelineBtn = document.getElementById("load-pipeline");
  const episodeMeta = document.getElementById("episode-meta");
  const timelineEl = document.getElementById("timeline");
  const chartEl = document.getElementById("timeline-chart");
  const barsEl = document.getElementById("posterior-bars");
  const attributionJson = document.getElementById("attribution-json");
  const advisorySummary = document.getElementById("advisory-summary");
  const advisoryDisclaimer = document.getElementById("advisory-disclaimer");
  const advisoryJson = document.getElementById("advisory-json");
  const uncertaintyPanel = document.getElementById("uncertainty-panel");
  const scorecardBody = document.querySelector("#scorecard tbody");
  const runMeta = document.getElementById("run-meta");

  function setStatus(msg) {
    statusEl.textContent = msg;
  }

  function fmtTime(iso) {
    try {
      return new Date(iso).toISOString().replace("T", " ").replace(".000Z", "Z");
    } catch {
      return String(iso);
    }
  }

  function renderTimeline(episode) {
    const points = episode.timeline || [];
    if (!points.length) {
      timelineEl.hidden = true;
      chartEl.hidden = true;
      episodeMeta.textContent = `${episode.episode_id} · ${episode.severity} · peak AQI ${episode.aqi_peak ?? "n/a"}`;
      return;
    }
    timelineEl.hidden = false;
    timelineEl.innerHTML = points
      .map(
        (p) =>
          `<span class="tick" data-phase="${p.phase || "none"}">${fmtTime(p.timestamp)} · AQI ${p.aqi ?? "n/a"} · ${p.phase}</span>`
      )
      .join("");

    episodeMeta.textContent = `${episode.episode_id} · ${episode.severity} · peak AQI ${episode.aqi_peak ?? "n/a"} · coverage ${((episode.station_coverage || 0) * 100).toFixed(0)}% · uncertainty ${episode.uncertainty ?? "n/a"}`;

    const aqis = points.map((p) => p.aqi).filter((v) => typeof v === "number");
    if (!aqis.length) {
      chartEl.hidden = true;
      return;
    }
    chartEl.hidden = false;
    const min = Math.min(...aqis);
    const max = Math.max(...aqis);
    const w = 640;
    const h = 160;
    const pad = 16;
    const coords = points.map((p, i) => {
      const x = pad + (i / Math.max(points.length - 1, 1)) * (w - pad * 2);
      const t = max === min ? 0.5 : ((p.aqi ?? min) - min) / (max - min);
      const y = h - pad - t * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    chartEl.innerHTML = `
      <polyline fill="none" stroke="#0d5c63" stroke-width="2"
        points="${coords.join(" ")}" />
      <text x="16" y="18" fill="#4a5568" font-size="11">AQI ${max}</text>
      <text x="16" y="${h - 6}" fill="#4a5568" font-size="11">AQI ${min}</text>
    `;
  }

  function renderUncertainty(critic, attribution) {
    if (!critic) {
      uncertaintyPanel.innerHTML = `<p class="meta-line">No critic output.</p>`;
      return;
    }
    const refused = critic.dominant_refused
      ? `<span class="badge bad">dominant refused (fail-closed)</span>`
      : `<span class="badge ok">dominant allowed</span>`;
    const findings = (critic.findings || [])
      .map(
        (f) =>
          `<li data-sev="${f.severity}"><strong>${f.code}</strong> (${f.severity}, penalty ${f.penalty}): ${f.message}</li>`
      )
      .join("");
    uncertaintyPanel.innerHTML = `
      <div>
        <p class="meta-line">Revised confidence: <strong>${critic.revised_confidence}</strong>
          · missing penalty ${critic.missing_data_penalty}
          · dampening ${critic.overconfidence_dampening}
          · ${refused}</p>
        <p class="meta-line">Attribution confidence (pre-critic): ${attribution?.confidence ?? "n/a"}</p>
        <ul class="findings">${findings}</ul>
      </div>`;
  }

  function renderScorecard(scorecard) {
    const rows = scorecard || [];
    if (!rows.length) {
      scorecardBody.innerHTML =
        '<tr><td colspan="6">No scorecard rows (load fixture pipeline).</td></tr>';
      return;
    }
    // Prefer non-prior rows first for readability; keep priors at end.
    const sorted = [...rows].sort((a, b) => {
      const ap = a.feature === "prior_base" ? 1 : 0;
      const bp = b.feature === "prior_base" ? 1 : 0;
      if (ap !== bp) return ap - bp;
      return Math.abs(b.contribution) - Math.abs(a.contribution);
    });
    scorecardBody.innerHTML = sorted
      .slice(0, 40)
      .map((r) => {
        const val =
          r.feature_value === null || r.feature_value === undefined
            ? "n/a"
            : String(r.feature_value);
        return `<tr>
          <td>${r.source_class}</td>
          <td>${r.feature}</td>
          <td>${val}</td>
          <td>${r.weight}</td>
          <td>${r.contribution}</td>
          <td>${r.rule}</td>
        </tr>`;
      })
      .join("");
  }

  function renderAttribution(attribution, critic) {
    const posts =
      (critic && critic.revised_posteriors) || attribution.posteriors || [];
    barsEl.innerHTML = posts
      .map((p) => {
        const pct = Math.round((p.probability || 0) * 100);
        return `<div class="bar-row">
          <span>${p.label || p.source_class}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
          <span>${pct}%</span>
        </div>`;
      })
      .join("");
    attributionJson.textContent = JSON.stringify(
      { attribution, critic },
      null,
      2
    );
    renderScorecard(attribution?.scorecard);
    renderUncertainty(critic, attribution);
  }

  function renderAdvisory(advisory) {
    advisorySummary.textContent = advisory.summary || "";
    advisoryDisclaimer.textContent = advisory.disclaimer || "";
    advisoryJson.textContent = JSON.stringify(advisory, null, 2);
  }

  function renderScience(result) {
    renderTimeline(result.episode);
    renderAttribution(result.attribution, result.critic);
    renderAdvisory(result.advisory);
  }

  function renderFullPipeline(payload) {
    runMeta.hidden = false;
    runMeta.textContent = `run_id=${payload.run_id} · mode=${payload.mode} · station=${payload.station_id} · observations=${payload.observations_used} · episodes=${payload.episodes_detected}`;
    if (!payload.science) {
      setStatus("Pipeline returned no science block (no episode detected).");
      return;
    }
    renderScience(payload.science);
  }

  function renderDemo(payload) {
    runMeta.hidden = true;
    const result = payload.result || payload;
    renderScience(result);
  }

  async function loadDemo() {
    const base = apiBaseEl.value.replace(/\/$/, "");
    setStatus("Fetching /v1/attribution/demo …");
    try {
      const res = await fetch(`${base}/v1/attribution/demo`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderDemo(data);
      setStatus("Demo loaded.");
    } catch (err) {
      setStatus(
        `Failed: ${err.message}. Start the API (uvicorn) and allow CORS.`
      );
    }
  }

  async function loadPipeline() {
    const base = apiBaseEl.value.replace(/\/$/, "");
    setStatus("Running /v1/pipeline/run?mode=fixture …");
    try {
      const res = await fetch(`${base}/v1/pipeline/run?mode=fixture`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderFullPipeline(data);
      setStatus(
        data.errors?.length
          ? `Pipeline done with errors: ${data.errors.join("; ")}`
          : "Fixture pipeline complete."
      );
    } catch (err) {
      setStatus(`Failed: ${err.message}`);
    }
  }

  if (window.location.protocol.startsWith("http")) {
    // Prefer same-origin /api when served behind CIRRUS ingress.
    const origin = window.location.origin;
    apiBaseEl.value = origin.endsWith("/") ? origin.slice(0, -1) + "/api" : origin + "/api";
    // Local file/static without /api mount: fall back if needed by user.
    if (window.location.port === "8080" || window.location.pathname.includes("dashboard")) {
      // keep /api guess; user can edit
    }
  }

  loadBtn.addEventListener("click", loadDemo);
  pipelineBtn.addEventListener("click", loadPipeline);
})();
