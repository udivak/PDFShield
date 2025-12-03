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
from presidio_analyzer import PatternRecognizer, Pattern
from transformers import pipeline

# Initialize Presidio engines (English only via spaCy)
configuration = {
    "nlp_engine_name": "spacy",
    "models": [
        {"lang_code": "en", "model_name": "en_core_web_sm"},
        {"lang_code": "he", "model_name": "en_core_web_sm"}, # Use English model as base for Hebrew Regex
    ],
}
provider = NlpEngineProvider(nlp_configuration=configuration)
nlp_engine = provider.create_engine()
analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
anonymizer = AnonymizerEngine()

# Initialize Hebrew NER pipeline (Hugging Face)
# We use aggregation_strategy="simple" to group tokens into words
try:
    he_ner = pipeline("ner", model="avichr/heBERT_NER", aggregation_strategy="simple")
    print("Hebrew model loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load Hebrew model: {e}")
    he_ner = None

# --- Custom Regex Recognizers for Israel ---
# (Same as before)
id_pattern = Pattern(name="israeli_id_pattern", regex=r"\b\d{9}\b", score=0.5)
id_recognizer = PatternRecognizer(supported_entity="ISRAELI_ID", patterns=[id_pattern], supported_language="he")
analyzer.registry.add_recognizer(id_recognizer)
id_recognizer_en = PatternRecognizer(supported_entity="ISRAELI_ID", patterns=[id_pattern], supported_language="en")
analyzer.registry.add_recognizer(id_recognizer_en)

phone_pattern = Pattern(name="israeli_phone_pattern", regex=r"\b0(?:5[^7]|[2-4]|[8-9])(?:-?\d){7}\b", score=0.6)
phone_recognizer = PatternRecognizer(supported_entity="ISRAELI_PHONE", patterns=[phone_pattern], supported_language="he")
analyzer.registry.add_recognizer(phone_recognizer)
phone_recognizer_en = PatternRecognizer(supported_entity="ISRAELI_PHONE", patterns=[phone_pattern], supported_language="en")
analyzer.registry.add_recognizer(phone_recognizer_en)


@app.route('/redact', methods=['POST'])
def redact_pdf():
    if 'file' not in request.files:
        return "No file part", 400
    
    file = request.files['file']
    language = request.form.get('language', 'en') # Default to English
    
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
            results = []
            
            if language == 'he':
                # 1. Run Regex (ID, Phone) using Presidio
                # We use 'he' language so our custom recognizers trigger
                regex_results = analyzer.analyze(text=text, entities=["ISRAELI_ID", "ISRAELI_PHONE"], language='he')
                results.extend(regex_results)
                
                # 2. Run Hebrew NER (Names, Locs, Orgs) using Transformers
                if he_ner:
                    ner_results = he_ner(text)
                    for entity in ner_results:
                        # entity structure: {'entity_group': 'PER', 'score': 0.99, 'word': '...', 'start': 10, 'end': 15}
                        # We need to convert this to Presidio-like result or just handle redaction directly.
                        # For simplicity, we'll handle redaction directly here by adding to a list of areas to redact.
                        
                        # Note: We need to find the text in the PDF.
                        # Transformers offsets are based on the string 'text'.
                        # PyMuPDF 'search_for' searches for the string.
                        # To be precise, we should use the text snippet.
                        entity_text = text[entity['start']:entity['end']]
                        
                        # Filter low confidence
                        if entity['score'] < 0.5:
                            continue
                            
                        # Map entity group to something meaningful if needed, but we redact everything found.
                        # Common groups: PER, ORG, LOC
                        
                        # Add to results list (simulated) or just redact immediately.
                        # Let's redact immediately for NER results.
                        areas = page.search_for(entity_text)
                        for area in areas:
                            page.add_redact_annot(area, fill=(0, 0, 0))
                            
            else:
                # English entities + Custom Regex
                entities = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "US_DRIVER_LICENSE", "ISRAELI_ID", "ISRAELI_PHONE"]
                results = analyzer.analyze(text=text, entities=entities, language='en')
            
            
            # Create redaction annotations for Presidio results
            for result in results:
                entity_text = text[result.start:result.end]
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
        print(e)
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
