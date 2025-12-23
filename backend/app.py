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


@app.route('/analyze', methods=['POST'])
def analyze_pdf():
    """
    Analyzes the PDF and returns a list of detected PII with their coordinates.
    Does NOT modify the PDF.
    """
    if 'file' not in request.files:
        return "No file part", 400
    
    file = request.files['file']
    language = request.form.get('language', 'en')
    
    if file.filename == '':
        return "No selected file", 400

    try:
        pdf_stream = file.read()
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        
        findings = []
        
        for page_num, page in enumerate(doc):
            text = page.get_text()
            results = []
            
            if language == 'he':
                # Custom Regex (ID, Phone)
                regex_results = analyzer.analyze(text=text, entities=["ISRAELI_ID", "ISRAELI_PHONE"], language='he')
                results.extend(regex_results)
                
                # Hebrew NER
                if he_ner:
                    ner_results = he_ner(text)
                    for entity in ner_results:
                        if entity['score'] < 0.5:
                            continue
                        # Create a pseudo-Presidio result for consistency or just handle directly
                        # We'll stick to collecting text/offsets.
                        # Note: heBERT returns offsets in the passed text string.
                        
                        # We will store enough info to finding the areas.
                        # It's easier to unify by just collecting the "entity_text" to search for.
                        entity_text = text[entity['start']:entity['end']]
                        
                        # Add to our unified results logic
                        results.append({"text": entity_text, "type": entity.get('entity_group', 'NER'), "score": float(entity['score'])})

            else:
                # English entities
                entities = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "US_DRIVER_LICENSE", "ISRAELI_ID", "ISRAELI_PHONE"]
                presidio_results = analyzer.analyze(text=text, entities=entities, language='en')
                results.extend(presidio_results)

            # Process all results to find coordinates
            for result in results:
                entity_text = ""
                entity_type = "UNKNOWN"
                
                # Handle Presidio result object
                if hasattr(result, 'start') and hasattr(result, 'end'):
                    entity_text = text[result.start:result.end]
                    entity_type = result.entity_type
                # Handle our dictionary hack for heBERT
                elif isinstance(result, dict):
                    entity_text = result['text']
                    entity_type = result['type']
                
                if not entity_text.strip():
                    continue

                # Find coordinates on page
                # search_for returns a list of Rect objects (x0, y0, x1, y1)
                areas = page.search_for(entity_text)
                
                for area in areas:
                    findings.append({
                        "page": page_num + 1, # 1-based for display
                        "x0": area.x0,
                        "y0": area.y0,
                        "x1": area.x1,
                        "y1": area.y1,
                        "text": entity_text,
                        "type": entity_type,
                        "id": f"{page_num}_{area.x0}_{area.y0}" # Unique ID for frontend
                    })

        return {"findings": findings}

    except Exception as e:
        print(f"Error in analyze: {e}")
        return str(e), 500


@app.route('/redact_custom', methods=['POST'])
def redact_custom():
    """
    Receives a PDF and a JSON list of redaction zones (page, rect).
    Applies the redactions and returns the PDF.
    """
    if 'file' not in request.files:
        return "No file part", 400
    
    file = request.files['file']
    import json
    redactions_json = request.form.get('redactions', '[]')
    
    try:
        redactions = json.loads(redactions_json)
    except:
        return "Invalid JSON in redactions", 400
        
    if file.filename == '':
        return "No selected file", 400

    try:
        pdf_stream = file.read()
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        
        for i, redaction in enumerate(redactions):
            try:
                # redaction: { 'page': 1, 'x0': ..., 'y0': ..., ... }
                page_idx = int(redaction.get('page', 0)) - 1
                if 0 <= page_idx < len(doc):
                    page = doc[page_idx]
                    
                    # Safely get coordinates, defaulting to 0.0 if missing or None
                    def safe_float(val):
                        if val is None: return 0.0
                        try: 
                            return float(val)
                        except: 
                            return 0.0

                    x0 = safe_float(redaction.get('x0'))
                    y0 = safe_float(redaction.get('y0'))
                    x1 = safe_float(redaction.get('x1'))
                    y1 = safe_float(redaction.get('y1'))
                    
                    # Validate coordinates (avoid NaN or Inf)
                    if not (all(map(lambda v: v == v and v != float('inf'), [x0, y0, x1, y1]))):
                         print(f"Skipping invalid redaction {i}: {redaction}")
                         continue

                    rect = fitz.Rect(x0, y0, x1, y1)
                    page.add_redact_annot(rect, fill=(0, 0, 0))
            except Exception as e:
                print(f"Error processing redaction {i}: {e}")
                continue
        
        for page in doc:
            page.apply_redactions()

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
        import traceback
        traceback.print_exc()
        print(f"Error in redact_custom: {e}")
        return str(e), 500

@app.route('/redact', methods=['POST'])
def redact_pdf():
    # Legacy endpoint for "One Click" redaction (or we can update frontend to use analyze->confirm flow always)
    # For now, keeping it as is but we could refactor it to use analyze logic internally if we wanted to DRY.
    # To minimize changes to the existing reliable flow while adding new features, I'll keep the logic mostly similar 
    # but use the same extraction steps.
    pass # Implementation below is kept from original but we will leave it or overwrite if requested. 
         # Actually, the user asked to DEVELOP OPTION 1 which replaces the flow. 
         # But the extensions's popup.js still calls /redact. 
         # I will leave the original /redact mostly as is for backward compatibility or direct usage, 
         # but I'll make sure it works if I didn't delete it.
         # Wait, I am REPLACING lines 54-141. So I need to provide the implementation for /redact as well if I want to keep it.
         # Or I can just redirect /redact to use the new logic: analyze -> apply all -> return.
    
    # Let's keep /redact working as "Auto Mode".
    if 'file' not in request.files:
        return "No file part", 400
    file = request.files['file']
    language = request.form.get('language', 'en')
    
    # ... (Re-implementing /redact logic or reusing analyzing) ...
    # Reuse valid logic:
    try:
        # We can actually just call analyze logic internally, but that returns JSON.
        # Let's just copy-paste the core logic to avoid complexity of internal HTTP calls or deep refactoring now.
        # Ideally, we'd extract a 'get_findings(doc, lang)' function.
        
        # ... (Original logic for /redact, simplified for brevity in this thought process, but needs to be in code) ...
        # Actually, let's extract the finding logic to a helper function to avoid duplication.
        pass
    except Exception as e:
        pass
    
    # Impl of /redact using the new helper method structure (simulated inline for the tool call)
    
    if file.filename == '':
        return "No selected file", 400

    try:
        pdf_stream = file.read()
        doc = fitz.open(stream=pdf_stream, filetype="pdf")
        
        # Copy of finding logic from analyze_pdf
        # To avoid duplicating 50 lines of code, I should probably have created a helper function.
        # Since I can't restart the tool call easily, I will implement /redact to just do what it did before.
        
        for page in doc:
            text = page.get_text()
            results = []
            if language == 'he':
                results.extend(analyzer.analyze(text=text, entities=["ISRAELI_ID", "ISRAELI_PHONE"], language='he'))
                if he_ner:
                     # minimal heBERT support for legacy endpoint
                     ner_res = he_ner(text)
                     for ent in ner_res:
                         if ent['score'] >= 0.5:
                            txt = text[ent['start']:ent['end']]
                            areas = page.search_for(txt)
                            for area in areas: page.add_redact_annot(area, fill=(0,0,0))
            else:
                 entities = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "US_DRIVER_LICENSE", "ISRAELI_ID", "ISRAELI_PHONE"]
                 results.extend(analyzer.analyze(text=text, entities=entities, language='en'))
            
            for result in results:
                if hasattr(result, 'start'):
                    t = text[result.start:result.end]
                    for area in page.search_for(t):
                         page.add_redact_annot(area, fill=(0,0,0))
            
            page.apply_redactions()

        output_stream = io.BytesIO()
        doc.save(output_stream)
        output_stream.seek(0)
        return send_file(output_stream, as_attachment=True, download_name=f"redacted_{file.filename}", mimetype='application/pdf')
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
