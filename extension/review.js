// Configure PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = 'lib/pdf.worker.js';

let pdfDoc = null;
let currentFindings = [];
let pdfBase64 = null; // Store base64 to ensure we always have data for upload
let originalFileName = "document.pdf";

document.addEventListener('DOMContentLoaded', async () => {
    // Load data passed from popup
    try {
        const data = await chrome.storage.local.get(['pdfData', 'findings', 'fileName']);

        if (!data.pdfData || !data.findings) {
            alert("No document data found. Please try again.");
            return;
        }

        pdfBase64 = data.pdfData;
        const pdfBytes = base64ToArrayBuffer(pdfBase64);
        currentFindings = data.findings;
        originalFileName = data.fileName || "document.pdf";

        renderPDF(pdfBytes);
        updateStats();

    } catch (e) {
        console.error("Error loading data", e);
        alert("Error loading data: " + e.message);
    }

    document.getElementById('cancelBtn').addEventListener('click', () => {
        window.close();
    });

    document.getElementById('downloadBtn').addEventListener('click', finalizeRedaction);
});

function base64ToArrayBuffer(base64) {
    const binaryString = window.atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
}

async function renderPDF(data) {
    const container = document.getElementById('container');

    try {
        pdfDoc = await pdfjsLib.getDocument({ data: data }).promise;

        for (let pageNum = 1; pageNum <= pdfDoc.numPages; pageNum++) {
            const page = await pdfDoc.getPage(pageNum);
            const scale = 1.5; // Good review size
            const viewport = page.getViewport({ scale: scale });

            // Create page wrapper
            const pageWrapper = document.createElement('div');
            pageWrapper.className = 'page-container';
            pageWrapper.style.width = `${viewport.width}px`;
            pageWrapper.style.height = `${viewport.height}px`;

            // Canvas for PDF content
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            canvas.height = viewport.height;
            canvas.width = viewport.width;

            await page.render({ canvasContext: context, viewport: viewport }).promise;
            pageWrapper.appendChild(canvas);

            // --- Manual Redaction Logic ---
            let isDrawing = false;
            let startX, startY;
            let selectionBox = null;

            pageWrapper.addEventListener('mousedown', (e) => {
                // Prevent interfering with clicking existing boxes
                if (e.target.classList.contains('redaction-box')) return;

                e.preventDefault(); // Stop native drag/text selection

                isDrawing = true;
                const rect = pageWrapper.getBoundingClientRect();
                startX = e.clientX - rect.left;
                startY = e.clientY - rect.top;

                selectionBox = document.createElement('div');
                selectionBox.className = 'selection-box';
                selectionBox.style.left = `${startX}px`;
                selectionBox.style.top = `${startY}px`;
                pageWrapper.appendChild(selectionBox);
            });

            pageWrapper.addEventListener('mousemove', (e) => {
                if (!isDrawing) return;
                const rect = pageWrapper.getBoundingClientRect();
                const currentX = e.clientX - rect.left;
                const currentY = e.clientY - rect.top;

                const width = Math.abs(currentX - startX);
                const height = Math.abs(currentY - startY);
                const left = Math.min(currentX, startX);
                const top = Math.min(currentY, startY);

                selectionBox.style.width = `${width}px`;
                selectionBox.style.height = `${height}px`;
                selectionBox.style.left = `${left}px`;
                selectionBox.style.top = `${top}px`;
            });

            pageWrapper.addEventListener('mouseup', (e) => {
                if (!isDrawing) return;
                isDrawing = false;

                // Finalize selection
                if (selectionBox) {
                    const wVal = parseFloat(selectionBox.style.width);
                    const hVal = parseFloat(selectionBox.style.height);

                    const rect = {
                        x: parseFloat(selectionBox.style.left),
                        y: parseFloat(selectionBox.style.top),
                        w: isNaN(wVal) ? 0 : wVal,
                        h: isNaN(hVal) ? 0 : hVal
                    };

                    pageWrapper.removeChild(selectionBox);
                    selectionBox = null;

                    // Ignore very small boxes
                    if (rect.w < 5 || rect.h < 5) return;

                    // Convert back to PDF coordinates
                    const finding = {
                        page: pageNum,
                        x0: rect.x / scale,
                        y0: rect.y / scale,
                        x1: (rect.x + rect.w) / scale,
                        y1: (rect.y + rect.h) / scale,
                        text: "Manual Selection",
                        type: "MANUAL",
                        id: `manual_${Date.now()}`
                    };

                    currentFindings.push(finding);
                    renderBox(finding, pageWrapper, scale);
                    updateStats();
                }
            });

            // Render existing findings
            const pageFindings = currentFindings.filter(f => f.page === pageNum);
            pageFindings.forEach(finding => {
                renderBox(finding, pageWrapper, scale);
            });

            container.appendChild(pageWrapper);
        }
    } catch (e) {
        console.error("Render error", e);
        alert("Error rendering PDF: " + e.message);
    }
}

function renderBox(finding, container, scale) {
    if (finding.ignored) return;

    // Calculate display coordinates
    const rect = {
        x: finding.x0 * scale,
        y: finding.y0 * scale,
        w: (finding.x1 - finding.x0) * scale,
        h: (finding.y1 - finding.y0) * scale
    };

    const box = document.createElement('div');
    box.className = 'redaction-box';
    box.id = `box-${finding.id}`;
    box.style.left = `${rect.x}px`;
    box.style.top = `${rect.y}px`;
    box.style.width = `${rect.w}px`;
    box.style.height = `${rect.h}px`;
    box.title = `${finding.type}: ${finding.text}`;

    if (finding.type === 'MANUAL') {
        box.style.border = '2px solid blue';
        box.style.backgroundColor = 'rgba(0, 0, 255, 0.3)';
    }

    box.addEventListener('click', (e) => {
        e.stopPropagation(); // Stop propagation to pageWrapper mousedown

        // Remove redaction
        if (confirm("Remove this redaction?")) {
            finding.ignored = true;
            if (finding.type === 'MANUAL') {
                const index = currentFindings.indexOf(finding);
                if (index > -1) currentFindings.splice(index, 1);
            }
            container.removeChild(box);
            updateStats();
        }
    });

    container.appendChild(box);
}

function updateStats() {
    const total = currentFindings.length;
    const ignored = currentFindings.filter(f => f.ignored).length;
    const active = total - ignored;
    document.getElementById('stats').textContent =
        `Found: ${total} | Redacting: ${active} | Removed: ${ignored}`;
}

async function finalizeRedaction() {
    const btn = document.getElementById('downloadBtn');
    btn.disabled = true;
    btn.textContent = "Processing...";

    try {
        const activeFindings = currentFindings.filter(f => !f.ignored);

        const formData = new FormData();

        // Use the global base64 string to create the blob
        // Decode base64 to byte string
        const byteCharacters = atob(pdfBase64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const pdfBlob = new Blob([byteArray], { type: "application/pdf" });

        formData.append('file', pdfBlob, originalFileName);
        formData.append('redactions', JSON.stringify(activeFindings));

        const response = await fetch('http://localhost:5001/redact_custom', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error("Server error: " + response.statusText);

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `redacted_${originalFileName}`;
        document.body.appendChild(a);
        a.click();

        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        btn.textContent = "Done!";
        setTimeout(() => window.close(), 2000);

    } catch (e) {
        console.error(e);
        alert("Error finalizing: " + e.message);
        btn.disabled = false;
        btn.textContent = "Confirm & Download";
    }
}
