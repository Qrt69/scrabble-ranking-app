#!/usr/bin/env python3
"""
Test script to debug Dropbox refresh token connection
"""

import os
import dropbox
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_refresh_token_connection():
    """Test the refresh token connection"""
    
    # Get environment variables
    app_key = os.environ.get("DROPBOX_APP_KEY", "")
    app_secret = os.environ.get("DROPBOX_APP_SECRET", "")
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN", "")
    access_token = os.environ.get("DROPBOX_TOKEN", "")
    
    print("=" * 60)
    print("DROPBOX CONNECTION TEST")
    print("=" * 60)
    print(f"App Key present: {'Yes' if app_key else 'No'}")
    print(f"App Secret present: {'Yes' if app_secret else 'No'}")
    print(f"Refresh Token present: {'Yes' if refresh_token else 'No'}")
    print(f"Access Token present: {'Yes' if access_token else 'No'}")
    print()
    
    # Test refresh token connection
    if app_key and app_secret and refresh_token:
        print("Testing refresh token connection...")
        try:
            dbx = dropbox.Dropbox(
                oauth2_refresh_token=refresh_token,
                app_key=app_key,
                app_secret=app_secret
            )
            
            # Test the connection
            account = dbx.users_get_current_account()
            print("✅ Refresh token connection successful!")
            print(f"Account: {account.name.display_name} ({account.email})")
            
            # Test listing files
            try:
                files = dbx.files_list_folder("/Scrabble App")
                print(f"✅ Can list files: {len(files.entries)} items found")
                for entry in files.entries:
                    if hasattr(entry, 'size'):
                        print(f"   - {entry.name} ({entry.size} bytes)")
                    else:
                        print(f"   - {entry.name} (folder)")
            except Exception as e:
                print(f"❌ Error listing files: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Refresh token connection failed: {e}")
            return False
    
    # Test access token connection (fallback)
    elif access_token:
        print("Testing access token connection...")
        try:
            dbx = dropbox.Dropbox(access_token)
            account = dbx.users_get_current_account()
            print("✅ Access token connection successful!")
            print(f"Account: {account.name.display_name} ({account.email})")
            return True
        except Exception as e:
            print(f"❌ Access token connection failed: {e}")
            return False
    
    else:
        print("❌ No valid Dropbox credentials found")
        return False

if __name__ == "__main__":
    test_refresh_token_connection() 