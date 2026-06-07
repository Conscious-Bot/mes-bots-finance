"""Dashboard JS/HTML constants -- extracted from render.py Phase 1b refactor (02/06).

Pure data, no behavior. Imported by render.py.
"""
from pathlib import Path

_LOGO = (Path(__file__).parent / "static" / "brand" / "presage_symbol.svg").read_text(encoding="utf-8")

# Set v2 (02/06) : ancien set GARDE pour Overview/Positions/Concentration/
# Alerts/Copilot/Method (user pref). SEULS Theses (crosshair) + Strategy (map)
# sont les nouveaux Lucide.
_NAV = (
    '<nav class="nav" role="navigation" aria-label="Main navigation">'
    '<div class="nitem on" data-nav="vigie"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a8 8 0 0 1 16 0"/><path d="M12 14l4.5-3.5"/><circle cx="12" cy="14" r="1.3" fill="currentColor" stroke="none"/></svg><span class="nlab">Overview</span></div>'
    '<div class="nitem" data-nav="positions"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4l8 4-8 4-8-4 8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/></svg><span class="nlab">Positions</span></div>'
    '<div class="nitem" data-nav="theses"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg><span class="nlab">Theses</span></div>'
    '<div class="nitem" data-nav="concentration"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 12V4"/><path d="M12 12l6.5 4"/></svg><span class="nlab">Concentration</span></div>'
    '<div class="nitem" data-nav="strategie"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="3.2" r="0.9"/><path d="M12 4.5 C 8.5 4.5, 7.5 9, 9.5 13 L 14.5 13 C 16.5 9, 15.5 4.5, 12 4.5 Z"/><path d="M10.5 7.5 L 13.5 9.5"/><line x1="9" y1="13" x2="15" y2="13"/><path d="M9.5 13 L 8.5 18 L 15.5 18 L 14.5 13"/><path d="M6 18 L 18 18 L 19.5 22 L 4.5 22 Z"/></svg><span class="nlab">Strategy</span></div>'
    '<div class="nitem" data-nav="urgence"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4l8.5 15H3.5L12 4z"/><path d="M12 10v4.5"/><circle cx="12" cy="17.5" r="0.7" fill="currentColor" stroke="none"/></svg><span class="nlab">Alerts</span></div>'
    '<div class="nitem" data-nav="copilot"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg><span class="nlab">Copilot</span></div>'
    # Position-card #1 nav. Deep-link via #card-TICKER. Click ticker dans
    # /positions ou /theses navigue ici (a wire couche 4).
    '<div class="nitem" data-nav="position-card"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="2"/><line x1="3.5" y1="9.5" x2="20.5" y2="9.5"/><line x1="7" y1="13" x2="17" y2="13"/><line x1="7" y1="16" x2="13" y2="16"/></svg><span class="nlab">Cards</span></div>'
    '</nav>'
)

_CTA_JS = """
(function(){
  /* Cmd+K v2 (02/06 #90) : score-based ranking + subseq fuzzy + highlighting.
     - Score : exact (1000) > ticker prefix (700) > name prefix (500) > ticker
       substring (400) > name word-prefix (350) > name substring (200) >
       subseq fuzzy ticker (100) > subseq fuzzy name (50). Recent +50.
       Length penalty -(tk.length - q.length) sur substring matches.
     - Subseq match : chars de q apparaissent en ordre dans cible (style
       VS Code Cmd+P / Linear / Sublime). "trsl" matche "TESLA".
     - Highlighting : chars matches en bold + couleur accent --data.
     - Latency : 311 tickers x score = ~3ms typique, sous le budget 16ms. */
  var modal=document.getElementById('ctaSearchModal');
  var input=document.getElementById('ctaSearchInput');
  var results=document.getElementById('ctaSearchResults');
  var btnSearch=document.getElementById('ctaSearch');
  var tkData=window.TK||{};
  var allTk=Object.keys(window._TKDOMAIN||{});
  var dataKeys=Object.keys(tkData);
  var uniq={}; allTk.concat(dataKeys).forEach(function(t){uniq[t]=1;});
  var allTickers=Object.keys(uniq).sort();
  var selIdx=0;
  var activeSector=null;
  function esc(s){
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function getRecent(){
    try { return JSON.parse(localStorage.getItem('presage_recent_tk')||'[]'); } catch(e){ return []; }
  }
  function pushRecent(tk){
    try {
      var r=getRecent().filter(function(x){return x!==tk;});
      r.unshift(tk);
      localStorage.setItem('presage_recent_tk', JSON.stringify(r.slice(0,5)));
    } catch(e){}
  }
  function isSubseq(q, s){
    var i=0;
    for (var j=0; j<s.length && i<q.length; j++){
      if (s.charCodeAt(j) === q.charCodeAt(i)) i++;
    }
    return i === q.length;
  }
  /* Score function : retourne -1 si pas de match, sinon score positif.
     Plus haut = meilleur. */
  function score(ql, ticker, name, isRecent){
    if (!ql) return isRecent ? 100 : 0;
    var tk = ticker.toLowerCase();
    var nm = (name||'').toLowerCase();
    var s = -1;
    if (tk === ql) s = 1000;
    else if (tk.indexOf(ql) === 0) s = 700;
    else if (nm.indexOf(ql) === 0) s = 500;
    else if (tk.indexOf(ql) > 0) s = 400;
    else {
      var words = nm.split(/\\s+/);
      var wp = false;
      for (var w=0; w<words.length; w++){ if (words[w].indexOf(ql) === 0){ wp=true; break; } }
      if (wp) s = 350;
      else if (nm.indexOf(ql) >= 0) s = 200;
      else if (isSubseq(ql, tk)) s = 100;
      else if (isSubseq(ql, nm)) s = 50;
    }
    if (s < 0) return -1;
    if (isRecent) s += 50;
    /* Length penalty : matches substring d'un ticker court > long. */
    if (s >= 200 && s < 1000) s -= Math.max(0, tk.length - ql.length);
    return s;
  }
  /* Highlight contiguous substring match bold ; sinon highlight subseq chars. */
  function highlight(text, ql){
    if (!ql || !text) return esc(text);
    var tL = text.toLowerCase();
    var idx = tL.indexOf(ql);
    if (idx >= 0) {
      return esc(text.slice(0,idx)) + '<b>' + esc(text.slice(idx, idx+ql.length)) + '</b>' + esc(text.slice(idx+ql.length));
    }
    var i = 0, out = '';
    for (var j=0; j<text.length; j++){
      var ch = text.charAt(j);
      if (i < ql.length && tL.charCodeAt(j) === ql.charCodeAt(i)) { out += '<b>' + esc(ch) + '</b>'; i++; }
      else out += esc(ch);
    }
    return out;
  }
  var sectors={};
  Object.keys(tkData).forEach(function(tk){
    var s=(tkData[tk]||{}).sector;
    if(s && s!=='Sans these') sectors[s]=(sectors[s]||0)+1;
  });
  var sectorList=Object.keys(sectors).sort(function(a,b){return sectors[b]-sectors[a];}).slice(0,8);
  function makeLogo(tk){
    if(typeof _tkLogoJs==='function') return _tkLogoJs(tk);
    return '<span class="tklogo tkfb">'+esc(String(tk||'?').charAt(0).toUpperCase())+'</span>';
  }
  function renderChips(){
    var chips=document.getElementById('ctaSearchChips');
    if(!chips) return;
    var html='<button class="cta-chip'+(activeSector===null?' act':'')+'" data-sec="">All</button>';
    sectorList.forEach(function(s){
      html+='<button class="cta-chip'+(activeSector===s?' act':'')+'" data-sec="'+esc(s)+'">'+esc(s)+' <span class="cta-chip-n">'+sectors[s]+'</span></button>';
    });
    chips.innerHTML=html;
    Array.from(chips.querySelectorAll('.cta-chip')).forEach(function(el){
      el.addEventListener('click',function(){
        activeSector=el.getAttribute('data-sec')||null;
        renderChips();
        render(input.value);
      });
    });
  }
  function render(q){
    var ql=(q||'').toLowerCase().trim();
    var recent=getRecent();
    var recentSet={}; recent.forEach(function(tk){recentSet[tk]=1;});
    var matches;
    if (!ql && !activeSector){
      var recentValid = recent.filter(function(tk){return allTickers.indexOf(tk)>=0;});
      var rest = allTickers.filter(function(tk){return recentValid.indexOf(tk)<0;}).slice(0, 25 - recentValid.length);
      matches = recentValid.concat(rest);
    } else {
      var scored = [];
      for (var i = 0; i < allTickers.length; i++) {
        var tk = allTickers[i];
        var d = tkData[tk] || {};
        if (activeSector && d.sector !== activeSector) continue;
        var sc = score(ql, tk, d.name || '', !!recentSet[tk]);
        if (sc >= 0) scored.push({tk: tk, sc: sc});
      }
      scored.sort(function(a, b){
        if (b.sc !== a.sc) return b.sc - a.sc;
        return a.tk.localeCompare(b.tk);
      });
      matches = scored.slice(0, 40).map(function(x){return x.tk;});
    }
    selIdx=0;
    if(!matches.length){ results.innerHTML='<div class="cta-result" style="opacity:.5">No match</div>'; return; }
    results.innerHTML=matches.map(function(tk,i){
      var d = tkData[tk] || {};
      var nm = d.name || '';
      var tkHtml = highlight(tk, ql);
      var nmHtml = highlight(nm, ql);
      var tag = recentSet[tk] ? '<span class="cta-tag">recent</span>' : '';
      return '<div class="cta-result '+(i===0?'sel':'')+'" data-tk="'+esc(tk)+'">'+makeLogo(tk)+'<span class="ctk">'+tkHtml+'</span><span class="cnm">'+nmHtml+'</span>'+tag+'</div>';
    }).join('');
  }
  function open(){
    modal.classList.add('open');
    input.value='';
    activeSector=null;
    renderChips();
    render('');
    setTimeout(function(){input.focus();},50);
  }
  function close(){ modal.classList.remove('open'); }
  function chooseSel(){
    var els=results.querySelectorAll('.cta-result[data-tk]');
    if(els[selIdx]){
      var tk=els[selIdx].getAttribute('data-tk');
      pushRecent(tk);
      close();
      if(typeof openLoupe==='function') openLoupe(tk);
    }
  }
  if(btnSearch) btnSearch.addEventListener('click',open);
  if(input){
    input.addEventListener('input',function(e){render(e.target.value);});
    input.addEventListener('keydown',function(e){
      if(e.key==='Escape'){ e.preventDefault(); close(); return; }
      if(e.key==='Enter'){ e.preventDefault(); chooseSel(); return; }
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){
        e.preventDefault();
        var els=results.querySelectorAll('.cta-result[data-tk]');
        if(!els.length) return;
        selIdx=(selIdx+(e.key==='ArrowDown'?1:-1)+els.length)%els.length;
        els.forEach(function(el,i){el.classList.toggle('sel',i===selIdx);});
        els[selIdx].scrollIntoView({block:'nearest'});
      }
    });
  }
  if(modal) modal.addEventListener('click',function(e){
    if(e.target===modal){ close(); return; }
    var r=e.target.closest('.cta-result[data-tk]');
    if(r){ var tk=r.getAttribute('data-tk'); pushRecent(tk); close(); if(typeof openLoupe==='function') openLoupe(tk); }
  });
  document.addEventListener('keydown',function(e){
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){ e.preventDefault(); open(); }
  });
})();
"""

_APP_JS = """
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
          else if(act==='tv'){ window.open('https://www.tradingview.com/symbols/'+encodeURIComponent(tk.replace(/\\./g,'-')), '_blank'); }
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
  window._TKDOMAIN = __TKDOMAIN_JSON__;
  window._TKLOCAL = __TKLOCAL_JSON__;
  function _tkLogoJs(tk){
    var init=String(tk||'?').charAt(0).toUpperCase();
    var fb="this.outerHTML='<span class=&quot;tklogo tkfb&quot;>"+init+"</span>'";
    // Priorite 1 : fichier local self-host (offline, sans appel externe)
    var localFile=(window._TKLOCAL||{})[tk]||(window._TKLOCAL||{})[String(tk).toUpperCase()];
    if(localFile){
      return '<img class="tklogo" src="/static/brand/logos/'+localFile+'" alt="" onerror="'+fb+'">';
    }
    var dom=(window._TKDOMAIN||{})[tk]||(window._TKDOMAIN||{})[String(tk).toUpperCase()];
    if(!dom) return '<span class="tklogo tkfb">'+init+'</span>';
    var ddg='https://icons.duckduckgo.com/ip3/'+dom+'.ico';
    var fb2="this.onerror=function(){"+fb+"};this.src='"+ddg+"'";
    return '<img class="tklogo" src="https://www.google.com/s2/favicons?domain='+dom+'&amp;sz=64" alt="" onerror="'+fb2+'">';
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
    document.getElementById('loupe').classList.add('open');
  }
  function closeLoupe(){ var el=document.getElementById('loupe'); if(el)el.classList.remove('open'); }
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
    box.innerHTML='<div class="qs-card"><input id="qs-input" type="text" aria-label="Search ticker or name" placeholder="Search ticker or name..." autocomplete="off"><div id="qs-res"></div></div>';
    document.body.appendChild(box);
    var inp=box.querySelector('#qs-input'),res=box.querySelector('#qs-res'),sel=0,cur=[];
    var rk={held:0,watch:1,core:2,extended:3,out:4};
    function lab(st){return {held:'held',watch:'watch',core:'core',extended:'extended'}[st]||'out-of-universe';}
    function openQS(){box.classList.add('open');inp.value='';qrender('');setTimeout(function(){inp.focus();},30);}
    function closeQS(){box.classList.remove('open');}
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
"""

_LOUPE_HTML = (
    '<div id="loupe" class="loupe"><div class="loupe-card">'
    '<button class="loupe-x" onclick="closeLoupe()" aria-label="Fermer">&times;</button>'
    '<div id="loupe-body"></div></div></div>'
)

_EU_SUFFIX = (
    ".PA",
    ".AS",
    ".DE",
    ".MI",
    ".ST",
    ".BR",
    ".MC",
    ".SW",
    ".VI",
    ".HE",
    ".CO",
    ".OL",
    ".LS",
    ".L",
    ".F",
    ".PL",
    ".WA",
    ".AT",
)

_MODE_BTN = """<button class="modetgl" title="Day / night mode" aria-label="Toggle day / night mode" onclick="document.body.classList.toggle('midnight');try{localStorage.setItem('hmdl-theme',document.body.classList.contains('midnight')?'midnight':'parchment')}catch(e){}"><svg class="ico-sun" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg><svg class="ico-moon" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>"""

# Method nitem sorti du nav principal (02/06 user) -- vit dans le foot
# au-dessus du switch de mode, comme une seconde tier "outillage / methode".
# Garde data-nav="methode" pour rester pilote par la meme JS handler.
_FOOT_METHOD = (
    '<div class="nitem" data-nav="methode" title="Method (signals + loop + biases + insider flow)">'
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="13" r="1.6" fill="currentColor" stroke="none"/>'
    '<path d="M8.6 9.6a5 5 0 0 0 0 6.8"/><path d="M15.4 9.6a5 5 0 0 1 0 6.8"/>'
    '<path d="M6 7a8.5 8.5 0 0 0 0 12"/><path d="M18 7a8.5 8.5 0 0 1 0 12"/>'
    '</svg><span class="nlab">Method</span></div>'
)

_THEME_INIT = (
    "<script>"
    "try{"
    "var t=localStorage.getItem('hmdl-theme');"
    # Anti-FOUC : ce script s'injecte AVANT </head> et AVANT body parse.
    # 1. Pre-paint le bg sur <html> immediatement (evite flash blanc)
    # 2. Schedule body class add via DOMContentLoaded pour le reste des styles
    "if(t==='midnight'){"
    "document.documentElement.style.background='#0F1115';"
    "document.addEventListener('DOMContentLoaded',function(){document.body.classList.add('midnight');});"
    "}"
    "}catch(e){}"
    "</script>"
)

_SORT_JS = """<script>document.addEventListener('DOMContentLoaded',function(){
document.querySelectorAll('table.dt').forEach(function(t){
  var tb=t.tBodies[0]; if(!tb) return;
  var dir={};
  t.querySelectorAll('thead th').forEach(function(th,ci){
    var key={0:'tk',1:'v',2:'w',3:'p'}[ci]; if(!key) return;
    th.style.cursor='pointer';
    th.addEventListener('click',function(){
      var num=key!=='tk', d=dir[ci]=-(dir[ci]||1);
      var rows=[].slice.call(tb.rows).filter(function(r){return r.hasAttribute('data-'+key);});
      rows.sort(function(a,b){
        var x=a.getAttribute('data-'+key), y=b.getAttribute('data-'+key);
        if(num){return (parseFloat(x)-parseFloat(y))*d;}
        return x<y?-d:(x>y?d:0);
      });
      rows.forEach(function(r){tb.appendChild(r);});
      t.querySelectorAll('thead th').forEach(function(h){h.removeAttribute('aria-sort');});
      th.setAttribute('aria-sort',d<0?'descending':'ascending');
    });
  });
});
});</script>"""

_DONUT_JS = ""  # legacy slot — tooltips no longer needed (info inline in .brk-row)

_CSORT_JS = """<script>document.addEventListener('DOMContentLoaded',function(){
document.querySelectorAll('.sec-cols').forEach(function(hdr){
  var root=hdr.parentElement, map={1:'w',2:'w',3:'pct',4:'dv',5:'pl'}, dir={};
  hdr.querySelectorAll('span').forEach(function(sp,ci){
    var key=map[ci]; if(!key) return;
    sp.style.cursor='pointer';
    sp.addEventListener('click',function(){
      var d=dir[ci]=-(dir[ci]||1);
      root.querySelectorAll('.sec-rows').forEach(function(box){
        var rows=[].slice.call(box.children).filter(function(r){return r.classList.contains('sec-row');});
        rows.sort(function(a,b){return (parseFloat(a.getAttribute('data-'+key))-parseFloat(b.getAttribute('data-'+key)))*d;});
        rows.forEach(function(r){box.appendChild(r);});
      });
    });
  });
});
/* Accordion sec-grp : click sec-h toggles .open (collapsed par defaut). */
document.querySelectorAll('.sec-grp .sec-h').forEach(function(h){
  h.addEventListener('click',function(){h.parentElement.classList.toggle('open');});
});
});</script>"""
