import { useState } from "react";
import {
  BrainCircuit,
  Sparkles,
  Send,
  Mail,
  CheckCircle2,
  TrendingDown,
  Clock,
  IndianRupee,
  X,
  Zap,
} from "lucide-react";
import { postRecommendations, postEmailPlan } from "../api/client";
import Loader from "../components/Loader";
import ApplianceSelector from "../components/ApplianceSelector";

const LOADER_MSGS = [
  "Waking up the AI agents...",
  "Collecting weather & usage data...",
  "Running the Prophet forecasts...",
  "Pricing every action against your tariff...",
  "The optimizer agent is designing your plan...",
];

function fmt(n) {
  return Number.isFinite(n) ? Number(n).toFixed(1) : "—";
}
function fmtMoney(n) {
  return Number.isFinite(n) ? Number(n).toFixed(2) : "—";
}

export default function Optimize() {
  const [hhSize, setHhSize] = useState(4);
  const [appliances, setAppliances] = useState(["Air Conditioning", "Microwave", "Computer", "Washing Machine"]);
  const [ratePeak, setRatePeak] = useState(12.0);
  const [rateOffpeak, setRateOffpeak] = useState(7.5);
  const [startHour, setStartHour] = useState("18");
  const [endHour, setEndHour] = useState("22");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");

  const [state, setState] = useState("idle"); // idle | running | done | error
  const [msgIndex, setMsgIndex] = useState(0);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [sending, setSending] = useState(false);
  const [emailState, setEmailState] = useState(null); // null | done | error
  const [emailReport, setEmailReport] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setEmailReport(null);
    setEmailState(null);
    if (appliances.length === 0) {
      setError("Select at least one appliance to optimize.");
      return;
    }
    setState("running");
    setMsgIndex(0);
    const ticker = setInterval(() => setMsgIndex((i) => (i + 1) % LOADER_MSGS.length), 42000);
    try {
      const res = await postRecommendations({
        hh_size: hhSize,
        appliances_present: appliances,
        rate_peak: ratePeak,
        rate_offpeak: rateOffpeak,
        tariff_peak_start: `${startHour}:00`,
        tariff_peak_end: `${endHour}:00`,
        timezone: "Asia/Kolkata",
      });
      setResult(res);
      setState("done");
    } catch (err) {
      setError(err.message);
      setState("error");
    } finally {
      clearInterval(ticker);
    }
  };

  const emailPlan = async () => {
    if (!result) return;
    setSending(true);
    setEmailState(null);
    try {
      const report = await postEmailPlan({
        email: email || "prithatiti@gmail.com",
        name: name || "User",
        plan_json: result,
      });
      setEmailReport(report);
      setEmailState("done");
    } catch (err) {
      setEmailState("error");
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  const totalKwh = (result?.actions || []).reduce((s, a) => s + (a.estimated_kwh_saving || 0), 0);
  const totalCost = (result?.actions || []).reduce((s, a) => s + (a.estimated_cost_saving || 0), 0);
  const currency = result?.currency || "INR";

  return (
    <>
      <div className="glow-orb orb-1" />
      <section className="container" style={{ paddingTop: 8 }}>
        <div className="page-head">
          <span className="eyebrow">
            <BrainCircuit size={14} /> AI Optimization
          </span>
          <h1>Build your energy plan</h1>
          <p>
            Our two AI agents analyze your home and tariff, then design a
            day-ahead plan that maximizes savings.
          </p>
        </div>

        <div className="split-page">
          <form className="card sticky" onSubmit={submit}>
            <h3 style={{ marginTop: 0, display: "flex", gap: 10, alignItems: "center" }}>
              <Sparkles size={19} /> Configure your home
            </h3>

            <div className="field">
              <label>Household size</label>
              <div className="range-row">
                <input type="range" min="1" max="8" value={hhSize} onChange={(e) => setHhSize(Number(e.target.value))} />
                <span className="range-value">{hhSize}</span>
              </div>
            </div>

            <div className="field mt">
              <label>Appliances to optimize</label>
              <ApplianceSelector selected={appliances} onChange={setAppliances} />
            </div>

            <div className="field mt">
              <label>Peak rate (INR / kWh)</label>
              <input className="input" type="number" step="0.5" min="1" value={ratePeak} onChange={(e) => setRatePeak(Number(e.target.value))} />
            </div>

            <div className="field mt">
              <label>Off-peak rate (INR / kWh)</label>
              <input className="input" type="number" step="0.5" min="1" value={rateOffpeak} onChange={(e) => setRateOffpeak(Number(e.target.value))} />
            </div>

            <div className="field mt">
              <label>Peak window (24h)</label>
              <div className="flex gap">
                <input className="input" type="number" min="0" max="23" value={startHour} onChange={(e) => setStartHour(e.target.value)} />
                <span className="dim" style={{ alignSelf: "center" }}>to</span>
                <input className="input" type="number" min="0" max="23" value={endHour} onChange={(e) => setEndHour(e.target.value)} />
              </div>
            </div>

            <fieldset style={{ border: "1px solid var(--border-strong)", borderRadius: 14, padding: "14px 16px", margin: 0, marginTop: 18 }}>
              <legend style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", padding: "0 6px" }}>
                Email report (optional)
              </legend>
              <div className="field">
                <label>Recipient email</label>
                <input className="input" type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="field" style={{ marginTop: 12 }}>
                <label>Your name</label>
                <input className="input" type="text" placeholder="e.g. Pritha" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
            </fieldset>

            <button type="submit" className="btn btn-primary btn-lg" style={{ width: "100%", marginTop: 22 }} disabled={state === "running" || sending}>
              {state === "running" ? "Designing your plan..." : <><Zap size={18} /> Design My Energy Plan</>}
            </button>
          </form>

          <div>
            {error && <div className="alert alert-error">{error}</div>}

            {state === "running" && (
              <>
                <Loader text={LOADER_MSGS[msgIndex]} />
                <div className="alert alert-info">
                  This usually takes 2–3 minutes while the AI agents run.
                  Grab a coffee ☕
                </div>
              </>
            )}

            {state === "idle" && (
              <div className="card" style={{ textAlign: "center", padding: "60px 30px" }}>
                <div style={{ fontSize: 32 }}>⚡</div>
                <h3>Your plan starts here</h3>
                <p className="muted" style={{ margin: "0 auto", maxWidth: 380 }}>
                  Configure your household on the left and let the AI agents
                  optimize tomorrow for you.
                </p>
              </div>
            )}

            {state === "done" && result && (
              <>
                <div className="stats-grid">
                  <div className="stat-card">
                    <TrendingDown className="stat-icon" size={26} />
                    <span className="stat-label">Est. Cost Saving</span>
                    <span className="stat-value">
                      {currency} {fmtMoney(totalCost)}
                    </span>
                    <span className="stat-sub">next day's plan</span>
                  </div>
                  <div className="stat-card">
                    <Zap className="stat-icon" size={26} />
                    <span className="stat-label">Energy Saved</span>
                    <span className="stat-value">{fmt(totalKwh)} kWh</span>
                    <span className="stat-sub">across {result.actions?.length || 0} actions</span>
                  </div>
                  <div className="stat-card">
                    <Clock className="stat-icon" size={26} />
                    <span className="stat-label">Peak Window</span>
                    <span className="stat-value" style={{ fontSize: 19 }}>
                      {startHour}:00 – {endHour}:00
                    </span>
                    <span className="stat-sub">dodging the expensive band</span>
                  </div>
                </div>

                <div className="card mt-lg">
                  <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 9 }}>
                    <BrainCircuit size={20} /> AI Summary
                  </h3>
                  <p style={{ fontSize: 14, color: "var(--text-muted)", margin: 0 }}>{result.summary}</p>
                </div>

                {result.actions?.length > 0 && (
                  <div className="grid-3 mt-lg">
                    {result.actions.map((a, i) => {
                      const positive = (a.estimated_cost_saving || 0) > 0;
                      return (
                        <div className="action-card" key={i}>
                          <div className="action-head">
                            <span className="action-appliance">
                              <span style={{ color: "var(--accent)" }}><Zap size={16} /></span>
                              {a.appliance}
                            </span>
                            <span className="action-saving">
                              {positive ? `${currency} ${fmtMoney(a.estimated_cost_saving)}` : "Free"}
                            </span>
                          </div>
                          <div className="action-recommendation">{a.recommendation}</div>
                          <div className="action-meta">
                            <span className={`saving-tag${positive ? "" : " zero-tag"}`}>
                              {fmt(a.estimated_kwh_saving)} kWh saved
                            </span>
                            <span className={`saving-tag${positive ? "" : " zero-tag"}`}>
                              {positive ? `${currency} ${fmtMoney(a.estimated_cost_saving)}` : "no saving"}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {result.confidence != null && (
                  <div className="card mt-lg">
                    <h3 style={{ marginTop: 0 }}>Confidence</h3>
                    <div className="confidence-row">
                      <span>Estimate quality</span>
                      <div className="meter">
                        <div className="meter-fill" style={{ width: `${Math.round(result.confidence * 100)}%` }} />
                      </div>
                      <span>{Math.round(result.confidence * 100)}%</span>
                    </div>
                    {result.factors?.length > 0 && (
                      <div className="flex gap wrap mt">
                        {result.factors.map((f, i) => (
                          <span className="badge" key={i}>{f}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="card mt-lg">
                  <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 9 }}>
                    <Mail size={19} /> Email this plan
                  </h3>
                  <p className="muted" style={{ marginTop: 0 }}>
                    The Email Agent rewrites the plan into a friendly report and
                    sends it to the address above.
                  </p>
                  <button className="btn btn-primary" onClick={emailPlan} disabled={sending}>
                    {sending ? "Sending..." : <><Send size={17} /> Email My Plan</>}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </section>

      {emailReport && (
        <div className="overlay" onClick={() => setEmailReport(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between align-center">
              <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 9 }}>
                <CheckCircle2 size={19} style={{ color: "var(--accent)" }} /> Email preview
              </h3>
              <button className="btn btn-ghost" onClick={() => setEmailReport(null)} style={{ padding: "7px 10px" }}>
                <X size={18} />
              </button>
            </div>
            <p className="muted" style={{ fontSize: 13, margin: "8px 0 14px" }}>
              Sent to <b>{emailReport.to}</b> (or composed for preview when SMTP is unconfigured).
            </p>
            <div className="email-preview">
              <div className="subject">{emailReport.subject}</div>
              <div dangerouslySetInnerHTML={{ __html: emailReport.body }} />
            </div>
            <p className="dim" style={{ fontSize: 12, marginBottom: 0 }}>
              <IndianRupee size={12} style={{ verticalAlign: -2 }} /> Delivery is
              best-effort — the composed email is always returned even when SMTP
              is not configured.
            </p>
          </div>
        </div>
      )}
    </>
  );
}