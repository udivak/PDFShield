document.addEventListener('DOMContentLoaded', function () {
    const fileInput = document.getElementById('fileInput');
    const fileNameDisplay = document.getElementById('fileName');
    const redactBtn = document.getElementById('redactBtn');
    const statusDiv = document.getElementById('status');

    let selectedFile = null;

    fileInput.addEventListener('change', function (e) {
        if (e.target.files.length > 0) {
            selectedFile = e.target.files[0];
            fileNameDisplay.textContent = selectedFile.name;
            redactBtn.disabled = false;
            statusDiv.textContent = '';
        } else {
            selectedFile = null;
            fileNameDisplay.textContent = 'No file chosen';
            redactBtn.disabled = true;
        }
    });

    redactBtn.addEventListener('click', async function () {
        if (!selectedFile) return;

        statusDiv.textContent = 'Analyzing for PII...';
        statusDiv.className = 'loading';
        redactBtn.disabled = true;

        const languageSelect = document.getElementById('languageSelect');
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('language', languageSelect.value);

        try {
            // 1. Send to Analyze Endpoint
            const response = await fetch('http://localhost:5001/analyze', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }

            const data = await response.json();

            if (!data.findings) {
                throw new Error("Invalid response from server");
            }

            statusDiv.textContent = `Found ${data.findings.length} items. Opening review...`;

            // 2. Read file as Base64 to pass to review page
            const reader = new FileReader();
            reader.onload = async function (e) {
                const base64PDF = e.target.result.split(',')[1]; // Remove "data:application/pdf;base64," prefix if present

                // 3. Store in local storage
                await chrome.storage.local.set({
                    pdfData: base64PDF,
                    findings: data.findings,
                    fileName: selectedFile.name
                });

                // 4. Open Review Page
                chrome.tabs.create({ url: 'review.html' });
                window.close(); // Close popup
            };
            reader.readAsDataURL(selectedFile);

        } catch (error) {
            console.error('Error:', error);
            statusDiv.textContent = 'Error: ' + error.message;
            statusDiv.className = 'error';
            redactBtn.disabled = false;
        }
    });
});
