import logging
from app import app

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.DEBUG)
    # Run the Flask application
    app.run(host="0.0.0.0", port=5000, debug=True)
