
  const items=document.querySelectorAll('[data-nav]'),pages=document.querySelectorAll('[data-page]');
  document.querySelectorAll('table.dt th').forEach(function(th){
    th.addEventListener('click',function(){
      var tb=th.closest('table').querySelector('tbody'), rows=[].slice.call(tb.children);
      var k=th.dataset.k, num=th.classList.contains('num');
      var dir=th.dataset.dir==='asc'?-1:1; th.dataset.dir=dir===1?'asc':'desc';
      rows.sort(function(a,b){var x=a.dataset[k],y=b.dataset[k]; if(num){x=parseFloat(x);y=parseFloat(y);} return x<y?-dir:(x>y?dir:0);});
      rows.forEach(function(r){tb.appendChild(r);});
    });
  });
  function show(id){
    pages.forEach(p=>p.classList.toggle('active',p.dataset.page===id));
    items.forEach(n=>n.classList.toggle('on',n.dataset.nav===id));

    if(history.replaceState){history.replaceState(null,'','#'+id);}
  }
  /* C (#90 motion) : View Transitions API pour morph entre pages.
     Capture snapshot avant + apres show(), browser crossfade smoothement.
     Fallback gracieux si pas supporte (Firefox <128, vieux Safari) : show() direct. */
  function navTo(id){
    if (document.startViewTransition) {
      document.startViewTransition(function(){ show(id); });
    } else {
      show(id);
    }
  }
  items.forEach(n=>n.addEventListener('click',()=>navTo(n.dataset.nav)));
  /* (Drop 03/06 deep audit : CountUp B retire -- gadget visible 1-2 fois/jour,
     pas assez de valeur vs cout cognitif. C (View Transitions nav) garde. */
  var _h=(location.hash||'').replace('#','');if(_h&&/^[a-z]+$/.test(_h))show(_h);
  // Cmd+1..9 retire 01/06 user feedback : pas utile, parasite plus qu'autre chose
  // Sticky page header drop shadow on scroll (Stripe/Linear pattern) :
  // ajoute .stuck class quand top scrolle past 1px, retire sinon.
  (function(){
    var headers=document.querySelectorAll('.phead');
    if(!headers.length || !window.IntersectionObserver) return;
    // Sentinel 1px before each header to detect stickiness
    headers.forEach(function(h){
      var sentinel=document.createElement('div');
      sentinel.style.cssText='position:absolute;top:-1px;height:1px;width:100%;pointer-events:none;';
      h.parentNode.insertBefore(sentinel, h);
      var obs=new IntersectionObserver(function(entries){
        h.classList.toggle('stuck', !entries[0].isIntersecting);
      }, {threshold:[0]});
      obs.observe(sentinel);
    });
  })();
  // Sparkline interactive hover (Robinhood pattern) : crosshair + tooltip
  // valeur sur le point survole le plus proche.
  (function(){
    Array.from(document.querySelectorAll('.ps-spark-wrap')).forEach(function(wrap){
      var svg=wrap.querySelector('.ps-spark');
      var tip=wrap.querySelector('.spk-tip');
      var cross=wrap.querySelector('.spk-cross');
      var cur=wrap.querySelector('.spk-cur');
      if(!svg || !tip) return;
      var ptsRaw=svg.getAttribute('data-pts')||'';
      var w=parseFloat(svg.getAttribute('data-w')||'130');
      var pts=ptsRaw.split(';').map(function(s){
        var p=s.split('|');
        return {x:parseFloat(p[0]),y:parseFloat(p[1]),val:p[2],date:p[3]};
      });
      if(!pts.length) return;
      svg.addEventListener('mousemove', function(e){
        var rect=svg.getBoundingClientRect();
        var mx=(e.clientX-rect.left)/rect.width*w;
        // find nearest point
        var best=pts[0], bestD=Math.abs(pts[0].x-mx);
        for(var i=1;i<pts.length;i++){
          var d=Math.abs(pts[i].x-mx);
          if(d<bestD){best=pts[i];bestD=d;}
        }
        cross.setAttribute('x1', best.x);
        cross.setAttribute('x2', best.x);
        cur.setAttribute('cx', best.x);
        cur.setAttribute('cy', best.y);
        var tipLeft=(best.x/w*rect.width);
        tip.style.left=tipLeft+'px';
        tip.style.display='block';
        tip.innerHTML='<span class="tip-val">'+Number(best.val).toLocaleString('fr-FR')+'&nbsp;€</span><span class="tip-date">'+best.date+'</span>';
      });
      svg.addEventListener('mouseleave', function(){
        tip.style.display='none';
      });
    });
  })();
  // Right-click context menu ticker (Bloomberg/TradingView pattern) : sur
  // tout element avec data-tk, ouvre menu avec actions Analyse / Copie /
  // Yahoo Finance / Watchlist.
  (function(){
    var menu=document.createElement('div');
    menu.id='ctx-menu';
    menu.style.cssText='position:fixed;display:none;z-index:200;background:var(--panel);border:1px solid var(--line2);border-radius:8px;padding:4px;min-width:180px;box-shadow:0 12px 32px -8px rgba(0,0,0,.25);font-family:var(--fb);font-size:16px;';
    document.body.appendChild(menu);
    function close(){ menu.style.display='none'; }
    function render(tk){
      menu.innerHTML=
        '<div class="ctx-item ctx-tk" style="padding:8px 14px;color:var(--steel);font-size:14px;text-transform:uppercase;letter-spacing:.1em;border-bottom:1px solid var(--line);margin-bottom:4px">'+tk+'</div>'+
        '<div class="ctx-item" data-act="analyze" style="padding:9px 14px;cursor:pointer;border-radius:6px;color:var(--ink)">Analyser (popup loupe)</div>'+
        '<div class="ctx-item" data-act="copy" style="padding:9px 14px;cursor:pointer;border-radius:6px;color:var(--ink)">Copier le ticker</div>'+
        '<div class="ctx-item" data-act="yahoo" style="padding:9px 14px;cursor:pointer;border-radius:6px;color:var(--ink)">Voir sur Yahoo Finance</div>'+
        '<div class="ctx-item" data-act="tv" style="padding:9px 14px;cursor:pointer;border-radius:6px;color:var(--ink)">Voir sur TradingView</div>';
      Array.from(menu.querySelectorAll('.ctx-item[data-act]')).forEach(function(el){
        el.addEventListener('mouseenter', function(){ el.style.background='color-mix(in srgb,var(--ink) 6%,transparent)'; });
        el.addEventListener('mouseleave', function(){ el.style.background='transparent'; });
        el.addEventListener('click', function(){
          var act=el.getAttribute('data-act');
          if(act==='analyze' && typeof openLoupe==='function'){ openLoupe(tk); }
          else if(act==='copy'){ navigator.clipboard && navigator.clipboard.writeText(tk); }
          else if(act==='yahoo'){ window.open('https://finance.yahoo.com/quote/'+encodeURIComponent(tk), '_blank'); }
          else if(act==='tv'){ window.open('https://www.tradingview.com/symbols/'+encodeURIComponent(tk.replace(/\./g,'-')), '_blank'); }
          close();
        });
      });
    }
    document.addEventListener('contextmenu', function(e){
      var el=e.target.closest('[data-tk]');
      if(!el) return;
      var tk=el.getAttribute('data-tk');
      if(!tk) return;
      e.preventDefault();
      render(tk);
      menu.style.display='block';
      // Position au point de clic, clamp dans viewport
      var x=e.clientX, y=e.clientY;
      menu.style.left=Math.min(x, window.innerWidth - 200)+'px';
      menu.style.top=Math.min(y, window.innerHeight - 180)+'px';
    });
    document.addEventListener('click', function(e){
      if(!e.target.closest('#ctx-menu')) close();
    });
    document.addEventListener('keydown', function(e){
      if(e.key==='Escape') close();
    });
  })();
  function _pct(v,sg){ return v==null?'&mdash;':((sg&&v>=0?'+':'')+v+'%'); }
  function mom(l,v){var c=v==null?'var(--steel)':(v>=0?'var(--acc)':'var(--bear)');return '<div class="lp-stat"><div class="lp-sl">'+l+'</div><div class="lp-sv" style="color:'+c+';font-size:19px">'+(v==null?'&mdash;':((v>=0?'+':'')+v+'%'))+'</div></div>';}
  // Sprint 3 logos tickers : map JS mirror du shared/ticker_logos.py
  window._TKDOMAIN = {"AAPL": "apple.com", "MSFT": "microsoft.com", "GOOGL": "google.com", "GOOG": "google.com", "AMZN": "amazon.com", "META": "meta.com", "NVDA": "nvidia.com", "TSLA": "tesla.com", "AMD": "amd.com", "AVGO": "broadcom.com", "MU": "micron.com", "MRVL": "marvell.com", "TSM": "tsmc.com", "KLAC": "kla.com", "TER": "teradyne.com", "SNPS": "www.synopsys.com", "SNOW": "snowflake.com", "ENTG": "entegris.com", "COHR": "coherent.com", "ALAB": "asteralabs.com", "VRT": "vertiv.com", "LNG": "cheniere.com", "CCJ": "cameco.com", "MP": "mpmaterials.com", "ASML.AS": "asml.com", "BESI.AS": "besi.com", "STMPA.PA": "st.com", "SAF.PA": "safran-group.com", "HO.PA": "thalesgroup.com", "SU.PA": "se.com", "4063.T": "shinetsuamerica.com", "6857.T": "advantest.com", "6920.T": "lasertec.co.jp", "7011.T": "mhi.com", "8035.T": "tel.com", "6890.T": "ferrotec.com", "6273.T": "smcworld.com", "6324.T": "harmonicdrive.net", "000660.KS": "skhynix.com", "1347.HK": "hhgrace.com", "0388.HK": "hkex.com.hk", "0700.HK": "tencent.com", "ASM.AS": "asm.com", "HDB": "hdfcbank.com", "INFY": "infosys.com", "ACMR": "acmrcsh.com", "GEV": "gevernova.com", "BWXT": "bwxt.com", "CEG": "constellationenergy.com"};
  window._TKLOCAL = {"COHR": "COHR.png", "7011.T": "7011.T.png", "0700.HK": "0700.HK.png", "INFY": "INFY.png", "ACMR": "ACMR.svg", "ASM.AS": "ASM.AS.png", "4063.T": "4063.T.svg", "GOOG": "GOOG.png", "SNPS": "SNPS.png", "6890.T": "6890.T.png", "AVGO": "AVGO.png", "MP": "MP.png", "6273.T": "6273.T.png", "GEV": "GEV.png", "MU": "MU.png", "VRT": "VRT.png", "SU.PA": "SU.PA.png", "AAPL": "AAPL.png", "CEG": "CEG.png", "ASML.AS": "ASML.AS.png", "BWXT": "BWXT.png", "GOOGL": "GOOGL.png", "6857.T": "6857.T.png", "SNOW": "SNOW.png", "META": "META.png", "TSLA": "TSLA.png", "HO.PA": "HO.PA.png", "6324.T": "6324.T.png", "AMZN": "AMZN.png", "6920.T": "6920.T.svg", "BESI.AS": "BESI.AS.png", "CCJ": "CCJ.png", "MRVL": "MRVL.png", "SAF.PA": "SAF.PA.png", "NVDA": "NVDA.png", "ENTG": "ENTG.png", "STMPA.PA": "STMPA.PA.png", "AMD": "AMD.png", "8035.T": "8035.T.svg", "KLAC": "KLAC.png", "MSFT": "MSFT.png", "HDB": "HDB.svg", "TER": "TER.png", "000660.KS": "000660.KS.png", "TSM": "TSM.png", "ALAB": "ALAB.png", "1347.HK": "1347.HK.svg", "0388.HK": "0388.HK.svg", "LNG": "LNG.png"};
  function _tkLogoJs(tk){
    var init=String(tk||'?').charAt(0).toUpperCase();
    var fb="this.outerHTML='<span class=&quot;tklogo tkfb&quot;>"+init+"</span>'";
    // Priorite 1 : fichier local self-host (offline, sans appel externe)
    var localFile=(window._TKLOCAL||{})[tk]||(window._TKLOCAL||{})[String(tk).toUpperCase()];
    if(localFile){
      return '<img class="tklogo" src="/static/brand/logos/'+localFile+'" alt="'+tk+' logo" loading="lazy" decoding="async" onerror="'+fb+'">';
    }
    var dom=(window._TKDOMAIN||{})[tk]||(window._TKDOMAIN||{})[String(tk).toUpperCase()];
    if(!dom) return '<span class="tklogo tkfb">'+init+'</span>';
    var ddg='https://icons.duckduckgo.com/ip3/'+dom+'.ico';
    var fb2="this.onerror=function(){"+fb+"};this.src='"+ddg+"'";
    return '<img class="tklogo" src="https://www.google.com/s2/favicons?domain='+dom+'&amp;sz=64" alt="'+tk+' logo" loading="lazy" decoding="async" onerror="'+fb2+'">';
  }
  function openLoupe(tk){
    var d=(window.TK||{})[tk]||{};
    var st=d.status||'out';
    var stm={held:['held','held'],watch:['watchlist','watch'],core:['core universe','univ'],extended:['extended universe','univ'],out:['out-of-universe','out']};
    var sb=stm[st]||stm.out;
    var badge='<span class="lp-badge '+sb[1]+'">'+sb[0]+(st==='held'&&d.weight_pct!=null?' &middot; '+d.weight_pct+'%':'')+'</span>';
    var a=d.analysis, sc='';
    if(a&&a.scores){
      var nm={quality:'Quality',growth:'Growth',profitability:'Profitability',valuation:'Valuation',risk:'Risk',momentum:'Momentum',macro_alignment:'Macro'};
      for(var k in nm){ if(a.scores[k]!=null){ var v=Math.round(a.scores[k]); sc+='<div class="lp-score"><span class="ln">'+nm[k]+'</span><span class="bar"><span class="bf" style="width:'+v+'%"></span></span><span class="vv">'+v+'</span></div>'; } }
    }
    var ana = a ? ('<div class="lp-sec">Latest analysis &middot; '+a.date+(a.type?' &middot; '+a.type:'')+'</div>'+sc+(a.regime?'<div class="lp-meta">Regime '+a.regime+(a.narr&&a.narr.length?' &middot; '+a.narr.join(', '):'')+'</div>':'')+(a.excerpt?'<div class="lp-ex">'+a.excerpt+'</div>':'')+'<div class="lp-hint">Full analysis: <code>/analyze '+tk+'</code> on Telegram, or ask in chat.</div>') : '<div class="lp-sec">Analysis</div><div class="lp-empty">No analysis stored. <code>/analyze '+tk+'</code> on Telegram to generate.</div>';
    document.getElementById('loupe-body').innerHTML =
      '<div class="lp-h">'+_tkLogoJs(tk)+'<span class="lp-tk">'+tk+'</span><span class="lp-nm">'+(d.name||'')+'</span></div>'
      +'<div class="lp-meta">'+badge+' &middot; '+(d.sector||'&mdash;')+' &middot; '+(d.country||'&mdash;')+'</div>'
      +((st==='held')?('<div class="lp-grid">'
      +'<div class="lp-stat"><div class="lp-sl">Weight</div><div class="lp-sv">'+d.weight_pct+'%</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Invested</div><div class="lp-sv">'+d.weight_eur+'&euro;</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">P&amp;L</div><div class="lp-sv">'+_pct(d.pnl,true)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Stop margin</div><div class="lp-sv">'+_pct(d.down)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">To target</div><div class="lp-sv">'+_pct(d.up)+'</div></div>'
      +'<div class="lp-stat"><div class="lp-sl">Asymmetry</div><div class="lp-sv">'+(d.ratio==null?'&mdash;':(d.ratio>=999?'target &check;':d.ratio.toFixed(1)+'&times;'))+'</div></div>'
      +'</div>'+(d.perf?('<div class="lp-sec" style="margin-top:16px">Recent momentum</div><div class="lp-mom">'+mom('Day',d.perf.d)+mom('Week',d.perf.w)+mom('Month',d.perf.m)+'</div>'):'')):'<div class="lp-empty" style="padding:var(--s25) 0 2px">No position ouverte sur ce titre.</div>')+ana;
    var lp=document.getElementById('loupe');lp.classList.add('open');lp.setAttribute('aria-hidden','false');
  }
  function closeLoupe(){ var el=document.getElementById('loupe'); if(el){el.classList.remove('open');el.setAttribute('aria-hidden','true');} }
  (function(){
    var BARS=document.getElementById('sb-bars'),PANEL=document.getElementById('sb-panel');
    if(!BARS||!PANEL||!window.SB_DATA)return;
    var DATA=window.SB_DATA;
    DATA.forEach(function(s){s.tw=s.t.reduce(function(a,x){return a+(x.w||0);},0);});
    var total=DATA.reduce(function(a,s){return a+s.tw;},0);
    if(total<=0)return;
    var sorted=DATA.slice().sort(function(a,b){return b.tw-a.tw;});
    var maxPct=sorted[0].tw/total*100;
    var groups={};
    var html='';
    sorted.forEach(function(s){
      var pct=s.tw/total*100,fillPct=pct/maxPct*100;
      var val=Math.round(s.tw/1000)+'k'+String.fromCharCode(8364);
      html+='<div class="sb-row" data-sec="'+s.name+'" tabindex="0">'
        +'<div class="sb-row-name"><span class="sb-row-dot" style="background:'+s.col+'"></span><span class="sb-row-label">'+s.name+'</span></div>'
        +'<div class="sb-row-bar"><div class="sb-row-fill" style="width:'+fillPct.toFixed(1)+'%;background:'+s.col+'"></div></div>'
        +'<div class="sb-row-pct">'+pct.toFixed(1)+'%</div>'
        +'<div class="sb-row-val">'+val+'</div>'
        +'</div>';
    });
    BARS.innerHTML=html;
    BARS.querySelectorAll('.sb-row').forEach(function(r){
      groups[r.dataset.sec]=r;
      r.addEventListener('click',function(){showSector(r.dataset.sec);});
      r.addEventListener('keydown',function(e){if(e.key==='Enter')showSector(r.dataset.sec);});
    });
    var n=sorted.length;
    function pv(p){return p==null?'&mdash;':((p>=0?'+':'')+p+'%');}
    function rw(l,v,c){return '<div style="display:flex;justify-content:space-between;padding:var(--s15) 0;border-bottom:.5px solid var(--line)"><span style="color:var(--steel)">'+l+'</span><span class="mono" style="color:'+(c||'var(--ink)')+'">'+v+'</span></div>';}
    function overview(){
      for(var k in groups){groups[k].classList.remove('on');groups[k].classList.remove('dim');}
      var top=sorted[0],tp=Math.round(top.tw/total*100),ov=tp>=30;
      PANEL.innerHTML='<div style="font-family:var(--fb);font-size:14px;letter-spacing:.1em;text-transform:uppercase;color:var(--steel);margin-bottom:var(--s25)">Overview</div>'
        +rw('Plus gros sector',top.name+' &middot; '+tp+'%',ov?'var(--bear)':'var(--acc)')
        +rw('Total positions',DATA.reduce(function(a,s){return a+s.t.length;},0)+'')
        +'<div style="margin-top:var(--s3);font-size:15px;color:'+(ov?'var(--warn)':'var(--steel)')+'">'+(ov?('&#9888; '+top.name+' au-dessus du cap 30%'):'sous le cap 30%')+'</div>'
        +'<div style="margin-top:var(--s35);font-size:14px;color:var(--steel)">click a sector to see its positions</div>';
    }
    function showSector(name){
      var s=null;DATA.forEach(function(d){if(d.name===name)s=d;});if(!s)return;
      for(var k in groups){if(k===name){groups[k].classList.add('on');groups[k].classList.remove('dim');}else{groups[k].classList.remove('on');groups[k].classList.add('dim');}}
      var rows=s.t.slice().sort(function(a,b){return b.w-a.w;}).map(function(x){var pc=x.pnl==null?'var(--steel)':(x.pnl>=0?'var(--acc)':'var(--bear)');return '<div class="sbrow" data-tk="'+x.tk+'"><span class="mono">'+x.tk+'</span><span style="display:flex;gap:var(--s3);align-items:center"><span class="mono" style="width:48px;text-align:right;color:'+pc+'">'+pv(x.pnl)+'</span><span class="mono" style="color:var(--steel);font-size:14px">stop '+(x.down==null?'&mdash;':x.down+'%')+'</span></span></div>';}).join('');
      PANEL.innerHTML='<div class="sb-back" style="cursor:pointer;color:var(--steel);font-size:14px;margin-bottom:var(--s2)">&larr; overview</div><div style="display:flex;align-items:center;gap:var(--s2);margin-bottom:var(--s25)"><span style="width:10px;height:10px;border-radius:2px;background:'+s.col+'"></span><span style="font-family:var(--fd);font-weight:500;font-size:16px">'+s.name+'</span><span class="mono" style="color:var(--steel);font-size:15px">'+Math.round(s.tw/total*100)+'% &middot; '+s.t.length+' lignes</span></div>'+rows+'<div style="margin-top:var(--s25);font-size:14px;color:var(--steel)">clique un titre pour sa fiche</div>';
    }
    PANEL.addEventListener('click',function(e){if(e.target.closest&&e.target.closest('.sb-back'))overview();});
    overview();
  })();
  /* Loupe : ouverture directe. Tous les essais d'animation/morph causent un bug
     visuel "interface saute" (View Transition + scale-in + variantes essayees
     02/06 soir). Modal apparait instant. Polish a re-tenter plus tard avec
     approche differente (peut-etre Web Animations API direct sur l'element). */
  document.addEventListener('click',function(ev){
    var r=ev.target.closest&&ev.target.closest('[data-tk]'); if(r&&r.dataset.tk){ openLoupe(r.dataset.tk); }
    if(ev.target.id==='loupe'){ closeLoupe(); }
  });
  document.addEventListener('keydown',function(ev){ if(ev.key==='Escape')closeLoupe(); });
  (function(){
    var box=document.createElement('div');box.id='qsearch';box.className='qs';
    box.setAttribute('role','dialog');box.setAttribute('aria-modal','true');box.setAttribute('aria-label','Quick search');box.setAttribute('aria-hidden','true');
    box.innerHTML='<div class="qs-card"><input id="qs-input" type="text" aria-label="Search ticker or name" placeholder="Search ticker or name..." autocomplete="off" inputmode="search" enterkeyhint="go"><div id="qs-res" role="listbox"></div></div>';
    document.body.appendChild(box);
    var inp=box.querySelector('#qs-input'),res=box.querySelector('#qs-res'),sel=0,cur=[];
    var rk={held:0,watch:1,core:2,extended:3,out:4};
    function lab(st){return {held:'held',watch:'watch',core:'core',extended:'extended'}[st]||'out-of-universe';}
    function openQS(){box.classList.add('open');box.setAttribute('aria-hidden','false');inp.value='';qrender('');setTimeout(function(){inp.focus();},30);}
    function closeQS(){box.classList.remove('open');box.setAttribute('aria-hidden','true');}
    function qrender(q){
      var TK=window.TK||{},ql=q.trim().toLowerCase(),out=[];
      for(var tk in TK){var d=TK[tk],nm=(d.name||'').toLowerCase();
        if(!ql||tk.toLowerCase().indexOf(ql)>=0||nm.indexOf(ql)>=0){out.push([tk,d]);}}
      out.sort(function(a,b){return (rk[a[1].status]||9)-(rk[b[1].status]||9);});
      cur=out.slice(0,8);sel=0;
      res.innerHTML=cur.length?cur.map(function(e,i){var d=e[1];
        return '<div class="qs-row'+(i===0?' on':'')+'" data-qtk="'+e[0]+'"><span class="qs-tk">'+e[0]+'</span><span class="qs-nm">'+(d.name||'')+'</span><span class="qs-st '+(d.status||'out')+'">'+lab(d.status||'out')+'</span></div>';
      }).join(''):'<div class="qs-empty">none titre</div>';
    }
    function pick(tk){if(!tk)return;closeQS();openLoupe(tk);}
    function hi(){var rows=res.querySelectorAll('.qs-row');for(var i=0;i<rows.length;i++){rows[i].classList.toggle('on',i===sel);}}
    inp.addEventListener('input',function(){qrender(inp.value);});
    res.addEventListener('click',function(e){var r=e.target.closest('.qs-row');if(r)pick(r.dataset.qtk);});
    box.addEventListener('click',function(e){if(e.target===box)closeQS();});
    document.addEventListener('keydown',function(e){
      if((e.metaKey||e.ctrlKey)&&(e.key==='k'||e.key==='K')){e.preventDefault();box.classList.contains('open')?closeQS():openQS();return;}
      if(!box.classList.contains('open'))return;
      if(e.key==='Escape'){closeQS();}
      else if(e.key==='ArrowDown'){e.preventDefault();sel=Math.min(cur.length-1,sel+1);hi();}
      else if(e.key==='ArrowUp'){e.preventDefault();sel=Math.max(0,sel-1);hi();}
      else if(e.key==='Enter'){e.preventDefault();if(cur[sel])pick(cur[sel][0]);}
    });
  })();
  (function(){
    try{var sy=sessionStorage.getItem('h_scroll');if(sy)window.scrollTo(0,parseFloat(sy)||0);}catch(e){}
    var lastAct=Date.now();
    ['mousemove','keydown','touchstart','wheel'].forEach(function(ev){document.addEventListener(ev,function(){lastAct=Date.now();},{passive:true});});
    setInterval(function(){
      var lp=document.getElementById('loupe');
      if(lp&&lp.classList.contains('open'))return;
      if(document.hidden)return;
      if(Date.now()-lastAct<6000)return;
      try{sessionStorage.setItem('h_scroll',String(window.scrollY||window.pageYOffset||0));}catch(e){}
      void 0;  /* auto-reload navigateur retire -- rafraichir avec Cmd+R */
    },75000);
  })();
