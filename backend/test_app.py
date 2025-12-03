import requests
import fitz
import io

def create_dummy_pdf():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Hello, my name is John Doe.", fontsize=12)
    page.insert_text((50, 70), "My email is john.doe@example.com", fontsize=12)
    page.insert_text((50, 90), "Call me at 555-0123", fontsize=12)
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def test_redaction():
    # Create dummy PDF
    pdf_buffer = create_dummy_pdf()
    
    # Send to backend
    url = 'http://localhost:5001/redact'
    files = {'file': ('test.pdf', pdf_buffer, 'application/pdf')}
    
    try:
        response = requests.post(url, files=files)
        
        if response.status_code == 200:
            print("Success: Received response from server")
            
            # Check if it's a valid PDF
            redacted_pdf = fitz.open(stream=response.content, filetype="pdf")
            print(f"Redacted PDF has {len(redacted_pdf)} pages")
            
            # Check text content (should still exist, but PII might be covered)
            # Note: PyMuPDF redaction removes text from the content stream if apply_redactions is called.
            # So we expect the PII text to be GONE or unsearchable.
            text = redacted_pdf[0].get_text()
            print("Extracted text from redacted PDF:")
            print(text)
            
            if "John Doe" not in text and "john.doe@example.com" not in text:
                print("PASS: PII text was removed from extraction!")
            else:
                print("FAIL: PII text still found in extraction.")
                
        else:
            print(f"Error: Server returned {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure the Flask server is running!")

if __name__ == "__main__":
    test_redaction()
