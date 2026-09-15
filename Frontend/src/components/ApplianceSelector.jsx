import { Check } from "lucide-react";

const APPLIANCES = [
  "Air Conditioning",
  "Refrigerator",
  "Washing Machine",
  "Dishwasher",
  "Microwave",
  "Computer",
  "TV",
  "Water Heater",
  "Electric Stove",
  "Clothes Dryer",
  "Other",
];

export default function ApplianceSelector({ selected, onChange }) {
  const toggle = (name) => {
    onChange(
      selected.includes(name)
        ? selected.filter((n) => n !== name)
        : [...selected, name]
    );
  };

  return (
    <div className="chip-grid">
      {APPLIANCES.map((name) => {
        const isSelected = selected.includes(name);
        return (
          <button
            type="button"
            key={name}
            className={`chip${isSelected ? " selected" : ""}`}
            onClick={() => toggle(name)}
          >
            {isSelected && <Check size={15} strokeWidth={3} />}
            {name}
          </button>
        );
      })}
    </div>
  );
}