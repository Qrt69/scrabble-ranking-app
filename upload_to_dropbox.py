#!/usr/bin/env python3
"""
Helper script to upload current Excel files to Dropbox for initial setup.
Run this script once to migrate your files to Dropbox.
"""

import os
import dropbox_integration
import sys

# Try to load from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv is not installed, continue without it
    pass

def upload_files_to_dropbox():
    """Upload current Excel files to Dropbox"""
    
    # Check if Dropbox access token is available
    access_token = os.environ.get("DROPBOX_ACCESS_TOKEN")
    if not access_token:
        print("❌ Error: DROPBOX_ACCESS_TOKEN environment variable not set")
        print("Please set your Dropbox access token as an environment variable")
        return False
    
    # Initialize Dropbox
    print("🔗 Initializing Dropbox connection...")
    if not dropbox_integration.initialize_dropbox(access_token):
        print("❌ Failed to connect to Dropbox")
        return False
    
    print("✅ Dropbox connection successful")
    
    # List files to upload
    files_to_upload = [
        "Globaal 2024-2025.xlsx",
        "Zomer 2025.xlsx", 
        "Info.xlsx"
    ]
    
    dropbox_manager = dropbox_integration.get_dropbox_manager()
    
    # Upload each file
    for filename in files_to_upload:
        if os.path.exists(filename):
            print(f"📤 Uploading {filename}...")
            dropbox_path = f"/Scrabble App/{filename}"
            
            if dropbox_manager.upload_file(filename, dropbox_path):
                print(f"✅ Successfully uploaded {filename}")
            else:
                print(f"❌ Failed to upload {filename}")
                return False
        else:
            print(f"⚠️  File {filename} not found locally - skipping")
    
    # List files in Dropbox to verify
    print("\n📋 Files in Dropbox:")
    files = dropbox_manager.list_files()
    for file_info in files:
        print(f"  - {file_info['name']} ({file_info['size']} bytes)")
    
    print("\n🎉 Upload complete! Your files are now in Dropbox.")
    print("You can now deploy your app with Dropbox integration enabled.")
    
    return True

if __name__ == "__main__":
    success = upload_files_to_dropbox()
    sys.exit(0 if success else 1) 