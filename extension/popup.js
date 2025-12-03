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

        statusDiv.textContent = 'Processing... This may take a moment.';
        statusDiv.className = 'loading';
        redactBtn.disabled = true;

        const languageSelect = document.getElementById('languageSelect');
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('language', languageSelect.value);

        try {
            const response = await fetch('http://localhost:5001/redact', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `redacted_${selectedFile.name}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            statusDiv.textContent = 'Success! Downloading file...';
            statusDiv.className = 'success';
        } catch (error) {
            console.error('Error:', error);
            statusDiv.textContent = 'Error: ' + error.message;
            statusDiv.className = 'error';
        } finally {
            redactBtn.disabled = false;
        }
    });
});
