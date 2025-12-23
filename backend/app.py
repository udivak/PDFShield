from flask import Flask, request, send_file
from flask_cors import CORS
import fitz  # PyMuPDF
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from transformers import pipeline
import io
import json
import traceback

app = Flask(__name__)
CORS(app)

# --- Configuration & Initialization ---
# Initialize Presidio with English spaCy model.
configuration = {
    "nlp_engine_name": "spacy",
    "models": [
        {"lang_code": "en", "model_name": "en_core_web_sm"},
        {"lang_code": "he", "model_name": "en_core_web_sm"},
    ],
}
provider = NlpEngineProvider(nlp_configuration=configuration)
analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
anonymizer = AnonymizerEngine()

# Initialize Hebrew NER using heBERT from Hugging Face.
try:
    he_ner = pipeline("ner", model="avichr/heBERT_NER", aggregation_strategy="simple")
    print("Hebrew model loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load Hebrew model: {e}")
    he_ner = None

# Register custom regex patterns for Israeli ID and Phone numbers.
id_pattern = Pattern(name="israeli_id_pattern", regex=r"\b\d{9}\b", score=0.5)
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="ISRAELI_ID", patterns=[id_pattern], supported_language="he"))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="ISRAELI_ID", patterns=[id_pattern], supported_language="en"))

phone_pattern = Pattern(name="israeli_phone_pattern", regex=r"\b0(?:5[^7]|[2-4]|[8-9])(?:-?\d){7}\b", score=0.6)
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="ISRAELI_PHONE", patterns=[phone_pattern], supported_language="he"))
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="ISRAELI_PHONE", patterns=[phone_pattern], supported_language="en"))


@app.route('/analyze', methods=['POST'])
def analyze_pdf():
    # Analyzes PDF text for PII using Presidio (En) and heBERT/Regex (He).
    # Returns a list of detected entities with bounding box coordinates for frontend preview.
    if 'file' not in request.files:
        return "No file part", 400
    
    file = request.files['file']
    language = request.form.get('language', 'en')
    
    if file.filename == '':
        return "No selected file", 400

    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        findings = []
        
        for page_num, page in enumerate(doc):
            text = page.get_text()
            results = []
            
            if language == 'he':
                # Custom Regex + heBERT
                results.extend(analyzer.analyze(text=text, entities=["ISRAELI_ID", "ISRAELI_PHONE"], language='he'))
                if he_ner:
                    ner_results = he_ner(text)
                    for entity in ner_results:
                        if entity['score'] >= 0.5:
                            # Convert heBERT result to dict for consistent processing
                            results.append({"text": text[entity['start']:entity['end']], "type": entity.get('entity_group', 'NER')})
            else:
                # English Presidio Analysis
                entities = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "US_DRIVER_LICENSE", "ISRAELI_ID", "ISRAELI_PHONE"]
                results.extend(analyzer.analyze(text=text, entities=entities, language='en'))

            # Convert text findings to visual bounding boxes
            for result in results:
                entity_text = ""
                entity_type = "UNKNOWN"
                
                if hasattr(result, 'start'): # Presidio result
                    entity_text = text[result.start:result.end]
                    entity_type = result.entity_type
                elif isinstance(result, dict): # heBERT result
                    entity_text = result['text']
                    entity_type = result['type']
                
                if not entity_text.strip(): continue

                for area in page.search_for(entity_text):
                    findings.append({
                        "page": page_num + 1,
                        "x0": area.x0, "y0": area.y0, "x1": area.x1, "y1": area.y1,
                        "text": entity_text, "type": entity_type,
                        "id": f"{page_num}_{area.x0}_{area.y0}"
                    })

        return {"findings": findings}

    except Exception as e:
        print(f"Error in analyze: {e}")
        return str(e), 500


@app.route('/redact_custom', methods=['POST'])
def redact_custom():
    # Applies specific redactions (black boxes) to the PDF based on provided coordinates.
    # Accepts a JSON list of redaction zones and returns the modified PDF file.
    if 'file' not in request.files: return "No file part", 400
    file = request.files['file']
    if file.filename == '': return "No selected file", 400
    
    try:
        redactions = json.loads(request.form.get('redactions', '[]'))
    except:
        return "Invalid JSON in redactions", 400

    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        
        for i, redaction in enumerate(redactions):
            try:
                page_idx = int(redaction.get('page', 0)) - 1
                if 0 <= page_idx < len(doc):
                    # Safely convert coordinates, defaulting to 0 on error
                    def safe(v): 
                        if v is None: return 0.0
                        try: return float(v)
                        except: return 0.0

                    coords = [safe(redaction.get(k)) for k in ['x0', 'y0', 'x1', 'y1']]
                    if not all(map(lambda v: v == v and v != float('inf'), coords)):
                        print(f"Skipping invalid redaction {i}: {redaction}")
                        continue

                    doc[page_idx].add_redact_annot(fitz.Rect(*coords), fill=(0, 0, 0))
            except Exception as e:
                print(f"Error processing redaction {i}: {e}")
                continue
        
        for page in doc:
            page.apply_redactions()

        output_stream = io.BytesIO()
        doc.save(output_stream)
        output_stream.seek(0)
        
        return send_file(output_stream, as_attachment=True, download_name=f"redacted_{file.filename}", mimetype='application/pdf')

    except Exception as e:
        traceback.print_exc()
        return str(e), 500


@app.route('/redact', methods=['POST'])
def redact_pdf():
    # Legacy 'Auto-Redact' endpoint. Analyzes and applies redactions in one pass without user review.
    # Kept for backward compatibility or potential 'Quick Redact' feature.
    if 'file' not in request.files: return "No file part", 400
    file = request.files['file']
    if file.filename == '': return "No selected file", 400
    language = request.form.get('language', 'en')

    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        
        for page in doc:
            text = page.get_text()
            results = []
            
            if language == 'he':
                results.extend(analyzer.analyze(text=text, entities=["ISRAELI_ID", "ISRAELI_PHONE"], language='he'))
                if he_ner:
                    for ent in he_ner(text):
                        if ent['score'] >= 0.5:
                            for area in page.search_for(text[ent['start']:ent['end']]):
                                page.add_redact_annot(area, fill=(0, 0, 0))
            else:
                entities = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "US_DRIVER_LICENSE", "ISRAELI_ID", "ISRAELI_PHONE"]
                results.extend(analyzer.analyze(text=text, entities=entities, language='en'))
            
            for result in results:
                if hasattr(result, 'start'):
                    for area in page.search_for(text[result.start:result.end]):
                        page.add_redact_annot(area, fill=(0, 0, 0))
            
            page.apply_redactions()
            
        output_stream = io.BytesIO()
        doc.save(output_stream)
        output_stream.seek(0)
        
        return send_file(output_stream, as_attachment=True, download_name=f"redacted_{file.filename}", mimetype='application/pdf')

    except Exception as e:
        print(e)
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
