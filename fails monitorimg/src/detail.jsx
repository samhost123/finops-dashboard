// Detail panel for a selected fail

const DetailPanel = ({ fail, stageMode, setStageMode, traceOpen, setTraceOpen }) => {
  if (!fail) {
    return (
      <div className="detail-empty">
        <div className="empty-inner">
          <div className="empty-k">NO FAIL SELECTED</div>
          <div className="empty-h">Select a fail from the queue to run<br/>the two-model pipeline.</div>
          <div className="empty-hint">
            <span className="empty-kbd mono">↑</span>
            <span className="empty-kbd mono">↓</span>
            navigate
            <span style={{margin: "0 8px"}}>·</span>
            <span className="empty-kbd mono">B</span>
            batch-analyze
          </div>
        </div>
      </div>
    );
  }

  const tierCls = `tier-${fail.tier.toLowerCase()}`;
  const priKind =
    fail.priority >= 85 ? "crit" :
    fail.priority >= 65 ? "warn" :
    fail.priority >= 40 ? "ok" : "";
  const covFillColor =
    fail.coverage >= 70 ? "var(--ok)" :
    fail.coverage >= 40 ? "var(--warn)" : "var(--crit)";

  const showS1 = stageMode === "both" || stageMode === "s1";
  const showS2 = stageMode === "both" || stageMode === "s2";
  const onlyOne = stageMode !== "both";

  return (
    <div className="detail">
      {/* Header */}
      <div className="detail-head">
        <div style={{flex: 1, minWidth: 0}}>
          <div className="fid-row">
            <span className="fid-label">FAIL</span>
            <span className="fid-value mono">{fail.id}</span>
            <span className={`chip ${tierCls}`}>{fail.tier}</span>
            {fail.isRegSho && <span className="chip chip-regsho">REG SHO · T-{fail.regShoDays}d</span>}
            {fail.gridlock && <span className="chip chip-gridlock">GRIDLOCK</span>}
          </div>
          <div className="fail-head-title mono">
            {fail.failType} · {fail.ticker}
            <span style={{color: "var(--text-dim)", fontWeight: 400, fontSize: 13, marginLeft: 8}}>
              {fail.name}
            </span>
          </div>
          <div className="fail-head-sub">
            {fail.shares.toLocaleString()} sh · ${Math.round(fail.mv).toLocaleString()} notional
            <span style={{margin: "0 8px", color: "var(--text-mute)"}}>·</span>
            {fail.counterparty} {fail.isPrime ? "(PB)" : "(Exec)"}
            <span style={{margin: "0 8px", color: "var(--text-mute)"}}>·</span>
            {fail.account}
            <span style={{margin: "0 8px", color: "var(--text-mute)"}}>·</span>
            CUSIP {fail.cusip}
          </div>
        </div>
        <div className="stage-toggle">
          <button className={`stg-btn ${stageMode==="both"?"is-active":""}`} onClick={() => setStageMode("both")}>BOTH</button>
          <button className={`stg-btn ${stageMode==="s1"?"is-active":""}`}   onClick={() => setStageMode("s1")}>STAGE 1</button>
          <button className={`stg-btn ${stageMode==="s2"?"is-active":""}`}   onClick={() => setStageMode("s2")}>STAGE 2</button>
        </div>
      </div>

      {/* Metrics strip */}
      <div className="mstrip with-flags">
        <div className="ms">
          <div className="ms-l">PRIORITY</div>
          <div className={`ms-v big ${priKind}`}>{fail.priority}</div>
          <div className="ms-s">of 100</div>
        </div>
        <div className="ms">
          <div className="ms-l">TIER</div>
          <div className={`ms-v ${priKind}`}>{fail.tier}</div>
          <div className="ms-s">{fail.escalation}</div>
        </div>
        <div className="ms">
          <div className="ms-l">AGE</div>
          <div className="ms-v">{fail.age}<span className="sm"> d</span></div>
          <div className="ms-s">{fail.age >= 10 ? "past SLA" : fail.age >= 7 ? "critical band" : "in window"}</div>
        </div>
        <div className="ms">
          <div className="ms-l">COVERAGE</div>
          <div className="ms-v">{fail.coverage}<span className="sm"> %</span></div>
          <div className="cov-bar"><div className="cov-bar-fill" style={{width: fail.coverage + "%", background: covFillColor}}/></div>
        </div>
        <div className="ms">
          <div className="ms-l">REG SHO</div>
          <div className="ms-v">{fail.isRegSho ? `T-${fail.regShoDays}d` : "—"}</div>
          <div className="ms-s">{fail.isRegSho ? "close-out window" : "no deadline"}</div>
        </div>
        <div className="ms">
          <div className="ms-l">FLAGS</div>
          <div className="flag-wrap">
            {fail.flagLabels.map((l, i) => <span key={i} className="flag-tag">{l}</span>)}
          </div>
        </div>
      </div>

      {/* Stage cards */}
      <div className={`stage-grid ${onlyOne ? "one" : ""}`}>
        {showS1 && (
          <section className="stage-card">
            <header className="stage-head">
              <div className="stage-num">01</div>
              <div>
                <div className="stage-title">TRIAGE MODEL</div>
                <div className="stage-sub">Prioritization · Tier · Flags</div>
              </div>
              <div className="stage-meta">triage-v2.3 · 387ms</div>
            </header>
            <div className="assessment">{fail.narrative.triage}</div>
            <div className="kv-grid">
              <div className="kv"><span className="k">Escalation</span><span className="v">{fail.escalation}</span></div>
              <div className="kv"><span className="k">CP class</span><span className="v">{fail.isPrime ? "Prime broker" : "Execution broker"}</span></div>
              <div className="kv"><span className="k">Account</span><span className="v">{fail.account}</span></div>
              <div className="kv"><span className="k">SLA state</span><span className="v">{fail.age >= 10 ? "BREACHED" : fail.age >= 7 ? "AT RISK" : "HEALTHY"}</span></div>
              <div className="kv"><span className="k">CUSIP</span><span className="v">{fail.cusip}</span></div>
              <div className="kv"><span className="k">Fail type</span><span className="v">{fail.failType}</span></div>
            </div>
          </section>
        )}
        {showS2 && (
          <section className="stage-card">
            <header className="stage-head">
              <div className="stage-num">02</div>
              <div>
                <div className="stage-title">RESOLUTION MODEL</div>
                <div className="stage-sub">Action plan · Fallback · Narrative</div>
              </div>
              <div className="stage-meta">resolve-v1.8 · 612ms</div>
            </header>
            {fail.gridlock ? (
              <div className="banner crit">GRIDLOCK DETECTED — an inbound delivery from a separate counterparty appears to be blocking this leg. Chain-match required before bilateral resolution.</div>
            ) : (
              <div className="banner ok">No gridlock detected. Resolution path is unblocked.</div>
            )}

            <div className="steps-title">RECOMMENDED RESOLUTION STEPS</div>
            <ol className="steps">
              {fail.narrative.steps.map((s, i) => (
                <li key={i}>
                  <span className="step-n mono">{String(i+1).padStart(2,"0")}</span>
                  <span className="step-t">{s}</span>
                </li>
              ))}
            </ol>

            <div className="subhead">FALLBACK STRATEGY</div>
            <div className="prose">{fail.narrative.fallback}</div>

            <div className="subhead">MODEL NARRATIVE</div>
            <div className="prose">{fail.narrative.model}</div>

            <div className={`banner-sm banner ${fail.tier==="CRITICAL"||fail.tier==="HIGH"?"warn":"ok"}`}>
              {fail.tier==="CRITICAL"||fail.tier==="HIGH"
                ? `Escalation recommended: ${fail.escalation}`
                : "No escalation required at this tier."}
            </div>
          </section>
        )}
      </div>

      {/* Reasoning trace */}
      <div className="trace">
        <button className="trace-tog" onClick={() => setTraceOpen(!traceOpen)}>
          <span className="mono">{traceOpen ? "▾" : "▸"}</span>
          <span>VIEW AI REASONING TRACE</span>
          <span className="spacer"/>
          <span className="mono" style={{color: "var(--text-mute)"}}>{fail.narrative.trace.length} steps</span>
        </button>
        {traceOpen && (
          <div className="trace-body">
            {fail.narrative.trace.map((t, i) => (
              <div className="trace-line" key={i}>
                <span className="trace-n">{String(i+1).padStart(2,"0")}</span>
                <span className="trace-t">{t}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

window.DetailPanel = DetailPanel;
