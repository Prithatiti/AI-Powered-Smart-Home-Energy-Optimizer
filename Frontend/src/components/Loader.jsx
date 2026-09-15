export default function Loader({ text = "Working on it..." }) {
  return (
    <div className="loader">
      <div className="spinner" />
      <div className="loader-text">{text}</div>
    </div>
  );
}