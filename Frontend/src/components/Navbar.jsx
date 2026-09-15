import { useState } from "react";
import { NavLink, Link } from "react-router-dom";
import { Zap, Menu, X, ArrowRight } from "lucide-react";

const links = [
  { to: "/", label: "Home" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/forecast", label: "Forecast" },
  { to: "/optimize", label: "Optimize" },
];

export default function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="nav">
      <div className="container nav-inner">
        <Link to="/" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-logo">
            <Zap size={19} strokeWidth={2.6} />
          </span>
          <span>
            Watt<span className="gradient-text">Pilot</span> AI
          </span>
        </Link>

        <button
          className="nav-burger"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle menu"
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>

        <nav className={`nav-links${open ? " open" : ""}`}>
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `nav-link${isActive ? " active" : ""}`
              }
              onClick={() => setOpen(false)}
            >
              {l.label}
            </NavLink>
          ))}
          <Link
            to="/optimize"
            className="btn btn-primary nav-cta"
            onClick={() => setOpen(false)}
          >
            Get My Plan <ArrowRight size={16} />
          </Link>
        </nav>
      </div>
    </header>
  );
}