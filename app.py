from flask import Flask, request, render_template, jsonify, send_file
from docling.document_converter import DocumentConverter
from pydantic import BaseModel, ValidationError, field_validator
import tempfile
import os
import torch
import numpy as np
from typing import Optional, Union
import re
from werkzeug.utils import secure_filename
import io

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    'pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls', 
    'html', 'htm', 'txt', 'md', 'rtf', 'odt', 'epub'
}

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

@app.route("/")
def index():
    return render_template("index.html")
@app.route("/process", methods=["POST"])
def process():
    try:
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
                # Convert with Docling
                result = converter.convert(temp_filepath)
                
                # Extract the document content as markdown string
                markdown_content = result.document.export_to_markdown()
                
                return jsonify({
                    "result": markdown_content,
                    "filename": filename,
                    "success": True
                })
            
            finally:
                # Clean up temp file
                if os.path.exists(temp_filepath):
                    os.unlink(temp_filepath)
        
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

            result = converter.convert(tmp_file_path)

            os.unlink(tmp_file_path)

            # Extract the document content as markdown string
            return jsonify({"result": result.document.export_to_markdown()})

    except Exception as e:
        app.logger.exception("Processing failed")
        return jsonify({"error": str(e)}), 500
    
if __name__ == "__main__":
    app.run(debug=True, port=5001)
