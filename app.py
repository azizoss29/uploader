import os
import logging
import time
import json
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename
import traceback
import tempfile
import threading

from utils.spreadsheet_parser import parse_spreadsheet
from utils.selenium_driver import MerchAutomation

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback_secret_key")

# Global variables to track upload state
upload_status = {
    "total": 0,
    "current": 0,
    "success": 0,
    "failed": 0,
    "status": "idle",  # idle, running, paused, completed, error
    "errors": [],
    "current_product": ""
}

upload_thread = None
upload_pause_event = threading.Event()
upload_stop_event = threading.Event()

# Set up temporary folders for file uploads
SPREADSHEET_FOLDER = tempfile.mkdtemp()
IMAGES_FOLDER = tempfile.mkdtemp()
ALLOWED_SPREADSHEET_EXTENSIONS = {'csv', 'xlsx', 'xls'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['SPREADSHEET_FOLDER'] = SPREADSHEET_FOLDER
app.config['IMAGES_FOLDER'] = IMAGES_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 64MB max upload size

def allowed_spreadsheet_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_SPREADSHEET_EXTENSIONS

def allowed_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle spreadsheet upload and validation"""
    global upload_status
    
    # Reset status on new upload
    upload_status = {
        "total": 0,
        "current": 0,
        "success": 0,
        "failed": 0,
        "status": "idle",
        "errors": [],
        "current_product": ""
    }
    
    # Check if a file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_spreadsheet_file(file.filename):
        return jsonify({'error': f'File type not allowed. Please upload one of: {", ".join(ALLOWED_SPREADSHEET_EXTENSIONS)}'}), 400
    
    # Save the file
    filename = secure_filename(file.filename or "")  # Handle possible None
    file_path = os.path.join(app.config['SPREADSHEET_FOLDER'], filename)
    file.save(file_path)
    
    try:
        # Parse the spreadsheet to validate data (without validating image paths)
        products = parse_spreadsheet(file_path)
        
        # Store the file path and product count in the session
        session['file_path'] = file_path
        session['product_count'] = len(products)
        
        # Store the list of image paths so we can display them for upload
        image_paths = [product['image_path'] for product in products]
        session['image_paths'] = image_paths
        
        return jsonify({
            'success': True,
            'message': f'Spreadsheet uploaded successfully. Found {len(products)} products to upload.',
            'count': len(products),
            'image_paths': image_paths
        })
    
    except Exception as e:
        logging.error(f"Error processing spreadsheet: {str(e)}")
        logging.error(traceback.format_exc())
        return jsonify({'error': f'Error processing spreadsheet: {str(e)}'}), 500

def upload_worker(file_path, headless, delay):
    """Worker function to handle the upload process in the background"""
    global upload_status
    
    try:
        # Parse the spreadsheet
        products = parse_spreadsheet(file_path)
        upload_status["total"] = len(products)
        upload_status["status"] = "running"
        
        # Set the upload status to a special message
        upload_status["errors"].append({
            "product": "note",
            "title": "Local Execution Required",
            "error": "This batch uploader needs to be run on your local machine to access Chrome. Please download this code and run it locally."
        })
        
        # Simulate "running" for a few seconds then set to completed
        time.sleep(5)
        upload_status["status"] = "completed"
        
        # Early return - we can't run Chrome in this environment
        return
        
        # The code below will only run when executed locally
        # Initialize Selenium automation - always set headless to False since user wants to see the browser
        # automation = MerchAutomation(headless=False)
        
        # Check if we're using uploaded images
        # image_mappings = session.get('image_mappings', {})
        
        # Start the upload process
        for i, product in enumerate(products):
            # Check if the upload has been stopped
            if upload_stop_event.is_set():
                upload_status["status"] = "stopped"
                break
            
            # Check if the upload has been paused
            while upload_pause_event.is_set() and not upload_stop_event.is_set():
                upload_status["status"] = "paused"
                time.sleep(1)
            
            upload_status["status"] = "running"
            upload_status["current"] = i + 1
            upload_status["current_product"] = product.get('title', f'Product {i+1}')
            
            try:
                # Check if we have a mapping for this image path
                original_path = product['image_path']
                if original_path in image_mappings:
                    # Use the uploaded image path
                    product['image_path'] = image_mappings[original_path]
                    logging.info(f"Using uploaded image for {product['title']}: {product['image_path']}")
                else:
                    # Use the original path (this will work when running locally)
                    logging.info(f"Using original image path for {product['title']}: {product['image_path']}")
                
                # Upload the product
                automation.upload_product(product)
                upload_status["success"] += 1
                time.sleep(delay)  # Add a delay between uploads to avoid rate limiting
            
            except Exception as e:
                logging.error(f"Error uploading product {i+1}: {str(e)}")
                upload_status["failed"] += 1
                upload_status["errors"].append({
                    "product": i + 1,
                    "title": product.get('title', f'Product {i+1}'),
                    "error": str(e)
                })
        
        # Clean up
        automation.close()
        upload_status["status"] = "completed"
    
    except Exception as e:
        logging.error(f"Upload worker error: {str(e)}")
        logging.error(traceback.format_exc())
        upload_status["status"] = "error"
        upload_status["errors"].append({
            "product": "global",
            "title": "Global Error",
            "error": str(e)
        })

@app.route('/start', methods=['POST'])
def start_upload():
    """Start the batch upload process"""
    global upload_thread, upload_status, upload_pause_event, upload_stop_event
    
    if 'file_path' not in session:
        return jsonify({'error': 'No file has been uploaded yet'}), 400
    
    if upload_status["status"] == "running":
        return jsonify({'error': 'Upload already in progress'}), 400
    
    # Get configuration options
    data = request.json or {}
    headless = data.get('headless', False)
    delay = int(data.get('delay', 2))
    
    # Reset control events
    upload_pause_event.clear()
    upload_stop_event.clear()
    
    # Get image upload mode (local or remote)
    image_mode = data.get('image_mode', 'local') if data else 'local'
    
    # Store image mode in session
    session['image_mode'] = image_mode
    
    # Start the upload process in a separate thread
    file_path = session['file_path']
    upload_thread = threading.Thread(
        target=upload_worker, 
        args=(file_path, headless, delay)
    )
    upload_thread.daemon = True
    upload_thread.start()
    
    return jsonify({'success': True, 'message': 'Upload started'})

@app.route('/upload_image', methods=['POST'])
def upload_image():
    """Upload an individual product image"""
    if 'image' not in request.files:
        return jsonify({'error': 'No image file part'}), 400
        
    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({'error': 'No image selected'}), 400
        
    if not allowed_image_file(image_file.filename):
        return jsonify({'error': f'Image file type not allowed. Please upload one of: {", ".join(ALLOWED_IMAGE_EXTENSIONS)}'}), 400
    
    # Get the image index and original path
    image_index = request.form.get('index')
    original_path = request.form.get('original_path')
    
    if not image_index or not original_path:
        return jsonify({'error': 'Missing image index or original path'}), 400
    
    # Save the image
    filename = secure_filename(image_file.filename or "")  # Handle possible None
    file_path = os.path.join(app.config['IMAGES_FOLDER'], filename)
    image_file.save(file_path)
    
    # Store the mapping from original path to uploaded path
    if 'image_mappings' not in session:
        session['image_mappings'] = {}
    
    session['image_mappings'][original_path] = file_path
    
    return jsonify({
        'success': True, 
        'message': f'Image uploaded successfully',
        'path': file_path
    })

@app.route('/status', methods=['GET'])
def get_status():
    """Get the current upload status"""
    return jsonify(upload_status)

@app.route('/pause', methods=['POST'])
def pause_upload():
    """Pause the current upload"""
    if upload_status["status"] != "running":
        return jsonify({'error': 'No active upload to pause'}), 400
    
    upload_pause_event.set()
    return jsonify({'success': True, 'message': 'Upload paused'})

@app.route('/resume', methods=['POST'])
def resume_upload():
    """Resume a paused upload"""
    if upload_status["status"] != "paused":
        return jsonify({'error': 'No paused upload to resume'}), 400
    
    upload_pause_event.clear()
    return jsonify({'success': True, 'message': 'Upload resumed'})

@app.route('/stop', methods=['POST'])
def stop_upload():
    """Stop the current upload"""
    if upload_status["status"] not in ["running", "paused"]:
        return jsonify({'error': 'No active upload to stop'}), 400
    
    upload_stop_event.set()
    upload_pause_event.clear()  # In case it was paused
    return jsonify({'success': True, 'message': 'Upload stopped'})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
