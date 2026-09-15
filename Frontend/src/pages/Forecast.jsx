import { useState } from "react";
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { CloudSun, CalendarDays, Gauge, Home as HomeIcon } from "lucide-react";
import { postForecast } from "../api/client";
import Loader from "../components/Loader";
import ApplianceSelector from "../components/ApplianceSelector";

const COLORS = ["#34d399", "#38bdf8", "#818cf8", "#fbbf24", "#f472b6", "#fb923c", "#2dd4bf", "#a78bfa"];

function fmt(n) {
  return Number.isFinite(n) ? Number(n).toFixed(1) : "—";
}

export default function Forecast() {
  const [city, setCity] = useState("Pune");
  const [hhSize, setHhSize] = useState(3);
  const [appliances, setAppliances] = useState(["Air Conditioning", "Refrigerator", "Computer"]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [forecast, setForecast] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setForecast(null);
    if (appliances.length === 0) {
      setError("Pick at least one appliance to forecast.");
      return;
    }
    setLoading(true);
    try {
      const res = await postForecast({
        city: city || null,
        hh_size: hhSize,
        appliances: appliances.map((name) => ({ name })),
        timezone: "Asia/Kolkata",
      });
      setForecast(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const totalKwh = (forecast || []).reduce((s, f) => s + (f.yhat || 0), 0);
  const chartData = (forecast || []).map((f) => ({
    name: f.appliance,
    kwh: Math.round(f.yhat * 10) / 10,
    lower: f.yhat_lower != null ? Math.round(f.yhat_lower * 10) / 10 : null,
    upper: f.yhat_upper != null ? Math.round(f.yhat_upper * 10) / 10 : null,
  }));

  return (
    <>
      <div className="glow-orb orb-2" />
      <section className="container" style={{ paddingTop: 8 }}>
        <div className="page-head">
          <span className="eyebrow">
            <CloudSun size={14} /> Day-Ahead Forecast
          </span>
          <h1>Forecast tomorrow's usage</h1>
          <p>
            Prophet ML models blend tomorrow's weather with your home profile
            to estimate each appliance's kWh.
          </p>
        </div>

        <div className="split-page">
          <form className="card sticky" onSubmit={submit}>
            <h3 style={{ marginTop: 0, display: "flex", gap: 10, alignItems: "center" }}>
              <HomeIcon size={19} /> Your home profile
            </h3>

            <div className="field">
              <label htmlFor="city">City</label>
              <input
                id="city"
                className="input"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="e.g. Pune"
              />
            </div>

            <div className="field mt">
              <label>Household size</label>
              <div className="range-row">
                <input
                  type="range"
                  min="1"
                  max="8"
                  value={hhSize}
                  onChange={(e) => setHhSize(Number(e.target.value))}
                />
                <span className="range-value">{hhSize}</span>
              </div>
            </div>

            <div className="field mt">
              <label>Appliances to forecast</label>
              <ApplianceSelector selected={appliances} onChange={setAppliances} />
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              style={{ width: "100%", marginTop: 22 }}
              disabled={loading}
            >
              {loading ? "Forecasting..." : "Forecast Tomorrow"}
            </button>
          </form>

          <div>
            {error && (
              <div className="alert alert-error">{error}</div>
            )}

            {loading && <Loader text="Running the Prophet models — usually just a few seconds..." />}

            {forecast && !loading && (
              <>
                <div className="stats-grid">
                  <div className="stat-card">
                    <CalendarDays className="stat-icon" size={26} />
                    <span className="stat-label">Forecast Day</span>
                    <span className="stat-value" style={{ fontSize: 19 }}>
                      {forecast[0]?.ds || "Tomorrow"}
                    </span>
                    <span className="stat-sub">{city || "your city"} · Asia/Kolkata</span>
                  </div>
                  <div className="stat-card">
                    <Gauge className="stat-icon" size={26} />
                    <span className="stat-label">Expected Total</span>
                    <span className="stat-value">{fmt(totalKwh)} kWh</span>
                    <span className="stat-sub">across {forecast.length} appliance(s)</span>
                  </div>
                </div>

                <div className="card mt-lg">
                  <h3 style={{ marginTop: 0 }}>Per-appliance forecast (kWh)</h3>
                  <div style={{ height: 300 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={chartData} margin={{ top: 6, right: 8, left: -8, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" vertical={false} />
                        <XAxis dataKey="name" tick={{ fill: "#93a4c0", fontSize: 11 }} axisLine={false} tickLine={false} interval={0} angle={-14} textAnchor="end" height={44} />
                        <YAxis tick={{ fill: "#93a4c0", fontSize: 11 }} axisLine={false} tickLine={false} unit=" kWh" />
                        <Tooltip
                          contentStyle={{ background: "#141e33", border: "1px solid rgba(148,163,184,0.25)", borderRadius: 10, fontSize: 12 }}
                          cursor={{ fill: "rgba(148,163,184,0.06)" }}
                        />
                        <Bar dataKey="kwh" name="kWh" radius={[6, 6, 0, 0]} maxBarSize={52}>
                          {chartData.map((_, i) => (
                            <Cell key={i} fill={COLORS[i % COLORS.length]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="card mt-lg">
                  <h3 style={{ marginTop: 0 }}>Forecast details</h3>
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Appliance</th>
                          <th>kWh (day)</th>
                          <th>Range (95%)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {forecast.map((f, i) => (
                          <tr key={i}>
                            <td>
                              <b>{f.appliance}</b>
                            </td>
                            <td>
                              <span className="badge">{fmt(f.yhat)} kWh</span>
                            </td>
                            <td className="muted">
                              {fmt(f.yhat_lower)} – {fmt(f.yhat_upper)} kWh
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}

            {!loading && !error && !forecast && (
              <div className="card" style={{ textAlign: "center", padding: "60px 30px" }}>
                <div style={{ fontSize: 32 }}>🌤️</div>
                <h3>Configure and forecast</h3>
                <p className="muted" style={{ margin: "0 auto", maxWidth: 380 }}>
                  Fill in your home profile on the left, then run the forecast
                  to see how much energy each appliance will likely draw
                  tomorrow.
                </p>
              </div>
            )}
          </div>
        </div>
      </section>
    </>
  );
}