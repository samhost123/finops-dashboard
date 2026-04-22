// Main App shell — orchestrates selection, batch run, tweaks, keyboard

const { useState, useEffect, useRef } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "dark",
  "accent": "#4ED6C9"
}/*EDITMODE-END*/;

const ACCENTS = [
  { name: "Cyan",   val: "#4ED6C9" },
  { name: "Amber",  val: "#F2B24B" },
  { name: "Violet", val: "#B5A3F0" },
  { name: "Lime",   val: "#C0E66C" },
  { name: "Coral",  val: "#F08970" }
];

const Tweaks = ({ tweaks, setTweaks, onClose }) => (
  <div className="tweaks">
    <div className="tw-head">TWEAKS</div>
    <div className="tw-row">
      <div className="tw-lab">THEME</div>
      <div className="tw-group">
        {["dark","light"].map(t => (
          <button key={t}
                  className={`tw-chip ${tweaks.theme===t?"is-on":""}`}
                  onClick={()=>setTweaks({...tweaks, theme: t})}>{t}</button>
        ))}
      </div>
    </div>
    <div className="tw-row">
      <div className="tw-lab">ACCENT</div>
      <div className="tw-group">
        {ACCENTS.map(a => (
          <button key={a.val}
                  className={`tw-swatch ${tweaks.accent===a.val?"is-on":""}`}
                  style={{background: a.val}}
                  title={a.name}
                  onClick={()=>setTweaks({...tweaks, accent: a.val})}/>
        ))}
      </div>
    </div>
  </div>
);

const App = () => {
  const fails = window.FINOPS.DATA;
  const [selectedId, setSelectedId] = useState(() => {
    try { return localStorage.getItem("finops:sel") || fails[0]?.id; } catch(e){ return fails[0]?.id; }
  });
  const [filter, setFilter] = useState("ALL");
  const [stageMode, setStageMode] = useState("both");
  const [traceOpen, setTraceOpen] = useState(false);
  const [analyzedIds, setAnalyzedIds] = useState(() => new Set([selectedId]));

  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState(0);
  const [batchCurrent, setBatchCurrent] = useState(null);
  const [batchCurrentId, setBatchCurrentId] = useState(null);
  const cancelRef = useRef(false);

  const [tweaksOpen, setTweaksOpen] = useState(false);
  const [tweaks, setTweaks] = useState(TWEAK_DEFAULTS);

  const selected = fails.find(f => f.id === selectedId) || null;

  useEffect(() => {
    try { localStorage.setItem("finops:sel", selectedId); } catch(e){}
    if (selectedId) setAnalyzedIds(prev => { const n = new Set(prev); n.add(selectedId); return n; });
  }, [selectedId]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", tweaks.theme);
    document.documentElement.style.setProperty("--accent", tweaks.accent);
  }, [tweaks]);

  // Tweaks protocol
  useEffect(() => {
    const handler = (e) => {
      if (!e.data || typeof e.data !== "object") return;
      if (e.data.type === "__activate_edit_mode") setTweaksOpen(true);
      if (e.data.type === "__deactivate_edit_mode") setTweaksOpen(false);
    };
    window.addEventListener("message", handler);
    window.parent.postMessage({ type: "__edit_mode_available" }, "*");
    return () => window.removeEventListener("message", handler);
  }, []);

  useEffect(() => {
    window.parent.postMessage({
      type: "__edit_mode_set_keys",
      edits: tweaks
    }, "*");
  }, [tweaks]);

  const startBatch = async () => {
    if (batchRunning) return;
    cancelRef.current = false;
    setBatchRunning(true);
    setBatchProgress(0);
    const total = fails.length;
    const fresh = new Set(analyzedIds);
    for (let i = 0; i < total; i++) {
      if (cancelRef.current) break;
      const f = fails[i];
      setBatchCurrent(`${f.id} · ${f.ticker} · ${f.failType}`);
      setBatchCurrentId(f.id);
      // simulate pipeline latency (fast enough to demo)
      await new Promise(r => setTimeout(r, 55 + Math.random() * 35));
      fresh.add(f.id);
      setAnalyzedIds(new Set(fresh));
      setBatchProgress(((i+1)/total) * 100);
    }
    setBatchRunning(false);
    setBatchCurrent(null);
    setBatchCurrentId(null);
  };

  const cancelBatch = () => { cancelRef.current = true; };

  // Keyboard
  useEffect(() => {
    const onKey = (e) => {
      const tg = e.target;
      if (tg && (tg.tagName === "INPUT" || tg.tagName === "TEXTAREA")) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const i = fails.findIndex(f => f.id === selectedId);
        if (i >= 0 && i < fails.length-1) setSelectedId(fails[i+1].id);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const i = fails.findIndex(f => f.id === selectedId);
        if (i > 0) setSelectedId(fails[i-1].id);
      } else if ((e.key === "b" || e.key === "B") && !batchRunning) {
        startBatch();
      } else if (e.key === "Escape" && batchRunning) {
        cancelBatch();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, batchRunning, fails]);

  return (
    <div className="app">
      <TopBar
        accent={tweaks.accent}
        onBatch={batchRunning ? cancelBatch : startBatch}
        batchRunning={batchRunning}
        onTweaks={()=>setTweaksOpen(!tweaksOpen)}
        tweaksOpen={tweaksOpen}
      />
      <KpiStrip
        fails={fails}
        analyzedIds={analyzedIds}
        batchRunning={batchRunning}
        batchProgress={batchProgress}
        batchCurrent={batchCurrent}
        onCancel={cancelBatch}
      />
      <div className="main">
        <div className="left-col">
          <QueueTable
            fails={fails}
            selectedId={selectedId}
            onSelect={setSelectedId}
            analyzedIds={analyzedIds}
            filter={filter}
            setFilter={setFilter}
            batchCurrentId={batchCurrentId}
          />
        </div>
        <div className="right-col">
          <DetailPanel
            fail={selected}
            stageMode={stageMode}
            setStageMode={setStageMode}
            traceOpen={traceOpen}
            setTraceOpen={setTraceOpen}
          />
        </div>
      </div>
      <div className="statusbar">
        <div className="sb-item"><span>ENV</span><span className="v">prod-replica</span></div>
        <div className="sb-item"><span>DATA</span><span className="v">synthetic · {fails.length} fails</span></div>
        <div className="sb-item"><span>PIPELINE</span><span className="v">triage-v2.3 → resolve-v1.8</span></div>
        <div className="spacer"/>
        <div className="sb-item"><span className="v">↑↓ navigate</span></div>
        <div className="sb-item"><span className="v">B batch</span></div>
        <div className="sb-item"><span className="v">ESC cancel</span></div>
      </div>
      {tweaksOpen && <Tweaks tweaks={tweaks} setTweaks={setTweaks}/>}
    </div>
  );
};

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
