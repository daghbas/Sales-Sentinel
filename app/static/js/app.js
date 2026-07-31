(() => {
  const chart = document.querySelector('.chart[data-sales]');
  if (!chart) return;
  const sales = JSON.parse(chart.dataset.sales || '[]');
  const forecasts = JSON.parse(chart.dataset.forecasts || '[]');
  const combined = [
    ...sales.map(item => ({ date: item.date, value: Number(item.value || 0), kind: 'actual' })),
    ...forecasts.map(item => ({ date: item.date, value: Number(item.median || 0), kind: 'forecast' }))
  ];
  const max = Math.max(...combined.map(item => item.value), 1);
  chart.innerHTML = combined.map(item => {
    const height = Math.max(3, item.value / max * 100);
    return `<div class="chart-bar ${item.kind === 'forecast' ? 'forecast' : ''}" style="height:${height}%" title="${item.date}: ${item.value.toLocaleString()}"></div>`;
  }).join('');
})();
