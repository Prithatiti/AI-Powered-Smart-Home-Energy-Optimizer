import { useEffect, useMemo, useState } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Zap, TrendingUp, Wind, Layers } from "lucide-react";
import { fetchHistory } from "../api/client";
import Loader from "../components/Loader";

const COLORS = ["#34d399", "#38bdf8", "#818cf8", "#fbbf24", "#f472b6", "#fb923c", "#2dd4bf", "#a78bfa"];

function fmt(n) {
  return Number.isFinite(n) ? n.toFixed(1) : "—";
}

export default function Dashboard() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchHistory(500);
        setData(res.records || []);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const stats = useMemo(() => {
    const total = data.reduce((s, r) => s + (r.kwh_consumed || 0), 0);
    const avg = data.length ? total / data.length : 0;
    const days = new Set(data.map((r) => r.date)).size;
    const byAppliance = {};
    data.forEach((r) => {
      byAppliance[r.appliance] = (byAppliance[r.appliance] || 0) + (r.kwh_consumed || 0);
    });
    const topAppliance = Object.entries(byAppliance).sort((a, b) => b[1] - a[1])[0];
    return { total, avg, days, topAppliance };
  }, [data]);

  const dailySeries = useMemo(() => {
    const map = {};
    data.forEach((r) => {
      const key = String(r.date).replace(/\//g, "-");
      map[key] = (map[key] || 0) + (r.kwh_consumed || 0);
    });
    return Object.entries(map)
      .sort((a, b) => (a[0] < b[0] ? -1 : 1))
      .slice(-14)
      .map(([date, kwh]) => ({ date, kwh: Math.round(kwh * 10) / 10 }));
  }, [data]);

  const applianceSeries = useMemo(() => {
    const map = {};
    data.forEach((r) => {
      map[r.appliance] = (map[r.appliance] || 0) + (r.kwh_consumed || 0);
    });
    return Object.entries(map)
      .map(([name, kwh]) => ({ name, value: Math.round(kwh * 10) / 10 }))
      .sort((a, b) => b.value - a.value);
  }, [data]);

  const tooltipStyle = {
    background: "#141e33",
    border: "1px solid rgba(148,163,184,0.25)",
    borderRadius: 10,
    fontSize: 12,
  };

  return (
    <>
      <div className="glow-orb orb-1" />
      <section className="container" style={{ paddingTop: 8 }}>
        <div className="page-head">
          <span className="eyebrow">
            <Layers size={14} /> Live Consumption
          </span>
          <h1>Energy Dashboard</h1>
          <p>A snapshot of your home's appliance-level usage from the last week.</p>
        </div>

        {loading && <Loader text="Loading history..." />}
        {error && (
          <div className="alert alert-error">
            <span>
              Could not reach the backend. Is <b>main.py</b> running on
              <b> 127.0.0.1:8000</b>? ({error})
            </span>
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <Zap className="stat-icon" size={26} />
                <span className="stat-label">Total Usage</span>
                <span className="stat-value">{fmt(stats.total)} kWh</span>
                <span className="stat-sub">across {stats.days} day(s)</span>
              </div>
              <div className="stat-card">
                <TrendingUp className="stat-icon" size={26} />
                <span className="stat-label">Avg / Run</span>
                <span className="stat-value">{fmt(stats.avg)} kWh</span>
                <span className="stat-sub">mean consumption per event</span>
              </div>
              <div className="stat-card">
                <Wind className="stat-icon" size={26} />
                <span className="stat-label">Top Appliance</span>
                <span className="stat-value" style={{ fontSize: 19 }}>
                  {stats.topAppliance ? stats.topAppliance[0] : "—"}
                </span>
                <span className="stat-sub">
                  {stats.topAppliance ? `${fmt(stats.topAppliance[1])} kWh total` : ""}
                </span>
              </div>
              <div className="stat-card">
                <Layers className="stat-icon" size={26} />
                <span className="stat-label">Appliances</span>
                <span className="stat-value">{applianceSeries.length}</span>
                <span className="stat-sub">tracked in this window</span>
              </div>
            </div>

            <div className="grid-2 mt-lg">
              <div className="card">
                <h3 style={{ marginTop: 0 }}>Daily consumption</h3>
                <div style={{ height: 280 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={dailySeries} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                      <defs>
                        <linearGradient id="kwh" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#34d399" stopOpacity={0.5} />
                          <stop offset="100%" stopColor="#34d399" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" vertical={false} />
                      <XAxis dataKey="date" tick={{ fill: "#93a4c0", fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: "#93a4c0", fontSize: 11 }} axisLine={false} tickLine={false} unit=" kWh" />
                      <Tooltip contentStyle={tooltipStyle} />
                      <Area type="monotone" dataKey="kwh" stroke="#34d399" strokeWidth={2.5} fill="url(#kwh)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="card">
                <h3 style={{ marginTop: 0 }}>Usage by appliance</h3>
                <div style={{ height: 280 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={applianceSeries} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: "#93a4c0", fontSize: 10.5 }} axisLine={false} tickLine={false} interval={0} angle={-18} textAnchor="end" height={48} />
                      <YAxis tick={{ fill: "#93a4c0", fontSize: 11 }} axisLine={false} tickLine={false} unit=" kWh" />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(148,163,184,0.06)" }} />
                      <Bar dataKey="value" name="kWh" radius={[6, 6, 0, 0]} maxBarSize={46}>
                        {applianceSeries.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="card mt-lg">
              <h3 style={{ marginTop: 0 }}>Recent events</h3>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Appliance</th>
                      <th>Date</th>
                      <th>Window</th>
                      <th>Mode</th>
                      <th>kWh</th>
                      <th>Avg Temp</th>
                      <th>Weather</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.slice(0, 12).map((r, i) => (
                      <tr key={i}>
                        <td>
                          <b>{r.appliance}</b>
                        </td>
                        <td className="muted">{r.date}</td>
                        <td className="muted">
                          {r.start_time}–{r.end_time}
                        </td>
                        <td className="muted">{r.mode}</td>
                        <td>{fmt(r.kwh_consumed)} kWh</td>
                        <td className="muted">{fmt(r.avg_temp)}°C</td>
                        <td className="muted">{r.weather_condition}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
        {!loading && !error && data.length === 0 && (
          <div className="alert alert-info">
            The dataset returned no records. Check the backend's CSV data source.
          </div>
        )}
      </section>
    </>
  );
}