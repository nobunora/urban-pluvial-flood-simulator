import SmokeApp from "./dev/SmokeApp";

export default function App() {
  if (new URLSearchParams(window.location.search).get("smoke") === "1") {
    return <SmokeApp />;
  }

  return (
    <main>
      <h1>Urban Pluvial Flood Simulator</h1>
      <p>Application skeleton is running.</p>
      <button type="button" onClick={() => { window.location.search = "smoke=1"; }}>
        開発用 Full 1 m 動作確認
      </button>
    </main>
  );
}
