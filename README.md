# Merch by Amazon Batch Uploader

A tool to automate uploading multiple products to Merch by Amazon using a spreadsheet.

## Features

- Upload products from a CSV or Excel spreadsheet
- Support for images from your local computer
- Visible browser automation that shows the entire process
- Waits for design processing before submitting
- Handles the confirmation dialog automatically
- Optional fields for bullet points and descriptions

## Prerequisites

- Python 3.7+
- Chrome browser installed
- Selenium and other dependencies (see requirements.txt)

## Installation

1. Download the code to your local machine
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
python main.py
```

4. Open a browser and go to `http://localhost:5000`

## Spreadsheet Format

Your spreadsheet must include these **required** columns:
- `title` - Product title
- `brand` - Brand name
- `image_path` - Full path to the image file on your computer

These columns are **optional**:
- `bullet_point_1` - First bullet point
- `bullet_point_2` - Second bullet point
- `description` - Product description

## How to Use

1. Prepare your spreadsheet with the required columns
2. Upload your spreadsheet through the web interface
3. Choose whether to use the local image paths or upload images directly
4. Start the upload process
5. The tool will open Chrome and start uploading your products
6. It will wait for each design to be processed before clicking the "Publish" button
7. It will handle the confirmation dialog by clicking the "Publish" button again

## Important Notes

- You need to be logged into your Merch by Amazon account in Chrome
- The tool runs locally on your machine to access your local images and browser
- You can pause, resume or stop the upload process at any time

## Troubleshooting

If you encounter any issues:
- Make sure Chrome is installed and updated
- Verify that your image paths are correct and accessible
- Check that your spreadsheet follows the required format
- Make sure you're logged into your Merch by Amazon account