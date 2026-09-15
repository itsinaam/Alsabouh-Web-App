import mimetypes
import uuid
from typing import Optional
from supabase import create_client, Client
from app.config.settings import settings


class SupabaseStorageService:
    """
    Storage service encapsulating Supabase Storage Bucket operations.
    Designed with a clean interface so the underlying storage provider (Supabase, S3, Azure)
    can be swapped without changing business logic.
    """

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.supabase_key = settings.SUPABASE_KEY
        self.bucket_name = settings.SUPABASE_BUCKET_NAME
        self.client: Optional[Client] = None

        if self.supabase_url and self.supabase_key:
            self.client = create_client(self.supabase_url, self.supabase_key)
            self._ensure_bucket()

    def _ensure_bucket(self):
        """Ensures the storage bucket exists with public access enabled."""
        if not self.client:
            return
        try:
            buckets = self.client.storage.list_buckets()
            bucket_names = [b.name for b in buckets]
            if self.bucket_name not in bucket_names:
                self.client.storage.create_bucket(self.bucket_name, options={"public": True})
        except Exception as e:
            # If bucket exists or error occurs, log and proceed gracefully
            print(f"[StorageService] Notice during bucket verification: {e}")

    def upload_file(
        self,
        file_bytes: bytes,
        destination_path: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Uploads a file's byte data to the Supabase storage bucket.
        Returns the public accessible URL of the uploaded file.
        """
        if not self.client:
            raise RuntimeError("Supabase client is not configured. Check SUPABASE_URL and SUPABASE_KEY in .env.")

        if not content_type:
            content_type, _ = mimetypes.guess_type(destination_path)
            content_type = content_type or "application/octet-stream"

        file_options = {
            "content-type": content_type,
            "upsert": "true"
        }

        # Upload file
        self.client.storage.from_(self.bucket_name).upload(
            path=destination_path,
            file=file_bytes,
            file_options=file_options
        )

        # Retrieve and return public URL
        public_url = self.client.storage.from_(self.bucket_name).get_public_url(destination_path)
        return public_url

    def upload_driver_document(
        self,
        file_bytes: bytes,
        original_filename: str,
        category: str,  # e.g., 'profile_photos', 'license_front', 'license_back', 'medical_certs'
        driver_id_or_ref: str
    ) -> str:
        """
        Helper method to organize driver attachments into clean directory structures.
        """
        extension = original_filename.split(".")[-1] if "." in original_filename else "bin"
        unique_filename = f"{uuid.uuid4().hex[:12]}.{extension}"
        destination_path = f"drivers/{driver_id_or_ref}/{category}/{unique_filename}"
        content_type, _ = mimetypes.guess_type(original_filename)

        return self.upload_file(file_bytes, destination_path, content_type)

    def upload_profile_picture(
        self,
        file_bytes: bytes,
        original_filename: str,
        role: str,
        user_id: str or int,
    ) -> str:
        """
        Uploads an avatar/profile picture into a structured profiles directory:
        profiles/{role}/{user_id}/avatar_{uuid}.{ext}
        """
        clean_role = str(role).lower().replace(" ", "_").replace("-", "_")
        extension = original_filename.split(".")[-1].lower() if "." in original_filename else "jpg"
        unique_filename = f"avatar_{uuid.uuid4().hex[:8]}.{extension}"
        destination_path = f"profiles/{clean_role}/{user_id}/{unique_filename}"
        content_type, _ = mimetypes.guess_type(original_filename)

        return self.upload_file(file_bytes, destination_path, content_type or "image/jpeg")

    def delete_file_by_url(self, file_url: Optional[str]) -> bool:
        """
        Extracts relative storage path from Supabase public URL and deletes the file.
        """
        if not file_url or not self.client:
            return False
        try:
            marker = f"/{self.bucket_name}/"
            if marker in file_url:
                destination_path = file_url.split(marker, 1)[1]
                return self.delete_file(destination_path)
            return False
        except Exception as e:
            print(f"[StorageService] Error deleting file by URL {file_url}: {e}")
            return False

    def delete_file(self, destination_path: str) -> bool:
        """Deletes a file from the Supabase bucket."""
        if not self.client:
            return False
        try:
            self.client.storage.from_(self.bucket_name).remove([destination_path])
            return True
        except Exception as e:
            print(f"[StorageService] Error deleting file {destination_path}: {e}")
            return False


storage_service = SupabaseStorageService()
