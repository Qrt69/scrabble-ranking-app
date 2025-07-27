#!/usr/bin/env python3
"""
Comprehensive Dropbox connection diagnostic script
This will help identify exactly what's wrong with the Dropbox connection
"""

import os
import sys
import logging
import requests
import dropbox
from datetime import datetime

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_environment():
    """Test environment variables and basic setup"""
    print("=== ENVIRONMENT TEST ===")
    
    # Check if we're on Render
    is_render = os.environ.get('RENDER', False)
    print(f"Running on Render: {is_render}")
    
    # Check Python version
    print(f"Python version: {sys.version}")
    
    # Check Dropbox token
    dropbox_token = os.environ.get("DROPBOX_TOKEN", "")
    print(f"DROPBOX_TOKEN present: {'Yes' if dropbox_token else 'No'}")
    print(f"DROPBOX_TOKEN length: {len(dropbox_token)}")
    print(f"DROPBOX_TOKEN starts with: {dropbox_token[:10]}..." if dropbox_token else "No token")
    
    # Check other environment variables
    debug_mode = os.environ.get("DEBUG", "")
    print(f"DEBUG mode: {debug_mode}")
    
    return dropbox_token

def test_network_connectivity():
    """Test basic network connectivity"""
    print("\n=== NETWORK CONNECTIVITY TEST ===")
    
    try:
        # Test basic internet connectivity
        response = requests.get("https://www.google.com", timeout=10)
        print(f"Internet connectivity: ✅ ({response.status_code})")
    except Exception as e:
        print(f"Internet connectivity: ❌ ({e})")
        return False
    
    try:
        # Test Dropbox API connectivity
        response = requests.get("https://api.dropboxapi.com/2/users/get_current_account", timeout=10)
        print(f"Dropbox API reachable: ✅ ({response.status_code})")
    except Exception as e:
        print(f"Dropbox API reachable: ❌ ({e})")
        return False
    
    return True

def test_dropbox_token_validity(token):
    """Test if the Dropbox token is valid"""
    print("\n=== DROPBOX TOKEN VALIDITY TEST ===")
    
    if not token:
        print("❌ No token provided")
        return False
    
    try:
        # Create Dropbox client
        dbx = dropbox.Dropbox(token)
        print("✅ Dropbox client created successfully")
        
        # Test token by getting account info
        account = dbx.users_get_current_account()
        print(f"✅ Token is valid - Account: {account.name.display_name}")
        print(f"   Email: {account.email}")
        print(f"   Country: {account.country}")
        
        return True
        
    except dropbox.exceptions.AuthError as e:
        print(f"❌ Authentication error: {e}")
        print("   This usually means the token is invalid or expired")
        return False
    except dropbox.exceptions.ApiError as e:
        print(f"❌ API error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_dropbox_operations(token):
    """Test basic Dropbox operations"""
    print("\n=== DROPBOX OPERATIONS TEST ===")
    
    if not token:
        print("❌ No token provided")
        return False
    
    try:
        dbx = dropbox.Dropbox(token)
        
        # Test listing files
        print("Testing file listing...")
        result = dbx.files_list_folder("")
        print(f"✅ Root folder listing successful - {len(result.entries)} items")
        
        # Look for the Scrabble App folder
        app_folder = None
        for entry in result.entries:
            if hasattr(entry, 'name') and entry.name == "Scrabble App":
                app_folder = entry
                break
        
        if app_folder:
            print("✅ Found 'Scrabble App' folder")
            
            # List files in the app folder
            app_files = dbx.files_list_folder("/Scrabble App")
            print(f"✅ App folder listing successful - {len(app_files.entries)} files")
            
            for entry in app_files.entries:
                if hasattr(entry, 'size'):
                    print(f"   - {entry.name} ({entry.size} bytes)")
                else:
                    print(f"   - {entry.name} (folder)")
        else:
            print("❌ 'Scrabble App' folder not found in root")
            print("   Available folders:")
            for entry in result.entries:
                if not hasattr(entry, 'size'):
                    print(f"   - {entry.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Dropbox operations failed: {e}")
        return False

def test_dropbox_integration_module():
    """Test the dropbox_integration module"""
    print("\n=== DROPBOX INTEGRATION MODULE TEST ===")
    
    try:
        import dropbox_integration
        print("✅ dropbox_integration module imported successfully")
        
        # Test initialization
        token = os.environ.get("DROPBOX_TOKEN", "")
        if token:
            success = dropbox_integration.initialize_dropbox(token)
            print(f"✅ Module initialization: {'Success' if success else 'Failed'}")
            
            if success:
                manager = dropbox_integration.get_dropbox_manager()
                if manager:
                    print("✅ Dropbox manager retrieved successfully")
                    
                    # Test connection
                    if manager.test_connection():
                        print("✅ Manager connection test passed")
                    else:
                        print("❌ Manager connection test failed")
                else:
                    print("❌ Dropbox manager is None")
        else:
            print("❌ No token available for module test")
            
    except ImportError as e:
        print(f"❌ Could not import dropbox_integration: {e}")
        return False
    except Exception as e:
        print(f"❌ Module test error: {e}")
        return False
    
    return True

def main():
    """Run all diagnostic tests"""
    print("🔍 DROPBOX CONNECTION DIAGNOSTIC")
    print("=" * 50)
    print(f"Timestamp: {datetime.now()}")
    print()
    
    # Run all tests
    token = test_environment()
    
    if not token:
        print("\n🚨 CRITICAL: No DROPBOX_TOKEN found!")
        print("   Please check your environment variables.")
        return
    
    network_ok = test_network_connectivity()
    if not network_ok:
        print("\n🚨 CRITICAL: Network connectivity issues!")
        return
    
    token_valid = test_dropbox_token_validity(token)
    if not token_valid:
        print("\n🚨 CRITICAL: Dropbox token is invalid!")
        print("   You may need to regenerate your Dropbox access token.")
        return
    
    operations_ok = test_dropbox_operations(token)
    module_ok = test_dropbox_integration_module()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 DIAGNOSTIC SUMMARY")
    print("=" * 50)
    
    if token_valid and operations_ok and module_ok:
        print("🎉 All tests passed! Dropbox should work correctly.")
        print("   If your app still has issues, the problem might be:")
        print("   - File permissions in Dropbox")
        print("   - Specific file access issues")
        print("   - App-specific logic errors")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
    
    print(f"\nDiagnostic completed at: {datetime.now()}")

if __name__ == "__main__":
    main() 