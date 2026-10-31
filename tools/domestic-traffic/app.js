/* Strategic Bearing – DGCA domestic traffic page. Data: data/dgca_domestic.json (built by pipeline/fetch_parse.py) */
(function () {
  'use strict';
  var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  var C = { navy:'#0B3A77', blue:'#0F5FC0', mute:'#53688A', line:'#DCE7F5', body:'#2C4166', red:'#C02828', green:'#0F6E5C' };
  var GROUPS = [
    ['IndiGo', '#1E63C4'], ['Air India Group', '#C02828'], ['Akasa Air', '#E8820C'], ['SpiceJet', '#7A1F5C'],
    ['Go First', '#0C7468'], ['Alliance Air', '#7C8DA6'], ['Others', '#B7C4D6']
  ];
  var FONT = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif";
  function lab(p) { var a = p.split('-'); return MON[+a[1] - 1] + ' ' + a[0]; }
  function full(p) { var a = p.split('-'); return FULL[+a[1] - 1] + ' ' + a[0]; }
  function f1(x) { return x == null ? '–' : x.toFixed(1); }
  function f2(x) { return x == null ? '–' : x.toFixed(2); }
  function sg(x, d) { return x == null ? '–' : (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(d == null ? 1 : d) + '%'; }
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]; }); }
  var narrow = function () { return window.innerWidth < 560; };
  var charts = [];

  fetch('data/dgca_domestic.json', { cache: 'no-cache' }).then(function (r) { return r.json(); }).then(render)
    .catch(function (e) { document.querySelectorAll('.chart').forEach(function (el) { el.innerHTML = '<p class="noscript">Could not load data (' + esc(e.message) + ').</p>'; }); });

  function render(D) {
    var nat = D.national, periods = nat.map(function (r) { return r.p; });
    var last = nat[nat.length - 1], asof = D.as_of_label;
    document.querySelectorAll('.asof').forEach(function (el) { el.textContent = asof; });
    var lastUrl = D.reports[D.as_of];
    document.querySelectorAll('.lastrep').forEach(function (a) { a.href = lastUrl; a.textContent = lab(D.as_of) + ' report, PDF'; });

    /* ---------- KPIs ---------- */
    var y = last.p.slice(0, 4), m = +last.p.slice(5, 7);
    var ytd = 0, ytdPrev = 0;
    nat.forEach(function (r) { var ry = r.p.slice(0, 4), rm = +r.p.slice(5, 7); if (rm <= m) { if (ry === y) ytd += r.pax; if (+ry === +y - 1) ytdPrev += r.pax; } });
    var ytdG = ytdPrev ? (ytd / ytdPrev - 1) * 100 : null;
    if (D.ytd && D.ytd.scope === 'ytd' && D.ytd.pax) { ytd = D.ytd.pax; ytdG = D.ytd.growth; } // prefer DGCA's own headline YTD
    var shareLast = D.share.filter(function (r) { return r.p === D.as_of; }).sort(function (a, b) { return b.s - a.s; });
    var lead = shareLast[0];
    $('kpis').innerHTML =
      kpi('lead', 'Passengers, ' + lab(last.p), f2(last.pax) + ' lakh', '<span class="' + (last.yoy < 0 ? 'neg' : '') + '">' + sg(last.yoy, 2) + '</span> vs ' + lab((+y - 1) + last.p.slice(4))) +
      kpi('', 'Jan–' + MON[m - 1] + ' ' + y, f2(ytd) + ' lakh', '<span class="' + (ytdG < 0 ? 'neg' : 'pos') + '">' + sg(ytdG, 2) + '</span> vs same months of ' + (+y - 1)) +
      kpi('', 'Largest airline, ' + lab(last.p), esc(lead.g) + ' ' + f1(lead.s) + '%', 'share of passengers carried') +
      kpi('', 'Months covered', String(nat.length), lab(periods[0]) + ' – ' + lab(last.p));
    function kpi(cls, k, v, sm) { return '<div class="kpi ' + cls + '"><span class="k">' + k + '</span><span class="v">' + v + '</span><span class="sm">' + sm + '</span></div>'; }

    /* ---------- takeaways (computed from the data) ---------- */
    var streak = 0; for (var i = nat.length - 1; i >= 0 && nat[i].yoy < 0; i--) streak++;
    var minR = nat.reduce(function (a, b) { return b.pax < a.pax ? b : a; });
    var maxR = nat.reduce(function (a, b) { return b.pax > a.pax ? b : a; });
    var ord = ['', '', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth'];
    var t1 = '<b>' + full(last.p) + ': ' + f2(last.pax) + ' lakh passengers, ' + sg(last.yoy, 2) + ' year on year</b>';
    if (streak >= 2) t1 += ', the ' + (ord[streak] || streak + 'th') + ' straight month below the previous year';
    if (minR.p === last.p) t1 += ', and the lowest month since this series began in ' + lab(periods[0]);
    t1 += '. The busiest month was ' + lab(maxR.p) + ' (' + f2(maxR.pax) + ' lakh).';
    $('t1').innerHTML = t1;

    var first = D.share.filter(function (r) { return r.p === periods[0]; });
    function gs(rows, g) { var r = rows.filter(function (x) { return x.g === g; })[0]; return r ? r.s : null; }
    var t2 = '<b>IndiGo carried ' + f1(gs(shareLast, 'IndiGo')) + '% of domestic passengers in ' + lab(last.p) + '</b>, up from ' + f1(gs(first, 'IndiGo')) + '% in ' + lab(periods[0]) +
      '. Air India Group holds ' + f1(gs(shareLast, 'Air India Group')) + '%. SpiceJet fell from ' + f1(gs(first, 'SpiceJet')) + '% to ' + f1(gs(shareLast, 'SpiceJet')) + '%';
    var gf = gs(first, 'Go First'); if (gf) t2 += ', and Go First (' + f1(gf) + '% in ' + lab(periods[0]) + ') exited in May 2023';
    $('t2').innerHTML = t2 + '.';

    var plfLast = D.plf.filter(function (r) { return r.p === D.as_of; });
    var big = {}; D.share_raw.filter(function (r) { return r.p === D.as_of && r.s >= 1; }).forEach(function (r) { big[r.a] = 1; });
    var plfBig = plfLast.filter(function (r) { return big[r.a]; }).sort(function (a, b) { return b.v - a.v; });
    if (plfBig.length) {
      var top = plfBig[0], others = plfBig.slice(1).map(function (r) { return esc(r.a) + ' ' + f1(r.v) + '%'; });
      $('t3').innerHTML = '<b>' + esc(top.a) + ' flew the fullest planes among the larger airlines in ' + lab(last.p) + ': ' + f1(top.v) + '% of seats filled</b>, against ' + others.join(', ') + '.';
    }

    /* ---------- chart 1: passengers + YoY ---------- */
    var c1 = echarts.init($('c1'), null, { renderer: 'svg' });
    charts.push([c1, function () { return opt1(); }]);
    function opt1() {
      var n = narrow();
      return {
        aria: { enabled: false }, textStyle: { fontFamily: FONT, color: C.body },
        animation: false,
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow', link: [{ xAxisIndex: 'all' }] }, confine: true,
          formatter: function (ps) { var r = nat[ps[0].dataIndex];
            return '<b>' + full(r.p) + '</b><br>Passengers: <b>' + f2(r.pax) + ' lakh</b><br>YoY: <b>' + sg(r.yoy, 2) + '</b>' +
              (r.basis === 'dgca_reported' ? ' <span style="color:#53688A">(as published by DGCA)</span>' : (r.yoy_dgca != null ? '<br><span style="color:#53688A">DGCA "monthly growth": ' + sg(r.yoy_dgca, 2) + '</span>' : '')); } },
        axisPointer: { link: [{ xAxisIndex: 'all' }] },
        grid: [{ left: n ? 40 : 52, right: n ? 8 : 18, top: 30, height: '52%' }, { left: n ? 40 : 52, right: n ? 8 : 18, top: '70%', bottom: n ? 40 : 34 }],
        xAxis: [0, 1].map(function (k) { return { type: 'category', gridIndex: k, data: periods, axisTick: { show: false },
          axisLine: { lineStyle: { color: C.line } },
          axisLabel: { show: k === 1, color: C.mute, fontSize: 11, interval: function (i, v) { return v.slice(5) === '01' || (!n && v.slice(5) === '07'); }, formatter: function (v) { return v.slice(5) === '01' ? v.slice(0, 4) : MON[+v.slice(5) - 1]; } } }; }),
        yAxis: [
          { gridIndex: 0, name: 'Passengers (lakh)', nameTextStyle: { color: C.mute, fontSize: 11, align: 'left', padding: [0, 0, 0, -30] }, min: 0, splitNumber: 4,
            axisLabel: { color: C.mute, fontSize: 11 }, splitLine: { lineStyle: { color: '#EEF3FA' } } },
          { gridIndex: 1, name: 'YoY %', nameTextStyle: { color: C.mute, fontSize: 11, align: 'left', padding: [0, 0, 0, -30] }, splitNumber: 3,
            axisLabel: { color: C.mute, fontSize: 11, formatter: '{value}%' }, splitLine: { lineStyle: { color: '#EEF3FA' } }, max: 30, interval: 10, min: function (v) { return Math.min(-10, Math.floor(v.min / 10) * 10); } }
        ],
        series: [
          { name: 'Passengers (lakh)', type: 'bar', data: nat.map(function (r) { return r.pax; }), barCategoryGap: '22%',
            itemStyle: { color: C.blue, borderRadius: [2, 2, 0, 0] }, emphasis: { itemStyle: { color: C.navy } } },
          { name: 'YoY change (%)', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barCategoryGap: '22%',
            data: nat.map(function (r) { return { value: r.yoy, itemStyle: { color: r.yoy < 0 ? C.red : (r.basis === 'dgca_reported' ? '#86B7A9' : C.green) } }; }),
            markLine: { silent: true, symbol: 'none', data: [{ yAxis: 0 }], lineStyle: { color: C.mute, type: 'solid', width: 1 }, label: { show: false } },
            label: { show: false } }
        ],
      };
    }
    var tb1 = '<thead><tr><th>Month</th><th>Passengers (lakh)</th><th>YoY</th><th>Basis</th></tr></thead><tbody>' +
      nat.slice().reverse().map(function (r) { return '<tr><td>' + lab(r.p) + '</td><td>' + f2(r.pax) + '</td><td>' + sg(r.yoy, 2) + '</td><td>' + (r.basis === 'computed' ? 'computed' : 'DGCA published') + '</td></tr>'; }).join('') + '</tbody>';
    $('tb1').innerHTML = '<caption class="sr">Monthly domestic passengers</caption>' + tb1;

    /* ---------- chart 2: market share ---------- */
    var ev = D.events || [];
    $('events').innerHTML = ev.map(function (e, i) { return '<li><span class="b" aria-hidden="true">' + (i + 1) + '</span><span><b>' + lab(e.p) + '</b> &middot; ' + esc(e.label) + ' <a href="' + esc(e.url) + '" target="_blank" rel="noopener" title="' + esc(e.detail) + '">DGCA ' + lab(e.src_report) + ' report</a></span></li>'; }).join('');
    var byP = {}; D.share.forEach(function (r) { (byP[r.p] = byP[r.p] || {})[r.g] = r; });
    var c2 = echarts.init($('c2'), null, { renderer: 'svg' });
    charts.push([c2, opt2]);
    function opt2() {
      var n = narrow();
      var series = GROUPS.map(function (g, gi) {
        var s = { name: g[0], type: 'line', stack: 'share', areaStyle: { opacity: 0.92 }, symbol: 'none', smooth: false,
          lineStyle: { width: 0.6, color: '#fff' }, itemStyle: { color: g[1] }, emphasis: { disabled: true },
          data: periods.map(function (p) { var r = byP[p] && byP[p][g[0]]; return r ? r.s : (g[0] === 'Go First' ? null : 0); }) };
        if (gi === 0) s.markLine = { silent: true, symbol: 'none', animation: false, label: { show: false },
          lineStyle: { color: C.navy, type: [3, 3], width: 1 }, data: ev.map(function (e) { return { xAxis: e.p }; }) };
        return s;
      });
      var span = n ? 3 : 1, stagPrev = false;
      series.push({ name: 'events', type: 'scatter', clip: false, silent: true, symbol: 'circle', symbolSize: 17, z: 10,
        itemStyle: { color: C.navy, borderColor: '#fff', borderWidth: 1, opacity: 1 }, tooltip: { show: false },
        label: { show: true, position: 'inside', color: '#fff', fontSize: 10.5, fontWeight: 700, formatter: function (p) { return p.data[2]; } },
        data: ev.map(function (e, i) { var gap = i ? periods.indexOf(e.p) - periods.indexOf(ev[i - 1].p) : 99;
          var st = gap <= span && !stagPrev; stagPrev = st; return [e.p, st ? 113 : 104, String(i + 1)]; }) });
      return {
        aria: { enabled: false }, textStyle: { fontFamily: FONT, color: C.body }, animation: false,
        legend: { top: 4, left: n ? 0 : 'center', itemWidth: 12, itemHeight: 10, itemGap: n ? 8 : 14, textStyle: { color: C.body, fontSize: n ? 11 : 12 }, data: GROUPS.map(function (g) { return g[0]; }) },
        tooltip: { trigger: 'axis', confine: true, order: 'seriesDesc',
          formatter: function (ps) { ps = ps.filter(function (x) { return x.seriesName !== 'events'; }); if (!ps.length) return ''; var p = periods[ps[0].dataIndex], rows = byP[p], h = '<b>' + full(p) + '</b>';
            GROUPS.forEach(function (g) { var r = rows[g[0]]; if (r) h += '<br><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + g[1] + ';margin-right:6px"></span>' + g[0] + ': <b>' + f1(r.s) + '%</b> <span style="color:#53688A">(' + f2(r.pax) + ' lakh)</span>'; });
            ev.forEach(function (e, i) { if (e.p === p) h += '<br><span style="color:#0B3A77">● ' + (i + 1) + ' ' + esc(e.label) + '</span>'; });
            return h; } },
        grid: { left: n ? 40 : 46, right: n ? 10 : 18, top: n ? 96 : 86, bottom: 30 },
        xAxis: { type: 'category', data: periods, boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: C.line } },
          axisLabel: { color: C.mute, fontSize: 11, interval: function (i, v) { return v.slice(5) === '01' || (!n && v.slice(5) === '07'); }, formatter: function (v) { return v.slice(5) === '01' ? v.slice(0, 4) : MON[+v.slice(5) - 1]; } } },
        yAxis: { type: 'value', min: 0, max: 100, interval: 25, axisLabel: { color: C.mute, fontSize: 11, formatter: '{value}%' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,.5)' } } },
        series: series
      };
    }
    var tb2 = '<thead><tr><th>Month</th>' + GROUPS.map(function (g) { return '<th>' + g[0] + '</th>'; }).join('') + '</tr></thead><tbody>' +
      periods.slice().reverse().map(function (p) { return '<tr><td>' + lab(p) + '</td>' + GROUPS.map(function (g) { var r = byP[p][g[0]]; return '<td>' + (r ? f1(r.s) + '%' : '–') + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody>';
    $('tb2').innerHTML = '<caption class="sr">Market share by airline group, % of passengers</caption>' + tb2;

    /* ---------- chart 3: PLF heatmap ---------- */
    var ROWNAME = function (a) { return a === 'Air India Group' ? 'Air India' : a; };
    var lastShare = {}; D.share_raw.forEach(function (r) { var k = ROWNAME(r.a); lastShare[k] = Math.max(lastShare[k] || 0, r.p >= periods[periods.length - 12] ? r.s : 0); });
    var avgPax = {}; D.share_raw.forEach(function (r) { var k = ROWNAME(r.a); avgPax[k] = (avgPax[k] || 0) + r.pax; });
    var rows = Object.keys(avgPax).sort(function (a, b) { return avgPax[a] - avgPax[b]; });
    var cell = {}; D.plf.forEach(function (r) { cell[ROWNAME(r.a) + '|' + r.p] = r; });
    var hm = [];
    rows.forEach(function (a, yi) { periods.forEach(function (p, xi) { var r = cell[a + '|' + p]; if (r) hm.push([xi, yi, r.v, r.a]); }); });
    var c3 = echarts.init($('c3'), null, { renderer: 'svg' });
    charts.push([c3, opt3]);
    function opt3() {
      var n = narrow();
      return {
        aria: { enabled: false }, textStyle: { fontFamily: FONT, color: C.body }, animation: false,
        tooltip: { confine: true, formatter: function (p) { var d = p.data; return '<b>' + esc(d[3]) + '</b> · ' + full(periods[d[0]]) + '<br>Load factor: <b>' + f1(d[2]) + '%</b>'; } },
        grid: { left: n ? 82 : 128, right: n ? 6 : 18, top: 10, bottom: n ? 62 : 56 },
        xAxis: { type: 'category', data: periods, splitArea: { show: false }, axisTick: { show: false }, axisLine: { show: false },
          axisLabel: { color: C.mute, fontSize: 11, interval: function (i, v) { return v.slice(5) === '01' || (!n && v.slice(5) === '07'); }, formatter: function (v) { return v.slice(5) === '01' ? v.slice(0, 4) : MON[+v.slice(5) - 1]; } } },
        yAxis: { type: 'category', data: rows.map(function (a) { return a === 'Air India' ? (n ? 'Air India*' : 'Air India (Group)*') : (n && a.length > 11 ? a.replace(' (AirAsia India)', '') : a); }), axisTick: { show: false }, axisLine: { show: false },
          axisLabel: { color: C.body, fontSize: n ? 10.5 : 12, width: n ? 78 : 124, overflow: 'truncate' } },
        visualMap: { type: 'piecewise', orient: 'horizontal', left: 'center', bottom: 4, itemWidth: 14, itemHeight: 10, itemGap: n ? 4 : 8,
          textStyle: { color: C.body, fontSize: n ? 10 : 11 }, dimension: 2,
          pieces: [{ lt: 60, label: '<60%', color: '#F4D6C9' }, { gte: 60, lt: 70, label: '60–70', color: '#DCE7F5' }, { gte: 70, lt: 80, label: '70–80', color: '#9EC0EA' },
                   { gte: 80, lt: 85, label: '80–85', color: '#5B92D6' }, { gte: 85, lt: 90, label: '85–90', color: '#1E63C4' }, { gte: 90, label: '90%+', color: '#0B3A77' }] },
        series: [{ type: 'heatmap', data: hm, itemStyle: { borderColor: '#fff', borderWidth: n ? 0.5 : 1 }, emphasis: { itemStyle: { borderColor: '#15D1BB', borderWidth: 2 } } }]
      };
    }
    $('tb3').innerHTML = '<caption class="sr">Load factor, ' + lab(D.as_of) + '</caption><thead><tr><th>Airline</th><th>Load factor, ' + lab(D.as_of) + '</th><th>Same month a year earlier</th></tr></thead><tbody>' +
      plfLast.slice().sort(function (a, b) { return b.v - a.v; }).map(function (r) {
        var py = (+D.as_of.slice(0, 4) - 1) + D.as_of.slice(4), pr = cell[ROWNAME(r.a) + '|' + py];
        return '<tr><td>' + esc(r.a) + '</td><td>' + f1(r.v) + '%</td><td>' + (pr ? f1(pr.v) + '%' : '–') + '</td></tr>'; }).join('') + '</tbody>';


    /* ---------- 4. capacity against demand (derived) ---------- */
    var cap = D.capacity;
    if (cap && cap.national && cap.national.length) {
      var cp = cap.national.filter(function (r) { return r.pax_yoy != null && r.seat_yoy != null; });
      var cper = cp.map(function (r) { return r.p; });
      var lastc = cp[cp.length - 1];

      /* Both series can go either way, and in this dataset they usually go up:
         23 of the 33 charted months grew. So the sentence is built from the
         signs rather than assuming a downturn. Saying "capacity is coming out"
         in a month when airlines added seats would be plainly wrong. */
      function gapLine(pax, seat) {
        var up = 'added', dn = 'taken out';
        if (pax >= 0 && seat >= 0) {
          return seat > pax
            ? 'Seats are being added faster than passengers are filling them.'
            : 'Seats are being added more slowly than demand is growing.';
        }
        if (pax < 0 && seat < 0) {
          return seat > pax
            ? 'Seats are coming out more slowly than demand is falling.'
            : 'Seats are coming out faster than demand is falling.';
        }
        return pax >= 0
          ? 'Demand grew while seats were ' + dn + ', which is why the aircraft are fuller.'
          : 'Seats were ' + up + ' into falling demand.';
      }

      $('t4').innerHTML = '<b>In ' + full(lastc.p) + ', passengers were ' + sg(lastc.pax_yoy, 2) +
        ' against a year earlier and implied seats ' + sg(lastc.seat_yoy, 2) + '</b>, so seat factor ' +
        (lastc.plf_chg < 0 ? 'fell ' : 'rose ') + Math.abs(lastc.plf_chg).toFixed(1) + ' points to ' +
        f1(lastc.plf) + '%. ' + gapLine(lastc.pax_yoy, lastc.seat_yoy);

      var c4 = echarts.init($('c4'), null, { renderer: 'svg' });
      charts.push([c4, opt4]);
      function opt4() {
        var n = narrow();
        return {
          aria: { enabled: false }, textStyle: { fontFamily: FONT, color: C.body }, animation: false,
          tooltip: {
            trigger: 'axis', confine: true,
            formatter: function (ps) {
              var r = cp[ps[0].dataIndex];
              return '<b>' + full(r.p) + '</b><br>Passengers: <b>' + sg(r.pax_yoy, 2) + '</b><br>' +
                'Implied seats: <b>' + sg(r.seat_yoy, 2) + '</b><br>Seat factor: <b>' + f1(r.plf) +
                '%</b> (' + (r.plf_chg > 0 ? '+' : '−') + Math.abs(r.plf_chg).toFixed(1) + 'pp)';
            }
          },
          legend: { data: ['Passengers', 'Implied seats'], top: 0, textStyle: { color: C.body, fontSize: n ? 11 : 12 } },
          grid: { left: n ? 42 : 56, right: n ? 10 : 20, top: 38, bottom: n ? 40 : 34 },
          xAxis: {
            type: 'category', data: cper, boundaryGap: false, axisTick: { show: false },
            axisLine: { lineStyle: { color: C.line } },
            axisLabel: {
              color: C.mute, fontSize: 11,
              interval: function (i, v) { return v.slice(5) === '01' || (!n && v.slice(5) === '07'); },
              formatter: function (v) { return v.slice(5) === '01' ? v.slice(0, 4) : MON[+v.slice(5) - 1]; }
            }
          },
          yAxis: {
            type: 'value', name: 'YoY %', nameTextStyle: { color: C.mute, fontSize: 11, align: 'left' },
            axisLabel: { color: C.mute, fontSize: 11, formatter: '{value}%' },
            splitLine: { lineStyle: { color: C.line } }
          },
          series: [
            { name: 'Passengers', type: 'line', symbol: 'none', smooth: false,
              data: cp.map(function (r) { return r.pax_yoy; }),
              lineStyle: { width: 2.4, color: C.blue }, itemStyle: { color: C.blue } },
            { name: 'Implied seats', type: 'line', symbol: 'none', smooth: false,
              data: cp.map(function (r) { return r.seat_yoy; }),
              lineStyle: { width: 2.4, color: '#8A5A10', type: 'dashed' }, itemStyle: { color: '#8A5A10' },
              markLine: { silent: true, symbol: 'none', data: [{ yAxis: 0 }],
                lineStyle: { color: C.mute, width: 1 }, label: { show: false } } }
          ]
        };
      }

      $('tb4').innerHTML = '<caption class="sr">Passengers and implied seats, year on year</caption>' +
        '<thead><tr><th>Month</th><th>Passengers, YoY</th><th>Implied seats, YoY</th>' +
        '<th>Seat factor</th><th>Seat factor change</th></tr></thead><tbody>' +
        cp.slice().reverse().map(function (r) {
          return '<tr><td>' + lab(r.p) + '</td><td>' + sg(r.pax_yoy, 2) + '</td><td>' + sg(r.seat_yoy, 2) +
            '</td><td>' + f1(r.plf) + '%</td><td>' + (r.plf_chg > 0 ? '+' : '−') +
            Math.abs(r.plf_chg).toFixed(1) + 'pp</td></tr>';
        }).join('') + '</tbody>';
    }


      /* the per-carrier block was being shipped and never shown; it answers
         the question the national lines raise but cannot: who actually took
         the seats out */
      if (cap && cap.carriers && cap.carriers.length) {
        var fromL = lab(cap.from), toL = lab(cap.to);
        $('tb4c').innerHTML = '<caption class="sr">Change by airline, ' + fromL +
          ' to ' + toL + '</caption><thead><tr><th>Airline</th><th>Passengers</th>' +
          '<th>Implied seats</th><th>Seat factor</th></tr></thead><tbody>' +
          cap.carriers.map(function (r) {
            return '<tr><td>' + esc(r.a) + '</td><td>' + sg(r.pax_pct, 1) + '</td><td>' +
              sg(r.seat_pct, 1) + '</td><td>' + (r.plf_chg > 0 ? '+' : '−') +
              Math.abs(r.plf_chg).toFixed(1) + 'pp</td></tr>';
          }).join('') + '</tbody>';
      }

    /* ---------- reports + checks ---------- */
    $('replist').innerHTML = Object.keys(D.reports).sort().reverse().map(function (k) { return '<li><a href="' + esc(D.reports[k]) + '" target="_blank" rel="noopener">' + full(k) + '</a></li>'; }).join('');
    var ck = D.checks || { n: 0, fails: [] };
    $('checks').innerHTML = '<li>' + ck.n + ' automated checks over ' + ck.months + ' months. In every month, the airline shares DGCA reports add up to 100% (±0.15 points), the airline totals match each report\'s headline figure, and computed YoY matches DGCA\'s "monthly growth" figure.</li>' +
      (ck.fails.length ? '<li>Where the traffic report and DGCA\'s ATR Form A statistics disagree, this page shows the traffic report\'s figure: ' + ck.fails.map(function (f) { return '<b>' + esc(f.t.replace(/^.*– /, '')) + ', ' + lab(f.p) + '</b> (' + esc(f.d.replace(/pdf=([\d.]+)L xlsx=([\d.]+)L diff=([+-][\d.]+)%/, 'traffic report $1 lakh, ATR Form A $2 lakh')) + ')'; }).join('; ') + '.</li>' : '<li>No disagreements with DGCA\'s ATR Form A statistics.</li>');

    charts.forEach(function (c) { c[0].setOption(c[1](), true); });
    var t; window.addEventListener('resize', function () { clearTimeout(t); t = setTimeout(function () { charts.forEach(function (c) { c[0].setOption(c[1](), true); c[0].resize(); }); }, 120); });
  }
})();
