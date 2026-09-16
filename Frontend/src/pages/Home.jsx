import { Link } from "react-router-dom";
import {
  ArrowRight,
  BrainCircuit,
  Cpu,
  LineChart,
  Mail,
  Wallet,
  Sparkles,
  Sun,
  Home as HomeIcon,
} from "lucide-react";

const features = [
  {
    icon: Sparkles,
    title: "AI Optimizer Agents",
    text: "Two Microsoft Agent Framework agents analyze your home and tariff — one gathers the data, the other designs the perfect energy plan.",
  },
  {
    icon: LineChart,
    title: "Day-Ahead Forecasting",
    text: "Prophet ML models combine tomorrow's weather with your appliance history to predict exactly how much energy each device will use.",
  },
  {
    icon: Wallet,
    title: "Time-of-Use Savings",
    text: "Peak and off-peak rates are priced into every recommendation, so the plan tells you the rupees saved — not just the kWh.",
  },
  {
    icon: Mail,
    title: "Email Reports",
    text: "Get a clean, human-friendly email summarizing your biggest win and the small tweaks that add up to real savings.",
  },
  {
    icon: Cpu,
    title: "Per-Appliance Precision",
    text: "Recommendations target each device individually — set-points, running windows and full-load scheduling for everything in your home.",
  },
  {
    icon: Sun,
    title: "Weather Aware",
    text: "A cooler or hotter day changes your strategy. WattPilot reads tomorrow's forecast and adapts the plan to it.",
  },
];

const steps = [
  {
    title: "Tell us about your home",
    text: "Number of occupants, the appliances you run and your location.",
  },
  {
    title: "AI designs your plan",
    text: "The agents simulate tomorrow and price each action against your tariff.",
  },
  {
    title: "Apply and save",
    text: "Follow the simple recommendations — and get the whole plan in your inbox.",
  },
];

export default function Home() {
  return (
    <>
      {/* HERO */}
      <section className="hero" id="top">
        <div className="hero-grid" />
        <div className="glow-orb orb-1" />
        <div className="glow-orb orb-2" />
        <div className="container hero-inner">
          <div>
            <span className="eyebrow">
              <Zap2 /> AI-Powered Energy Intelligence
            </span>
            <h1>
              Slash your power bill with <span className="gradient-text">smart scheduling</span>
            </h1>
            <p className="hero-sub">
              WattPilot AI forecasts every appliance in your home, times your
              energy use to dodge peak pricing and sends you an easy
              plan — optimized by AI, written for humans.
            </p>
            <div className="hero-cta">
              <Link to="/optimize" className="btn btn-primary btn-lg">
                Build My Plan <ArrowRight size={18} />
              </Link>
              <Link to="/dashboard" className="btn btn-secondary btn-lg">
                <HomeIcon size={18} /> View Dashboard
              </Link>
            </div>
            <div className="hero-stats">
              <div className="hero-stat">
                <b>Up to 28%</b>
                <span>potential bill savings</span>
              </div>
              <div className="hero-stat">
                <b>Per-appliance</b>
                <span>forecast &amp; actions</span>
              </div>
              <div className="hero-stat">
                <b>24/7</b>
                <span>AI-driven planning</span>
              </div>
            </div>
          </div>

          <div className="hero-visual">
            <div className="hero-card">
              <div>
                <div className="row">
                  <span className="badge">
                    <BrainCircuit size={14} /> Tomorrow's Plan
                  </span>
                  <span className="muted" style={{ fontSize: 11.5 }}>
                    Sep 16 · cooler day
                  </span>
                </div>
                <div className="hero-savings">INR 223</div>
                <div className="muted" style={{ fontSize: 12.5 }}>
                  estimated savings
                </div>
              </div>
              <div style={{ marginTop: 20 }}>
                <div className="bullet-row">
                  <span className="dot" />
                  <span>
                    <b className="gradient-text">Air Conditioning</b> — raise
                    set-point, trim runtime
                  </span>
                </div>
                <div className="bullet-row">
                  <span className="dot" />
                  <span>
                    <b className="gradient-text">Washing Machine</b> — run
                    full loads off-peak
                  </span>
                </div>
                <div className="bullet-row">
                  <span className="dot" />
                  <span>
                    <b className="gradient-text">Computer</b> — auto-sleep
                    during idle hours
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="section" id="feature">
        <div className="container">
          <div style={{ textAlign: "center", marginBottom: 44 }}>
            <span className="eyebrow">
              <Cpu size={14} /> Why WattPilot
            </span>
            <h2 style={{ fontSize: "clamp(20px, 3.2vw, 28px)", margin: "8px 0 4px" }}>
              Everything your energy plan needs
            </h2>
            <p className="muted" style={{ maxWidth: 620, margin: "0 auto" }}>
              One dashboard that turns raw usage and a pricey tariff into
              actions you can actually take.
            </p>
          </div>
          <div className="grid-3">
            {features.map((f) => (
              <div className="card card-hover feature-card" key={f.title}>
                <div className="feature-icon">
                  <f.icon size={22} />
                </div>
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="section-tight" id="how">
        <div className="container">
          <div style={{ textAlign: "center", marginBottom: 40 }}>
            <span className="eyebrow">
              <Sparkles size={14} /> Three simple steps
            </span>
            <h2 style={{ fontSize: "clamp(20px, 3.2vw, 28px)", margin: "8px 0 4px" }}>
              How it works
            </h2>
          </div>
          <div className="steps">
            {steps.map((s) => (
              <div className="step" key={s.title}>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="section" id="cta">
        <div className="container">
          <div className="cta-band">
            <div className="glow-orb orb-3" />
            <Mail size={26} style={{ color: "var(--accent)" }} />
            <h2>Ready to put your energy on autopilot?</h2>
            <p>
              Get a personalized optimization plan in minutes — and have it
              waiting in your inbox, warm and ready to read.
            </p>
            <div className="flex gap wrap justify-between align-center" style={{ justifyContent: "center" }}>
              <Link to="/optimize" className="btn btn-primary btn-lg">
                Start Optimizing <ArrowRight size={18} />
              </Link>
              <Link to="/forecast" className="btn btn-ghost btn-lg">
                Try the Forecast
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}

function Zap2() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  );
}