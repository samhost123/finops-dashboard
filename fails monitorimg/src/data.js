// Synthetic fail dataset + AI narratives. Attached to window.FINOPS.

(function(){
  const PRIME = [
    "Aldrich Prime","Keystone PB","Meridian Clearing","Arbor Prime","Halcyon Stock Loan",
    "Northpoint PB","Vanguard Prime Desk","Cedarwood SecFin","Blackstone Prime","Tethys Prime"
  ];
  const EXEC = [
    "Halberd CM","Rowe & Finch","Sterling Ridge","Pemberton","Orion Exec","Ashcroft",
    "Caldera Trading","Westvale","Ironwood","Lattice MM","Sable River","Dunmoor",
    "Granite Peak","Marlow Exec","Penrose","Thorne Markets","Vantage Point","Quarry & Vale",
    "Helmsford","Bramley","Covington","Elmwood","Faircroft","Glenharrow","Hartwell",
    "Isenberg","Jarrow","Kilbride","Linfield","Monteith","Nivelle","Overton","Pilgrim",
    "Quessant","Redstone","Shelbourne","Talmadge","Undercliff","Velour","Wingate","Xylon"
  ];
  const TICKERS = [
    ["037833100","AAPL","Apple Inc."],["594918104","MSFT","Microsoft"],["023135106","AMZN","Amazon"],
    ["67066G104","NVDA","NVIDIA"],["88160R101","TSLA","Tesla"],["30303M102","META","Meta"],
    ["02079K305","GOOGL","Alphabet A"],["084670702","BRK.B","Berkshire B"],["46625H100","JPM","JPMorgan"],
    ["92826C839","V","Visa"],["91324P102","UNH","UnitedHealth"],["478160104","JNJ","J&J"],
    ["931142103","WMT","Walmart"],["68389X105","ORCL","Oracle"],["806857108","SCHW","Schwab"],
    ["172967424","C","Citigroup"],["949746101","WFC","Wells Fargo"],["00287Y109","ABBV","AbbVie"],
    ["718172109","PFE","Pfizer"],["G0R2N1101","SHEL","Shell ADR"],["G3910J112","RIO","Rio Tinto"],
    ["225401108","CVX","Chevron"],["30231G102","XOM","Exxon"],["254687106","DIS","Disney"],
    ["57636Q104","MA","Mastercard"]
  ];
  const FAIL_TYPES = ["CNS Fail","DVP Fail","B2B Pending","Corporate Action","Trade Dispute (DK)"];
  const ACCOUNTS = ["FIRM-001","FIRM-037","CUST-4421","CUST-8812","PROP-011","OMNIBUS-A","CUST-6677","CUST-2204"];
  const FLAGS = [
    {c:"REG_SHO",l:"Reg SHO threshold security"},
    {c:"HTB",l:"Hard-to-borrow"},
    {c:"CORP_ACT",l:"Active corporate action"},
    {c:"PARTIAL",l:"Partial delivery received"},
    {c:"RECALL",l:"Stock loan recall in flight"},
    {c:"CLIENT_BREAK",l:"Client trade break unresolved"},
    {c:"CTPY_UNRESP",l:"Counterparty non-responsive"},
    {c:"BUYIN_ELIGIBLE",l:"Buy-in eligible"}
  ];

  function mul32(s){return function(){let t=s+=0x6D2B79F5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296}}
  const rnd=mul32(42);
  const pick=a=>a[Math.floor(rnd()*a.length)];
  const ri=(a,b)=>Math.floor(rnd()*(b-a+1))+a;

  function make(i){
    const [cusip,sym,name]=pick(TICKERS);
    const failType=pick(FAIL_TYPES);
    const shares=[200,500,750,1000,1500,2500,5000,7500,10000,15000,25000][ri(0,10)];
    const price=30+rnd()*540;
    const mv=shares*price;
    const age=ri(1,14);
    const coverage=Math.max(0,Math.min(100,Math.round(20+rnd()*95)));
    const cp=rnd()<0.45?pick(PRIME):pick(EXEC);
    const isPrime=PRIME.includes(cp);
    const isRegSho=rnd()<0.35;
    const fcnt=ri(1,3);
    const fset=new Set();
    while(fset.size<fcnt)fset.add(FLAGS[ri(0,FLAGS.length-1)].c);
    if(isRegSho)fset.add("REG_SHO");
    const flags=[...fset];
    const gridlock=failType==="B2B Pending"&&coverage<40&&rnd()<0.6;
    const priority=Math.min(99,Math.round(age*4.2+Math.min(mv/20000,45)+(isRegSho?22:0)+(100-coverage)*0.18+(gridlock?10:0)));
    const tier=priority>=85||age>=10?"CRITICAL":priority>=65||age>=7?"HIGH":priority>=40?"MEDIUM":"LOW";
    const escalation={CRITICAL:"VP / Settlements Head",HIGH:"Desk Supervisor",MEDIUM:"Ops Analyst",LOW:"Queue · monitor"}[tier];
    const regShoDays=isRegSho?Math.max(0,13-age):null;
    return {id:`FID-${10000+i}`,ticker:sym,cusip,name,failType,shares,price,mv,age,coverage,
      counterparty:cp,isPrime,account:pick(ACCOUNTS),isRegSho,regShoDays,flags,gridlock,
      priority,tier,escalation};
  }

  const DATA=[];
  for(let i=0;i<50;i++)DATA.push(make(i));
  DATA.sort((a,b)=>{
    const o={CRITICAL:0,HIGH:1,MEDIUM:2,LOW:3};
    if(o[a.tier]!==o[b.tier])return o[a.tier]-o[b.tier];
    if(b.age!==a.age)return b.age-a.age;
    return b.priority-a.priority;
  });

  // ---------- Narrative generation ----------
  function triage(f){
    const age=f.age>=10?`aged ${f.age} business days — past our SLA window`:
              f.age>=7?`${f.age} days aged, entering the critical band`:
              f.age>=4?`${f.age} days aged, still recoverable`:
              `only ${f.age} day${f.age===1?"":"s"} old`;
    const mv=f.mv>2_000_000?`material notional exposure at $${(f.mv/1e6).toFixed(2)}M`:
             f.mv>500_000?`meaningful exposure at $${(f.mv/1e3).toFixed(0)}K`:
             `modest exposure at $${(f.mv/1e3).toFixed(0)}K`;
    const rs=f.isRegSho?` This security is on the Reg SHO threshold list with ${f.regShoDays} business day${f.regShoDays===1?"":"s"} remaining before mandatory close-out.`:"";
    const cp=f.isPrime?` The counterparty is one of our prime brokers, giving us direct stock-loan channels to work through.`:
             ` The counterparty is an execution broker, which limits remediation to bilateral recall or buy-in.`;
    return `This ${f.failType.toLowerCase()} on ${f.ticker} (${f.shares.toLocaleString()} sh) is ${age}, with ${mv}.${rs}${cp}`;
  }
  function steps(f){
    const s=[];
    if(f.coverage>=80){
      s.push(`Confirm ${f.shares.toLocaleString()} ${f.ticker} in house box — inventory reports ${f.coverage}% coverage.`);
      s.push(`Stage delivery via the cashier to ${f.counterparty} against the open obligation.`);
    } else if(f.coverage>=40){
      s.push(`Deliver the covered leg (${f.coverage}%) immediately to stop the clock on that portion.`);
      s.push(`Route a recall on any out-on-loan ${f.ticker} positions to close the remaining gap.`);
    } else {
      s.push(`Inventory is thin (${f.coverage}%). Source via stock-loan starting with top-tier lenders.`);
      s.push(`Parallel path: check street for same-day availability — ${f.ticker} liquidity supports it.`);
    }
    if(f.gridlock) s.push(`Gridlock suspected. Contact Settlements to chain-match the offsetting inbound position.`);
    if(f.isRegSho&&f.regShoDays<=3) s.push(`Reg SHO deadline imminent (${f.regShoDays}d). Prepare forced buy-in authorization and notify desk head.`);
    if(f.failType==="Trade Dispute (DK)") s.push(`Pull original ticket and confirmations — DK typically signals a mis-booking. Reconcile within 24h.`);
    if(f.failType==="Corporate Action") s.push(`Confirm the corporate action record date and entitlement; coordinate with Asset Servicing on any claim adjustment.`);
    s.push(`Document resolution path in ops log and flag for ${f.escalation} if unresolved by EOD.`);
    return s;
  }
  function fallback(f){
    if(f.coverage<30&&f.age>=7) return `If stock-loan sourcing doesn't land within 24h, fall back to authorized buy-in at market. Given age (${f.age}d) and coverage (${f.coverage}%), further delay risk outweighs execution cost.`;
    if(f.gridlock) return `Primary fallback is a chain-match with the offsetting inbound. If Settlements can't identify the chain by T+1, escalate to bilateral cancel-and-correct.`;
    if(f.isPrime) return `Fallback leverages the prime brokerage relationship — a direct stock-loan call should clear within one business day. If that fails, escalate via the PB relationship manager.`;
    return `Standard fallback: partial delivery against available inventory, recall outstanding loans, hold balance to T+1. Escalate if coverage hasn't improved.`;
  }
  function model(f){
    const risk=f.priority>=85?"critical":f.priority>=65?"elevated":f.priority>=40?"moderate":"low";
    const act=f.tier==="CRITICAL"?"immediate action by the settlements lead":
              f.tier==="HIGH"?"same-day resolution by the responsible desk":
              "routine handling within the ops queue";
    const drivers=f.flags.map(c=>FLAGS.find(x=>x.c===c)?.l.toLowerCase()||c).slice(0,2).join(" and ");
    return `The model reads this fail as ${risk}-risk and recommends ${act}. The combination of ${drivers} drives most of the priority score. Resolution is feasible within existing operational channels — no extraordinary intervention is warranted unless coverage deteriorates.`;
  }
  function trace(f){
    return [
      `Record ingested: type=${f.failType}, age=${f.age}d, notional=$${Math.round(f.mv).toLocaleString()}, coverage=${f.coverage}%.`,
      `Reg SHO threshold check: ${f.isRegSho?`match — ${f.regShoDays}d remaining in close-out window.`:"no match."}`,
      `Counterparty classification: ${f.isPrime?"prime broker (direct stock-loan channel)":"execution broker (bilateral channel only)"}.`,
      `Aging bucket: ${f.age>=10?"CRITICAL (10+d)":f.age>=7?"HIGH (7-9d)":f.age>=4?"MEDIUM (4-6d)":"LOW (1-3d)"} → weight ${(f.age*4.2).toFixed(1)} pts.`,
      `Notional weight ${Math.min(f.mv/20000,45).toFixed(1)} pts; coverage-gap weight ${((100-f.coverage)*0.18).toFixed(1)} pts.`,
      `Flags: ${f.flags.join(", ")}. Gridlock detector: ${f.gridlock?"TRUE — inbound chain suspected":"FALSE"}.`,
      `Composite priority ${f.priority}/100 → tier ${f.tier}. Routing to ${f.escalation}.`,
      `Stage 2 plan built against ${f.coverage>=80?"high-coverage":f.coverage>=40?"partial-coverage":"low-coverage"} playbook.`,
      `No policy violations detected. Emitting resolution package.`
    ];
  }

  DATA.forEach(f=>{
    f.narrative={triage:triage(f),steps:steps(f),fallback:fallback(f),model:model(f),trace:trace(f)};
    f.flagLabels=f.flags.map(c=>FLAGS.find(x=>x.c===c)?.l||c);
  });

  window.FINOPS={DATA,FLAGS,FAIL_TYPES};
})();
