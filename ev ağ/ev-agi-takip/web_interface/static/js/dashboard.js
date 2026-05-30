(function () {
  const canvas = document.getElementById("trafficChart");
  if (!canvas || typeof Chart === "undefined") return;

  const labels = window.CHART_LABELS || [];
  const values = window.CHART_VALUES || [];

  new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "GB",
          data: values,
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.12)",
          fill: true,
          tension: 0.2,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      animation: false,
      animations: {
        colors: false,
        x: false,
        y: false,
      },
      transitions: {
        active: { animation: { duration: 0 } },
        resize: { animation: { duration: 0 } },
      },
      plugins: {
        legend: { labels: { color: "#8b9cb3" } },
      },
      scales: {
        x: { ticks: { color: "#8b9cb3", maxRotation: 45 }, grid: { color: "#2d3a4f" } },
        y: { ticks: { color: "#8b9cb3" }, grid: { color: "#2d3a4f" }, beginAtZero: true },
      },
    },
  });
})();
