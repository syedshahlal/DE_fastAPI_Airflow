/* fastAPI_app/static/js/script.js */

let accessToken = "";
let transactionChart;

// Function to initialize the Chart.js chart
function initializeChart() {
    const ctx = document.getElementById('transactionChart').getContext('2d');
    transactionChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [], // Transaction IDs or timestamps
            datasets: [{
                label: 'Transaction Amount',
                data: [],
                backgroundColor: 'rgba(54, 162, 235, 0.6)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Transaction ID'
                    }
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Amount (USD)'
                    }
                }
            }
        }
    });
}

// Function to handle user login
async function login() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    const response = await fetch('/token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`
    });

    const data = await response.json();

    if (response.status === 200) {
        accessToken = data.access_token;
        document.getElementById('login-status').innerText = "Login successful!";
        document.getElementById('login-form').style.display = 'none';
        document.getElementById('chart-container').style.display = 'block';
        initializeChart();
        connectWebSocket();
    } else {
        document.getElementById('login-status').innerText = "Login failed: " + data.detail;
    }
}

// Function to connect to the WebSocket with the token
function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsProtocol}://${window.location.host}/ws/transactions?token=${accessToken}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = function(event) {
        console.log("WebSocket connection established.");
    };

    ws.onmessage = function(event) {
        const transaction = JSON.parse(event.data);
        const label = transaction.transaction_id.substring(0, 8); // Shorten ID for display
        const amount = transaction.transaction_details.amount;

        // Add data to chart
        transactionChart.data.labels.push(label);
        transactionChart.data.datasets[0].data.push(amount);

        // Keep only the latest 20 transactions
        if (transactionChart.data.labels.length > 20) {
            transactionChart.data.labels.shift();
            transactionChart.data.datasets[0].data.shift();
        }

        transactionChart.update();
    };

    ws.onclose = function(event) {
        console.log("WebSocket connection closed. Attempting to reconnect in 5 seconds...");
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = function(error) {
        console.error("WebSocket error:", error);
        ws.close();
    };
}

// Attach the login function to the login button
document.addEventListener('DOMContentLoaded', () => {
    const loginButton = document.querySelector('#login-form button');
    loginButton.addEventListener('click', login);
});
