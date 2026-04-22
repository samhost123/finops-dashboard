// Queue table + KPI strip + Top bar

const fmtMoney = (n) => {
  if (n >= 1_000_000) return "$" + (n/1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return "$" + (n/1000).toFixed(0) + "K";
  return "$" + Math.round(n).toLocaleString();
};
const ageClass = (a) => a >= 10 ? "age-crit" : a >= 7 ? "age-warn" : a >= 4 ? "age-ok" : "age-fresh";
const tierCls  = (t) => `tier-${t.toLowerCase()}`;

const Spark = ({ v }) => {
  const w = Math.max(2, (v / 100) * 44);
  const cls = v < 40 ? "low" : v < 70 ? "mid" : "";
  return (
    <div className="spark" style={{ width: 44, height: 4 }}>
      <div className={`spark-fill ${cls}`} style={{ width: w }} />
    </div>
  );
};

const TopBar = ({ accent, onBatch, batchRunning, onTweaks, tweaksOpen }) => {
  const t = new Date();
  const time = t.toLocaleTimeString("en-US", { hour12: false });
  return (
    <div className="topbar">
      <div className="brand">
        <div className="brand-mark">F</div>
        <div>
          <div className="brand-name">FINOPS RESOLVER</div>
          <div className="brand-sub">POST-TRADE FAILS · INTERNAL</div>
        </div>
      </div>
      <div className="top-nav">
        <button className="active">Fails Queue</button>
        <button>Inventory</button>
        <button>Stock Loan</button>
        <button>Audit Log</button>
        <button>Settings</button>
      </div>
      <div className="top-right">
        <div className="status-cluster">
          <div className="status-item"><span className="dot ok"/><span className="label">MODEL</span><span className="val">triage-v2.3 · resolve-v1.8</span></div>
          <div className="status-item"><span className="dot ok"/><span className="label">OLLAMA</span><span className="val">localhost:11434</span></div>
          <div className="status-item"><span className="label">UTC</span><span className="val">{time}</span></div>
        </div>
        <button className={`btn-primary ${batchRunning ? "danger" : ""}`}
                onClick={onBatch}
                style={batchRunning ? {} : { background: accent }}>
          {batchRunning ? "■  CANCEL" : "▶  ANALYZE ALL"}
        </button>
        <button className="btn-ghost" onClick={onTweaks}>{tweaksOpen ? "✕ TWEAKS" : "⚙ TWEAKS"}</button>
      </div>
    </div>
  );
};

const KpiStrip = ({ fails, analyzedIds, batchRunning, batchProgress, batchCurrent, onCancel }) => {
  const total = fails.length;
  const critical = fails.filter(f => f.tier === "CRITICAL").length;
  const escalate = fails.filter(f => f.tier === "CRITICAL" || f.tier === "HIGH").length;
  const avgCov = Math.round(fails.reduce((a,f)=>a+f.coverage,0)/total);
  const gridlock = fails.filter(f => f.gridlock).length;
  const regSho = fails.filter(f => f.isRegSho).length;
  const notional = fails.reduce((a,f)=>a+f.mv,0);
  const analyzedPct = Math.round((analyzedIds.size/total)*100);

  const K = (label, val, sub, kind) => (
    <div className={`kpi ${kind||""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-val">{val}</div>
      <div className="kpi-sub">{sub}</div>
    </div>
  );

  return (
    <div className="kpis">
      {K("OPEN FAILS", total, "monitored")}
      {K("CRITICAL", critical, `${Math.round(critical/total*100)}% of book`, critical>0?"crit":"")}
      {K("NEEDS ESCALATION", escalate, "VP + desk supv.", escalate>5?"warn":"")}
      {K("AVG COVERAGE", avgCov + "%", avgCov>=60?"healthy inventory":"thin inventory")}
      {K("GRIDLOCK", gridlock, "chain-match needed", gridlock>0?"warn":"")}
      {K("REG SHO", regSho, "close-out eligible", regSho>0?"crit":"")}
      {K("NOTIONAL EXPOSURE", fmtMoney(notional), "across open book")}
      <div className="kpi batch-cell">
        <div className="kpi-label">AI PIPELINE</div>
        {!batchRunning ? (
          <>
            <div className="kpi-val mono">{analyzedIds.size}<span className="of">/{total}</span></div>
            <div className="batch-meta">
              <span>{analyzedPct}% analyzed</span>
              <span>press B to batch</span>
            </div>
            <div className="ai-bar"><div style={{width: analyzedPct + "%"}}/></div>
          </>
        ) : (
          <>
            <div className="batch-status pulse">ANALYZING · {Math.round(batchProgress)}%</div>
            {batchCurrent && <div className="batch-current mono">→ {batchCurrent}</div>}
            <div className="ai-bar"><div style={{width: batchProgress + "%"}}/></div>
            <div className="batch-meta">
              <span>stage 1 · stage 2</span>
              <button className="bp-cancel" onClick={onCancel}>CANCEL</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

const QueueTable = ({ fails, selectedId, onSelect, analyzedIds, filter, setFilter, batchCurrentId }) => {
  const filters = ["ALL","CRITICAL","HIGH","MEDIUM","LOW","REG SHO","GRIDLOCK"];
  const filtered = React.useMemo(() => {
    return fails.filter(f => {
      if (filter === "ALL") return true;
      if (filter === "REG SHO") return f.isRegSho;
      if (filter === "GRIDLOCK") return f.gridlock;
      return f.tier === filter;
    });
  }, [fails, filter]);

  return (
    <>
      <div className="queue-head">
        <div className="panel-title">FAIL QUEUE</div>
        <div className="panel-sub mono">{filtered.length} of {fails.length} fails</div>
        <div className="qh-filters">
          {filters.map(f => (
            <button key={f} className={`qf-btn ${filter===f?"is-active":""}`} onClick={()=>setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>
      <div className="queue-scroll">
        <table className="qtab">
          <thead>
            <tr>
              <th>TIER</th>
              <th className="right">PRI</th>
              <th>ID</th>
              <th>SECURITY</th>
              <th>TYPE</th>
              <th>COUNTERPARTY</th>
              <th>ACCT</th>
              <th className="right">SHARES</th>
              <th className="right">NOTIONAL</th>
              <th className="right">AGE</th>
              <th>REG SHO</th>
              <th>COVERAGE</th>
              <th>FLAGS</th>
              <th>AI</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(f => {
              const sel = f.id === selectedId;
              const analyzed = analyzedIds.has(f.id);
              const isCurrent = f.id === batchCurrentId;
              return (
                <tr key={f.id}
                    className={`qrow ${sel?"is-sel":""} ${isCurrent?"pulse":""}`}
                    onClick={() => onSelect(f.id)}>
                  <td>
                    <span className={`tdot ${tierCls(f.tier)}`}/>
                    <span className={`tier-name ${tierCls(f.tier)}`}>{f.tier.slice(0,4)}</span>
                  </td>
                  <td className="right mono">{f.priority}</td>
                  <td className="mono">{f.id}</td>
                  <td>
                    <div className="sym mono">{f.ticker}</div>
                    <div className="cusip mono">{f.cusip}</div>
                  </td>
                  <td>{f.failType}</td>
                  <td>
                    <span className={`cp-dot ${f.isPrime?"cp-prime":"cp-exec"}`}/>
                    <span className="cp-name">{f.counterparty}</span>
                  </td>
                  <td className="mono" style={{color: "var(--text-dim)"}}>{f.account}</td>
                  <td className="right mono">{f.shares.toLocaleString()}</td>
                  <td className="right mono">{fmtMoney(f.mv)}</td>
                  <td className="right"><span className={`age-pill ${ageClass(f.age)}`}>{f.age}d</span></td>
                  <td>{f.isRegSho ? <span className="rs-pill mono">T-{f.regShoDays}d</span> : <span className="muted">—</span>}</td>
                  <td>
                    <div className="cov-wrap">
                      <Spark v={f.coverage}/>
                      <span className="cov-n mono">{f.coverage}%</span>
                    </div>
                  </td>
                  <td>
                    <div className="fchips">
                      {f.flags.slice(0,2).map(c => <span key={c} className="fchip mono">{c}</span>)}
                      {f.flags.length > 2 && <span className="fchip-more mono">+{f.flags.length-2}</span>}
                    </div>
                  </td>
                  <td>{analyzed ? <span className="ai-done">●</span> : <span className="ai-pending">○</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
};

Object.assign(window, { TopBar, KpiStrip, QueueTable, fmtMoney, ageClass, tierCls });
