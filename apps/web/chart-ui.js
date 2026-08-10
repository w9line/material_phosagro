(() => {
  const modes = {bar:'Сравнить', line:'Динамика', donut:'Структура', scatter:'Точки', stacked:'По категориям'};
  const viewModes = {};
  const colors = ['#b76543', '#4f765f', '#3f6590', '#9c7a45', '#7b596b'];
  const escText = value => esc(value ?? '');
  const chartMode = chart => viewModes[chart.chart_id] || 'bar';
  const canStack = chart => chart.series?.length > 1 && chart.chart_type !== 'inventory';
  const chartModes = chart => Object.keys(modes).filter(mode => mode !== 'stacked' || canStack(chart));
  const chartValue = value => Number(value || 0).toLocaleString('ru-RU', {maximumFractionDigits: 1});
  const optionMarkup = (chart, selected) => chartModes(chart).map(mode => `<option value="${mode}"${mode === selected ? ' selected' : ''}>${modes[mode]}</option>`).join('');

  function chartSvgMarkup(chart, mode = chartMode(chart)) {
    const labels = chart.labels || [], series = chart.series || [];
    const width = 760, height = 340, left = 56, right = 24, top = 48, bottom = 52;
    const plotWidth = width - left - right, plotHeight = height - top - bottom;
    const values = series.flatMap(item => (item.values || []).map(value => Math.max(0, Number(value) || 0)));
    if (!labels.length || !series.length) return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}"><text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#74756e">Нет данных для графика</text></svg>`;
    const totals = labels.map((_, index) => series.reduce((sum, item) => sum + Math.max(0, Number(item.values?.[index]) || 0), 0));
    const max = Math.max(1, ...(mode === 'stacked' ? totals : values));
    const y = value => top + plotHeight - (Math.max(0, Number(value) || 0) / max) * plotHeight;
    const x = index => left + (labels.length === 1 ? plotWidth / 2 : index * plotWidth / (labels.length - 1));
    const labelMarkup = labels.map((label, index) => `<text x="${x(index).toFixed(1)}" y="${height - 17}" text-anchor="middle" font-size="11" fill="#74756e">${escText(label)}</text>`).join('');
    const gridMarkup = [0, .5, 1].map(step => `<line x1="${left}" y1="${y(max * step).toFixed(1)}" x2="${width - right}" y2="${y(max * step).toFixed(1)}" stroke="#c9c3b8" stroke-width="1"/><text x="${left - 9}" y="${(y(max * step) + 4).toFixed(1)}" text-anchor="end" font-size="10" fill="#74756e">${chartValue(max * step)}</text>`).join('');
    const legend = series.map((item, index) => `<g transform="translate(${left + index * 165},18)"><rect width="10" height="10" fill="${colors[index % colors.length]}"/><text x="16" y="10" font-size="11" fill="#343b35">${escText(item.name)}</text></g>`).join('');
    let marks = '';
    if (mode === 'line' || mode === 'scatter') {
      marks = series.map((item, seriesIndex) => {
        const points = (item.values || []).map((value, index) => `${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ');
        const dots = (item.values || []).map((value, index) => `<circle cx="${x(index).toFixed(1)}" cy="${y(value).toFixed(1)}" r="${mode === 'scatter' ? 5 : 3.5}" fill="${colors[seriesIndex % colors.length]}"/>`).join('');
        return `${mode === 'line' ? `<polyline points="${points}" fill="none" stroke="${colors[seriesIndex % colors.length]}" stroke-width="2.5"/>` : ''}${dots}`;
      }).join('');
    } else if (mode === 'stacked') {
      const group = plotWidth / labels.length, bar = Math.min(52, group * .62);
      marks = labels.map((_, index) => {
        let used = 0;
        return series.map((item, seriesIndex) => {
          const value = Math.max(0, Number(item.values?.[index]) || 0), next = used + value;
          const rect = `<rect x="${(left + index * group + (group - bar) / 2).toFixed(1)}" y="${y(next).toFixed(1)}" width="${bar.toFixed(1)}" height="${Math.max(0, y(used) - y(next)).toFixed(1)}" fill="${colors[seriesIndex % colors.length]}"/>`;
          used = next; return rect;
        }).join('');
      }).join('');
    } else if (mode === 'donut') {
      const donutValues = series.length === 1 ? series[0].values : series.map(item => (item.values || []).reduce((sum, value) => sum + Math.max(0, Number(value) || 0), 0));
      const donutLabels = series.length === 1 ? labels : series.map(item => item.name);
      const total = Math.max(1, donutValues.reduce((sum, value) => sum + Math.max(0, Number(value) || 0), 0));
      const radius = 88, circumference = 2 * Math.PI * radius, centerX = 245, centerY = 181;
      let offset = 0;
      marks = donutValues.map((value, index) => {
        const length = Math.max(0, Number(value) || 0) / total * circumference;
        const mark = `<circle cx="${centerX}" cy="${centerY}" r="${radius}" fill="none" stroke="${colors[index % colors.length]}" stroke-width="30" stroke-dasharray="${length.toFixed(2)} ${(circumference - length).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${centerX} ${centerY})"/>`;
        offset += length; return mark;
      }).join('') + `<circle cx="${centerX}" cy="${centerY}" r="55" fill="#f8f6f0"/><text x="${centerX}" y="${centerY - 2}" text-anchor="middle" font-size="22" font-weight="600" fill="#202520">${chartValue(total)}</text><text x="${centerX}" y="${centerY + 18}" text-anchor="middle" font-size="10" fill="#74756e">${escText(chart.unit || 'значение')}</text>`;
      const donutLegend = donutLabels.map((label, index) => `<g transform="translate(430,${76 + index * 30})"><rect width="10" height="10" fill="${colors[index % colors.length]}"/><text x="17" y="10" font-size="12" fill="#343b35">${escText(label)} · ${chartValue(donutValues[index])}</text></g>`).join('');
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escText(chart.title || 'График')}"><rect width="100%" height="100%" fill="#f8f6f0"/>${marks}${donutLegend}</svg>`;
    } else {
      const group = plotWidth / labels.length, bar = Math.min(42, group / Math.max(1, series.length + .8));
      marks = labels.map((_, labelIndex) => series.map((item, seriesIndex) => {
        const value = Math.max(0, Number(item.values?.[labelIndex]) || 0), barX = left + labelIndex * group + (group - series.length * bar) / 2 + seriesIndex * bar;
        return `<rect x="${barX.toFixed(1)}" y="${y(value).toFixed(1)}" width="${Math.max(4, bar - 3).toFixed(1)}" height="${Math.max(0, top + plotHeight - y(value)).toFixed(1)}" fill="${colors[seriesIndex % colors.length]}"/>`;
      }).join('')).join('');
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escText(chart.title || 'График')}"><rect width="100%" height="100%" fill="#f8f6f0"/>${gridMarkup}${legend}${marks}${labelMarkup}</svg>`;
  }

  function setChartView(index, mode) {
    const chart = chartFor(chatHistory[index]);
    if (!chart || !chartModes(chart).includes(mode)) return;
    viewModes[chart.chart_id] = mode;
    renderMessages();
  }

  function downloadChart(index) {
    const chart = chartFor(chatHistory[index]);
    if (!chart) return;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([chartSvgMarkup(chart)], {type:'image/svg+xml'}));
    link.download = `${chart.chart_type || 'chart'}-${Date.now()}.svg`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function chartCard(chart, index) {
    const selected = chartMode(chart);
    return `<div class="chat-chart chart-preview" data-chart-open="${index}" role="button" tabindex="0" aria-label="Открыть график ${escText(chart.title || 'График')}"><div class="chart-card-head"><strong>${escText(chart.title || 'График')}</strong><label class="chart-picker" onclick="event.stopPropagation()">Вид <select onchange="setChartView(${index}, this.value)">${optionMarkup(chart, selected)}</select></label><button type="button" class="link-button" data-chart-download="${index}">Скачать SVG ↗</button></div>${chartSvgMarkup(chart, selected)}</div>`;
  }

  function openChartModal(index) {
    const chart = chartFor(chatHistory[index]);
    if (!chart) return;
    activeChartIndex = index;
    const selected = chartMode(chart);
    $('chartModalTitle').textContent = chart.title || 'График';
    $('chartModalKind').innerHTML = optionMarkup(chart, selected);
    $('chartModalKind').onchange = event => { viewModes[chart.chart_id] = event.target.value; $('chartModalBody').innerHTML = chartSvgMarkup(chart, event.target.value); };
    $('chartModalBody').innerHTML = chartSvgMarkup(chart, selected);
    $('chartModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }

  window.chartSvgMarkup = chartSvgMarkup;
  window.chartCard = chartCard;
  window.setChartView = setChartView;
  window.downloadChart = downloadChart;
  window.openChartModal = openChartModal;
})();
