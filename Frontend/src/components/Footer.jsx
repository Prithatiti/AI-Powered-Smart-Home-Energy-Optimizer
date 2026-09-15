import { Link } from "react-router-dom";
import { Zap } from "lucide-react";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="foot-grid">
          <div className="foot-brand">
            <Link to="/" className="brand" style={{ marginBottom: 14 }}>
              <span className="brand-logo">
                <Zap size={19} strokeWidth={2.6} />
              </span>
              <span>
                Watt<span className="gradient-text">Pilot</span> AI
              </span>
            </Link>
            <p>
              An AI-powered smart home energy optimizer. Forecast your usage,
              outsmart the tariff and keep more money in your pocket.
            </p>
          </div>
          <div className="foot-col">
            <h4>Product</h4>
            <Link to="/dashboard">Dashboard</Link>
            <Link to="/forecast">Day-Ahead Forecast</Link>
            <Link to="/optimize">Optimization Plan</Link>
          </div>
          <div className="foot-col">
            <h4>Technology</h4>
            <a href="#feature">AI Agents</a>
            <a href="#feature">Prophet Forecasts</a>
            <a href="#feature">Time-of-Use Tariffs</a>
          </div>
          <div className="foot-col">
            <h4>Resources</h4>
            <a href="#how">How it works</a>
            <a href="#cta">Get started</a>
          </div>
        </div>
        <div className="foot-bottom">
          <span>© {new Date().getFullYear()} WattPilot AI. All rights reserved.</span>
          <span>Built with React + FastAPI + Azure OpenAI</span>
        </div>
      </div>
    </footer>
  );
}