
  async function lookup() {
    const zip = document.getElementById("zipInput").value.trim();
    const resultDiv = document.getElementById("result");
    resultDiv.innerHTML = "Loading...";

    try {
      const response = await fetch(`http://127.0.0.1:5000/score_for_zip/${zip}`);

      // If backend returns 4xx or 5xx, handle gracefully
      if (!response.ok) {
        const text = await response.text();
        resultDiv.innerHTML = `<strong>Server error:</strong> ${response.status}<br>${text}`;
        return;
      }

      // Try to parse JSON
      const data = await response.json();

      if (data.error) {
        resultDiv.innerHTML = `<strong>Error:</strong> ${data.error}`;
        return;
      }

      // SUCCESS — display the score
      resultDiv.innerHTML = `
        <h3>Results</h3>
        <p><strong>ZIP:</strong> ${data.zipcode}</p>
        <p><strong>Tract:</strong> ${data.tract}</p>
        <p><strong>Score:</strong> ${data.score}</p>
      `;
    } catch (err) {
      resultDiv.innerHTML = `<strong>Request failed:</strong> ${err}`;
    }
  }
