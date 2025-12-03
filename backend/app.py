from flask import Flask, request, send_file
from flask_cors import CORS
import fitz  # PyMuPDF
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
import io
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

from presidio_analyzer.nlp_engine import NlpEngineProvider

# Initialize Presidio engines with small model
configuration = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
}
provider = NlpEngineProvider(nlp_configuration=configuration)
nlp_engine = provider.create_engine()
analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
anonymizer = AnonymizerEngine()

@app.route('/redact', methods=['POST'])
def redact_pdf():
    if 'file' not in request.files:
        return "No file part", 400
    
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    try:
        # Read PDF from memory
        pdf_stream = file.read()
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        
        # Iterate through pages
        for page in doc:
            # Get text from page
            text = page.get_text()
            
            # Analyze text for PII
            results = analyzer.analyze(text=text, entities=["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "US_DRIVER_LICENSE"], language='en')
            
            # Create redaction annotations
            for result in results:
                # Get bounding boxes for the detected entity
                # Note: Presidio gives character offsets, we need to map to PDF coordinates.
                # PyMuPDF's search_for is a simple way to find the text location.
                # Ideally, we would map offsets more precisely, but search_for is a good start.
                entity_text = text[result.start:result.end]
                
                # Search for the text on the page to get coordinates
                # We limit to 1 instance to avoid redacting wrong occurrences if duplicates exist,
                # but for now, let's redact all occurrences of this specific string snippet to be safe,
                # or refine logic to match context. 
                # A safer approach for this MVP is to search for the exact text snippet.
                areas = page.search_for(entity_text)
                
                for area in areas:
                    page.add_redact_annot(area, fill=(0, 0, 0))
            
            # Apply redactions
            page.apply_redactions()
            
        # Save redacted PDF to memory
        output_stream = io.BytesIO()
        doc.save(output_stream)
        output_stream.seek(0)
        
        return send_file(
            output_stream,
            as_attachment=True,
            download_name=f"redacted_{file.filename}",
            mimetype='application/pdf'
        )

    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
