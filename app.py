from flask import Flask, request, render_template, jsonify, send_file
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import PdfFormatOption
from pydantic import BaseModel, ValidationError, field_validator
import tempfile
import os
import torch
import numpy as np
from typing import Optional, Union
import re
from werkzeug.utils import secure_filename
import io

# Set environment variables for better PyTorch stability
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'

# Configure PyTorch for CPU usage and stability
torch.set_num_threads(1)
if torch.cuda.is_available():
    torch.cuda.empty_cache()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    'pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls', 
    'html', 'htm', 'txt', 'md', 'rtf', 'odt', 'epub'
}

# Configure Docling with minimal pipeline options to avoid tensor errors
try:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False  # Disable OCR to reduce memory usage
    pipeline_options.do_table_structure = False  # Disable table structure to avoid tensor issues
    
    # Create converter with configuration
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
except Exception as e:
    # Fallback to basic converter if configuration fails
    print(f"Warning: Failed to configure advanced options, using basic converter: {e}")
    converter = DocumentConverter()

# Pydantic models for input validation
class TextInput(BaseModel):
    inputText: str
    
    @field_validator('inputText')
    @classmethod
    def validate_text(cls, v):
        if not v or not v.strip():
            raise ValueError('Input text cannot be empty')
        if len(v) > 100000:  # Limit to 100KB of text
            raise ValueError('Input text is too long (max 100,000 characters)')
        return v.strip()

class URLInput(BaseModel):
    url: str
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if not url_pattern.match(v):
            raise ValueError('Invalid URL format')
        return v

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_convert_document(filepath):
    """
    Attempt document conversion with fallback strategies
    """
    try:
        # First attempt: use configured converter
        with torch.no_grad():
            result = converter.convert(filepath)
            return result.document.export_to_markdown()
    except Exception as e:
        print(f"Primary conversion failed: {e}")
        
        try:
            # Second attempt: use basic converter
            basic_converter = DocumentConverter()
            with torch.no_grad():
                result = basic_converter.convert(filepath)
                return result.document.export_to_markdown()
        except Exception as e2:
            print(f"Fallback conversion failed: {e2}")
            
            # Third attempt: try with text extraction only
            try:
                # For text files, read directly
                if filepath.lower().endswith(('.txt', '.md')):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        return f.read()
                else:
                    raise Exception("Text extraction not supported for this file type")
            except Exception as e3:
                raise Exception(f"All conversion methods failed. Last error: {str(e3)}")

@app.route("/")
def index():
    return render_template("index.html")
@app.route("/process", methods=["POST"])
def process():
    try:
        # Set PyTorch to use CPU only and manage memory
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Check if it's a file upload or text input
        if 'file' in request.files and request.files['file'].filename:
            # Handle file upload
            file = request.files['file']
            
            if file.filename == '':
                return jsonify({"error": "No file selected"}), 400
            
            if not allowed_file(file.filename):
                return jsonify({"error": f"File type not supported. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}), 400
            
            # Save file temporarily
            filename = secure_filename(file.filename or "uploaded_file")
            temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(temp_filepath)
            
            try:
                # Convert with Docling using safe conversion method
                markdown_content = safe_convert_document(temp_filepath)
                
                return jsonify({
                    "result": markdown_content,
                    "filename": filename,
                    "success": True
                })
            
            except Exception as conversion_error:
                app.logger.error(f"Conversion failed for {filename}: {str(conversion_error)}")
                return jsonify({"error": f"Failed to convert file: {str(conversion_error)}"}), 500
            
            finally:
                # Clean up temp file
                if os.path.exists(temp_filepath):
                    os.unlink(temp_filepath)
                # Clear any cached tensors
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        
        else:
            # Handle text input (fallback for backward compatibility)
            if request.is_json and request.get_json(silent=True) is not None:
                data = request.get_json()
                # Validate input using Pydantic
                try:
                    text_input = TextInput(**data)
                    input_text = text_input.inputText
                except ValidationError as e:
                    return jsonify({"error": f"Validation error: {e.errors()}"}), 400
            else:
                # Fallback to form field
                input_text = request.form.get("inputText")
                if input_text:
                    try:
                        text_input = TextInput(inputText=input_text)
                        input_text = text_input.inputText
                    except ValidationError as e:
                        return jsonify({"error": f"Validation error: {e.errors()}"}), 400

            if not input_text:
                return jsonify({"error": "No file or text provided."}), 400

            # Write to temp file
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".md") as tmp:
                tmp.write(input_text)
                tmp.flush()
                tmp_file_path = tmp.name

            try:
                with torch.no_grad():  # Disable gradient computation
                    result = converter.convert(tmp_file_path)
                
                # Extract the document content as markdown string
                return jsonify({"result": result.document.export_to_markdown()})
            
            finally:
                os.unlink(tmp_file_path)
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    except Exception as e:
        app.logger.exception("Processing failed")
        return jsonify({"error": str(e)}), 500
    
if __name__ == "__main__":
    app.run(debug=True, port=5001)
