import { useState } from "react";
import { runContractProbe, type ProbeReport } from "./runContractProbe.ts";

export default function ContractProbe() {
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<ProbeReport | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const onRun = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const next = await runContractProbe();
      setReport(next);
    } catch {
      setReport(null);
      setRunError("Probe runner stopped unexpectedly.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <main style={{ maxWidth: 880, margin: "1.5rem auto", padding: "0 1rem" }}>
      <h1>A12 Contract Probe</h1>
      <p>Development-only check of the typed API client against the running backend.</p>
      <button type="button" onClick={() => void onRun()} disabled={running}>
        {running ? "Running…" : "Run probe"}
      </button>

      {runError ? <p>{runError}</p> : null}

      {report ? (
        <section>
          <h2>{report.ok ? "PASS" : "FAIL"}</h2>
          <p>
            total {report.total} · passed {report.passed} · failed {report.failed}
          </p>
          <ol>
            {report.steps.map((step) => (
              <li key={step.name}>
                <strong>{step.ok ? "PASS" : "FAIL"}</strong> {step.name}
                {step.httpStatus !== undefined ? ` · HTTP ${String(step.httpStatus)}` : ""}
                <div>{step.message}</div>
              </li>
            ))}
          </ol>
          <details>
            <summary>JSON report</summary>
            <pre>{JSON.stringify(report, null, 2)}</pre>
          </details>
        </section>
      ) : null}
    </main>
  );
}
