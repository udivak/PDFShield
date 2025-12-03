import requests
import fitz
import io

def create_dummy_pdf():
    doc = fitz.open()
    page = doc.new_page()
    # Insert Israeli ID and Phone (ASCII)
    page.insert_text((50, 50), "My ID is 123456789", fontsize=12)
    page.insert_text((50, 70), "Call me at 054-1234567", fontsize=12)
    # Try inserting Hebrew (might not render correctly without font, but text stream should have it)
    # "Shalom, my name is Israel Israeli"
    page.insert_text((50, 90), "Shalom, my name is Israel Israeli", fontsize=12)
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def test_redaction():
    pdf_buffer = create_dummy_pdf()
    
    # Send to backend with language='he'
    url = 'http://localhost:5001/redact'
    files = {'file': ('test_he.pdf', pdf_buffer, 'application/pdf')}
    data = {'language': 'he'}
    
    try:
        response = requests.post(url, files=files, data=data)
        
        if response.status_code == 200:
            print("Success: Received response from server")
            redacted_pdf = fitz.open(stream=response.content, filetype="pdf")
            text = redacted_pdf[0].get_text()
            print("Extracted text from redacted PDF:")
            print(text)
            
            # Check for ID redaction
            if "123456789" not in text:
                print("PASS: Israeli ID redacted")
            else:
                print("FAIL: Israeli ID NOT redacted")
                
            # Check for Phone redaction
            if "054-1234567" not in text:
                print("PASS: Israeli Phone redacted")
            else:
                print("FAIL: Israeli Phone NOT redacted")
                
        else:
            print(f"Error: Server returned {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_redaction()
