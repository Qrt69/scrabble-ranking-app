import dropbox
import os
import tempfile
import logging
from datetime import datetime
import pandas as pd
import json

logger = logging.getLogger(__name__)

class DropboxManager:
    def __init__(self, app_key, app_secret, refresh_token=None, access_token=None):
        """Initialize Dropbox connection with refresh token support"""
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.app_folder = "/Scrabble App"  # Your app folder name
        
        # Initialize connection
        if access_token:
            # Use existing access token (for backward compatibility)
            self.dbx = dropbox.Dropbox(access_token)
        elif refresh_token:
            # Use refresh token for long-term access
            self.dbx = dropbox.Dropbox(oauth2_refresh_token=refresh_token, app_key=app_key, app_secret=app_secret)
        else:
            raise ValueError("Either access_token or refresh_token must be provided")
        
    def refresh_access_token(self):
        """Refresh the access token using the refresh token"""
        try:
            if self.refresh_token:
                # Create new Dropbox instance with refresh token
                self.dbx = dropbox.Dropbox(oauth2_refresh_token=self.refresh_token, app_key=self.app_key, app_secret=self.app_secret)
                logger.info("Access token refreshed successfully")
                return True
            else:
                logger.warning("No refresh token available for token refresh")
                return False
        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
            return False
    
    def test_connection(self):
        """Test if Dropbox connection works"""
        try:
            self.dbx.users_get_current_account()
            logger.info("Dropbox connection successful")
            return True
        except dropbox.exceptions.AuthError as e:
            if "expired_access_token" in str(e):
                logger.info("Access token expired, attempting to refresh...")
                if self.refresh_access_token():
                    # Test connection again after refresh
                    try:
                        self.dbx.users_get_current_account()
                        logger.info("Dropbox connection successful after token refresh")
                        return True
                    except Exception as e2:
                        logger.error(f"Connection failed after token refresh: {e2}")
                        return False
                else:
                    logger.error("Failed to refresh access token")
                    return False
            else:
                logger.error(f"Dropbox authentication error: {e}")
                return False
        except Exception as e:
            logger.error(f"Dropbox connection failed: {e}")
            return False
    
    def _ensure_valid_connection(self):
        """Ensure we have a valid connection, refreshing token if needed"""
        try:
            # Test current connection
            self.dbx.users_get_current_account()
            return True
        except dropbox.exceptions.AuthError as e:
            if "expired_access_token" in str(e):
                logger.info("Access token expired, refreshing...")
                return self.refresh_access_token()
            else:
                raise e
    
    def list_files(self):
        """List all files in the app folder"""
        try:
            self._ensure_valid_connection()
            result = self.dbx.files_list_folder(self.app_folder)
            files = []
            for entry in result.entries:
                # Only process files, not folders
                if hasattr(entry, 'size'):
                    files.append({
                        'name': entry.name,
                        'path': entry.path_display,
                        'size': entry.size,
                        'modified': entry.server_modified
                    })
            logger.info(f"Found {len(files)} files in Dropbox")
            return files
        except Exception as e:
            logger.error(f"Error listing Dropbox files: {e}")
            return []
    
    def download_file(self, dropbox_path, local_path):
        """Download a file from Dropbox to local path"""
        try:
            self._ensure_valid_connection()
            with open(local_path, 'wb') as f:
                metadata, response = self.dbx.files_download(dropbox_path)
                f.write(response.content)
            logger.info(f"Downloaded {dropbox_path} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"Error downloading {dropbox_path}: {e}")
            return False
    
    def upload_file(self, local_path, dropbox_path):
        """Upload a file from local path to Dropbox"""
        try:
            self._ensure_valid_connection()
            with open(local_path, 'rb') as f:
                self.dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
            logger.info(f"Uploaded {local_path} to {dropbox_path}")
            return True
        except Exception as e:
            logger.error(f"Error uploading {local_path}: {e}")
            return False
    
    def file_exists(self, dropbox_path):
        """Check if a file exists in Dropbox"""
        try:
            self._ensure_valid_connection()
            self.dbx.files_get_metadata(dropbox_path)
            return True
        except dropbox.exceptions.ApiError as e:
            if e.error.is_not_found():
                return False
            else:
                raise e
    
    def sync_excel_files(self, required_files):
        """Sync Excel files from Dropbox to local storage"""
        synced_files = []
        
        for filename in required_files:
            dropbox_path = f"{self.app_folder}/{filename}"
            local_path = filename
            
            if self.file_exists(dropbox_path):
                if self.download_file(dropbox_path, local_path):
                    synced_files.append(filename)
                    logger.info(f"Synced {filename} from Dropbox")
            else:
                logger.warning(f"File {filename} not found in Dropbox")
        
        return synced_files
    
    def backup_excel_file(self, local_filename):
        """Backup an Excel file to Dropbox after updates"""
        dropbox_path = f"{self.app_folder}/{local_filename}"
        
        if os.path.exists(local_filename):
            if self.upload_file(local_filename, dropbox_path):
                logger.info(f"Backed up {local_filename} to Dropbox")
                return True
            else:
                logger.error(f"Failed to backup {local_filename} to Dropbox")
                return False
        else:
            logger.error(f"Local file {local_filename} not found for backup")
            return False
    
    def upload_pdf_report(self, local_pdf_path, date_str):
        """Upload a PDF report to Dropbox"""
        # Generate filename based on date
        dt_obj = datetime.strptime(date_str, '%d/%m/%Y')
        if dt_obj.month in [7, 8]:
            # Summer competition
            filename = f"zomerwedstrijd van {dt_obj.day}-{dt_obj.month}-{str(dt_obj.year)[2:]}.pdf"
        else:
            # Regular season
            filename = f"wedstrijd van {dt_obj.day}-{dt_obj.month}-{dt_obj.year}.pdf"
        
        dropbox_path = f"{self.app_folder}/Wedstrijdverslagen/{filename}"
        
        if self.upload_file(local_pdf_path, dropbox_path):
            logger.info(f"Uploaded PDF report {filename} to Dropbox")
            return True
        else:
            logger.error(f"Failed to upload PDF report {filename} to Dropbox")
            return False

# Global Dropbox manager instance
dropbox_manager = None

def initialize_dropbox(app_key=None, app_secret=None, refresh_token=None, access_token=None):
    """Initialize the global Dropbox manager with refresh token support"""
    global dropbox_manager
    
    # For backward compatibility, if only access_token is provided
    if access_token and not refresh_token:
        dropbox_manager = DropboxManager(access_token=access_token)
    elif refresh_token and app_key and app_secret:
        dropbox_manager = DropboxManager(app_key=app_key, app_secret=app_secret, refresh_token=refresh_token)
    else:
        logger.error("Invalid Dropbox configuration. Need either access_token or (app_key, app_secret, refresh_token)")
        return False
    
    return dropbox_manager.test_connection()

def get_dropbox_manager():
    """Get the global Dropbox manager instance"""
    return dropbox_manager 